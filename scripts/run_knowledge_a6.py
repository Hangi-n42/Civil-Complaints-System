"""Frozen A6 development comparison on an isolated ledger; never loads assessor answers."""
import argparse
import asyncio
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic, sleep
from unittest.mock import patch
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import settings
from app.generation.service import GenerationService
from app.knowledge import discovery_analysis as a2, discovery_inputs as inputs
from app.knowledge import discovery_profile as profile, ontology_run as manual
from app.knowledge.schemas import RunRequest
from app.knowledge.service import KnowledgeService, utcnow

ASSETS = ROOT / 'configs/knowledge/a6_v1'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def ordered_survey(survey, file_order):
    """Evaluation intervention only: hold Scout priority fixed in both order arms."""
    def wrapped(files, blocks):
        profiles, frontier, contexts = survey(files, blocks)
        frontier.sort(key=lambda g: file_order.index(g['file_id']))
        for index, group in enumerate(frontier):
            group['priority'] = index + 1
            group['reason'] += '; A6 사전 고정 처리 순서'
        return profiles, frontier, contexts
    return wrapped


def wait(service, identifier):
    while True:
        run = service.run(identifier)
        if run['status'] not in {'queued', 'running', 'cancel_requested'}:
            return run
        sleep(.1)


def check_freeze():
    frozen = json.loads((ASSETS / 'freeze.json').read_text(encoding='utf-8'))
    for name, expected in frozen['sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('동결 자산 변경: ' + name)
    return frozen


def run_case(case_id, output, input_root, base=None):
    frozen = check_freeze()
    config = json.loads((ASSETS / 'generation.json').read_text(encoding='utf-8'))
    case = next(c for c in config['cases'] if c['id'] == case_id)
    marker = output / 'study.json'
    if json.loads(marker.read_text(encoding='utf-8'))['freeze'] != frozen:
        raise ValueError('다른 동결 조건의 출력 디렉터리입니다.')
    db_path = output / 'knowledge.db'
    if db_path.resolve() == Path(settings.KNOWLEDGE_DB_PATH).resolve():
        raise ValueError('운영 원장은 평가 출력으로 사용할 수 없습니다.')
    result_path = output / (case_id + '.json')
    reservation = output / (case_id + '.started.json')
    if result_path.exists() or reservation.exists():
        raise ValueError('최초 실행을 덮어쓰거나 자동 재시도하지 않습니다.')
    if bool(case.get('base_case')) != bool(base):
        raise ValueError('증분 단계에는 검수한 이전 단계 version ID가 필요합니다.')
    identity = a2.model_identity(a2.recipe(config['budgets']))
    if {k:v['digest'] for k,v in identity.items()} != config['model_digests']:
        raise ValueError('동결 모델 digest와 다릅니다.')
    if {k:v['name'] for k,v in identity.items()} != config['models']:
        raise ValueError('동결 모델 이름과 다릅니다.')
    write(reservation, dict(started_at=utcnow(), case=case, model_identity=identity, base=base))
    service = KnowledgeService(db_path)
    calls = []
    started = monotonic()
    record = dict(case=case, started_at=utcnow(), model_identity=identity,
                  human_preparation_s=None, human_cq_s=None, human_review_s=None,
                  human_repair_s=None, participant_count=0, model_calls=calls)
    original_call = GenerationService.call_ollama
    original_post = httpx.AsyncClient.post

    async def observed_post(client, url, **kwargs):
        if str(url).endswith('/api/generate'):
            calls[-1]['wire_attempted'] = True
        return await original_post(client, url, **kwargs)

    async def bounded_call(instance, prompt, **kwargs):
        remaining = config['budgets']['model_seconds'] - sum(c['elapsed_s'] for c in calls)
        if len(calls) >= config['budgets']['model_calls'] or remaining <= 0:
            raise ValueError('A6 고정 호출/시간 예산 소진')
        kwargs['timeout'] = min(remaining, config['call_timeout_s'],
                                kwargs.get('timeout') or config['call_timeout_s'])
        kwargs['local_only'] = True
        row = dict(started_at=utcnow(), prompt_sha256=sha256(prompt.encode()).hexdigest(),
                   prompt_chars=len(prompt), options={k:v for k,v in kwargs.items()
                   if k in {'model', 'temperature', 'think', 'num_ctx', 'num_predict', 'timeout'}},
                   elapsed_s=0)
        calls.append(row)
        tick = monotonic()
        try:
            result = await asyncio.wait_for(original_call(instance, prompt, **kwargs), kwargs['timeout'])
            row['metadata'] = {k:v for k,v in result.items() if k != 'text'}
            return result
        except Exception as exc:
            row['error'] = str(exc)
            raise
        finally:
            row['elapsed_s'] = round(monotonic() - tick, 3)
            # Preserve every attempted network generation even if later parsing/publication fails.
            with (output / (case_id + '.calls.jsonl')).open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')

    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(inputs, 'ROOT', input_root.resolve()))
            stack.enter_context(patch.object(GenerationService, 'call_ollama', bounded_call))
            stack.enter_context(patch.object(httpx.AsyncClient, 'post', observed_post))
            stack.enter_context(patch.object(manual, 'BUDGETS',
                {stage: (4096, 32768) for stage in manual.BUDGETS}))
            if case.get('file_order'):
                stack.enter_context(patch.object(profile, 'survey',
                    ordered_survey(profile.survey, case['file_order'])))
            catalog = inputs.catalog(case['scope'], case['step'])
            if catalog['manifest_sha256'] != config['manifest_sha256']:
                raise ValueError('동결 manifest와 다릅니다.')
            grounded = wait(service, service.start(RunRequest(kind='discovery',
                bundle_id=catalog['bundle_id'], manifest_hash=catalog['manifest_sha256'],
                scope=case['scope'], step=case['step'], file_ids=case['file_ids']))['run_id'])
            record['input_run'] = grounded
            if grounded['status'] != 'succeeded':
                raise ValueError('A1 입력 고정 실패')
            if base:
                prior = json.loads((output / (case['base_case'] + '.json')).read_text(encoding='utf-8'))
                from app.knowledge.ontology_schema import get_ontology
                if get_ontology(service, base)['run_id'] != prior['run']['id']:
                    raise ValueError('고정한 이전 실행에서 검수한 version이 아닙니다.')
            common = dict(cqs=[config['cqs'][key] for key in case['cq_ids']])
            if case['method'] == 'manual':
                request = RunRequest(kind='ontology', source_version_ids=grounded['input_version_ids'], **common)
            else:
                request = RunRequest(kind='discovery', discovery_mode='analyze',
                    input_run_id=grounded['id'], lineage_id=case['lineage'],
                    base_ontology_version_id=base, discovery_budgets=config['budgets'], **common)
            run = wait(service, service.start(request)['run_id'])
            record['run'] = run
            block_map = {b['id']: b for b in a2.load_blocks(service, grounded)}
            units = run.get('analysis_units', run['units'])
            def provided_ids(unit):
                if case['method'] != 'manual':
                    return unit.get('provided_block_ids', [])
                return [run['frozen_blocks'][int(row['ref'][1:])]['id']
                        for row in unit.get('inputs', [])]
            groups = {g['id']: g for g in run.get('frontier', [])}
            record['actual_order'] = [dict(stage=u['stage'], unit_id=u['id'],
                primary_order=[dict(file_id=block_map[i]['file_id'], block_index=block_map[i]['block_index'])
                    for i in (groups[u['group_id']]['block_ids'] if u.get('group_id') in groups else provided_ids(u))
                    if i in block_map],
                provided_set=[dict(file_id=block_map[i]['file_id'], block_index=block_map[i]['block_index'],
                             evidence_id=block_map[i]['evidence_id'])
                        for i in provided_ids(u) if i in block_map])
                for u in units if u.get('attempts') or u.get('call', {}).get('attempted')]
            record['input_blocks'] = [dict(file_id=b['file_id'], block_index=b['block_index'],
                id=b['id'], evidence_id=b['evidence_id'], text_sha256=sha256(b['text'].encode()).hexdigest(),
                locator=b['locator']) for b in block_map.values()]
    except Exception as exc:
        record['error'] = str(exc)
    finally:
        service.shutdown()
        record.update(finished_at=utcnow(), elapsed_s=round(monotonic()-started, 3),
                      generation_calls=sum(bool(c.get('wire_attempted')) for c in calls),
                      generation_attempts=len(calls), model_wait_s=round(sum(c['elapsed_s'] for c in calls), 3))
        write(result_path, record)
    print(json.dumps({k:record.get(k) for k in
        ('error', 'generation_calls', 'model_wait_s', 'elapsed_s')}, ensure_ascii=False), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'run'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case')
    parser.add_argument('--input-root', type=Path, default=ROOT)
    parser.add_argument('--base')
    args = parser.parse_args()
    if args.action == 'init':
        frozen = check_freeze()
        args.output.mkdir(parents=True, exist_ok=False)
        write(args.output / 'study.json', dict(freeze=frozen, started_at=utcnow()))
    elif args.case:
        run_case(args.case, args.output, args.input_root, args.base)
    else:
        parser.error('run에는 --case가 필요합니다.')


if __name__ == '__main__':
    main()
