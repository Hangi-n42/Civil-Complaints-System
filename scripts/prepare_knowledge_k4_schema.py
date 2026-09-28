"""Add the five reviewed K4 pilot definitions through existing K3 decisions.

Run from an activated project environment: python scripts/prepare_knowledge_k4_schema.py
Requires imported/parsed pilot sources and a reviewed K3 base in the local DB.
No parsing, model calls, source edits, or operational activation are performed.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.knowledge.ontology_schema import decide, default_cqs, get_ontology, publish
from app.knowledge.service import KnowledgeService, encode, utcnow


def matches(locator, expected):
    return all(locator.get(key) == value for key, value in expected.items())


def resolve_inputs(service, config):
    sources, selected, excluded = {}, {}, []
    for name, spec in config['sources'].items():
        found = [(item['source'], version) for item in service.sources()['items']
                 for version in item['versions']
                 if version['sha256'] == spec['sha256'] and version['format'] == spec['format']]
        if len(found) != 1:
            raise ValueError(f'{name}: 일치하는 등록 원문 하나가 필요합니다. 먼저 K2 파일럿을 등록하세요.')
        source, version = found[0]
        if version['processing_status'] != 'parsed':
            raise ValueError(f'{name}: 자료를 먼저 파싱 완료해야 합니다.')
        selection = spec['selection']
        blocks = service.blocks(source['id'], version['id'])['items']
        chosen = []
        for block in blocks:
            locator = block['locator']
            include = (matches(locator, selection.get('locator', {}))
                       and ('script_arrays' not in selection or locator.get('script_array') in selection['script_arrays'])
                       and ('official_codes' not in selection or locator.get('official_code') in selection['official_codes']))
            if include:
                chosen.append(block)
            else:
                excluded.append(dict(block_id=block['id'], source_version_id=version['id'],
                                     reason=spec['excluded_reason']))
        if not chosen:
            raise ValueError(f'{name}: 선택 범위의 추출 블록이 없습니다.')
        sources[name] = dict(source_id=source['id'], source_version_id=version['id'],
                             sha256=version['sha256'], parse_run_ids=list(dict.fromkeys(b['parse_run_id'] for b in chosen)),
                             latest_parse_run_id=version['latest_parse_run_id'], selection=selection)
        selected[name] = chosen
    values = []
    for proposal in config['candidates']:
        candidate = deepcopy(proposal)
        candidate['evidence'] = []
        for ref in candidate.pop('evidence_refs'):
            found = [b for b in selected[ref['source']] if matches(b['locator'], ref['locator'])
                     and ref['quote'] in b['text']]
            if len(found) != 1:
                raise ValueError(f"{candidate['id']}: 근거 위치와 발췌가 한 블록에 일치해야 합니다: {ref}")
            candidate['evidence'].append(dict(evidence_id=found[0]['evidence_id'], quote=ref['quote']))
        values.append(candidate)
    return sources, selected, excluded, values


def prepare(db_path, config_path, base_id=None):
    db_path = Path(db_path)
    if not db_path.exists():
        raise ValueError('로컬 지식 DB가 없습니다. K2 자료 등록·파싱과 K3 기준 온톨로지 검토가 먼저 필요합니다.')
    # Do not let the service startup recovery mark another process's active job as interrupted.
    with sqlite3.connect(db_path) as db:
        if any(json.loads(r[0])['status'] in {'queued', 'running', 'cancel_requested'}
               for r in db.execute('SELECT payload FROM runs')):
            raise ValueError('실행 중인 지식 작업이 있습니다. 해당 작업이 끝난 뒤 실행하세요.')
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    service = KnowledgeService(db_path)
    started = monotonic()
    run = None
    try:
        base_id = base_id or config['base_ontology_version_id']
        try:
            base = get_ontology(service, base_id)
        except KeyError as exc:
            raise ValueError('검토된 K3 기준 버전이 필요합니다. 해당 DB의 --base-ontology-version-id를 지정하세요.') from exc
        if base['status'] != 'reviewed':
            raise ValueError('기준 온톨로지는 reviewed 상태여야 합니다.')
        sources, selected, excluded, candidates = resolve_inputs(service, config)
        blocks = [b for group in selected.values() for b in group]
        cqs = [cq for cq in default_cqs()['items'] if cq['id'] in config['cq_ids']]
        if {cq['id'] for cq in cqs} != set(config['cq_ids']):
            raise ValueError('선택한 개발 CQ 질문이 없습니다.')
        identity = dict(config=config, base_id=base_id, base_hash=base['schema_hash'], cqs=cqs,
                        block_ids=[b['id'] for b in blocks])
        digest = sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        run_id = digest[:32]
        with service.repository.connect() as db:
            row = db.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()
            run = json.loads(row['payload']) if row else None
            if run and run.get('manual_input_hash') != digest:
                raise ValueError('보충 실행 식별자가 다른 입력과 충돌했습니다.')
            if not run:
                run = dict(id=run_id, kind='ontology', origin='manual', manual_input_hash=digest,
                           supplement_version=config['version'], status='running',
                           input_version_ids=[s['source_version_id'] for s in sources.values()],
                           base_ontology_version_id=base_id, base_candidates=base['candidates'],
                           frozen_blocks=blocks, sources=sources, cqs=cqs, excluded_blocks=excluded,
                           units=[dict(id='manual-schema-supplement', stage='manual', status='running', error=None)],
                           review=dict(origin='manual', actor='codex-source-review', note=config['review_note']),
                           started_at=utcnow(), finished_at=None,
                           metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
                db.execute('INSERT INTO runs VALUES(?,?)', (run_id, encode(run)))
        reused = run['status'] == 'succeeded'
        if not reused:
            run.update(publish(service, run, candidates))
            with service.repository.connect() as db:
                change = service.repository.get(db, 'changesets', run['changeset_id'])
            if not change['reviewed_ontology_version_id']:
                decision = decide(service, change['id'], dict(
                    expected_changeset_revision=change['revision'], actor='codex-source-review',
                    decisions=[dict(candidate_id=c['id'], action='accept', reason=config['review_note']) for c in candidates]))
                run['reviewed_ontology_version_id'] = decision['reviewed_ontology_version_id']
            else:
                run['reviewed_ontology_version_id'] = change['reviewed_ontology_version_id']
            run['units'][0].update(status='succeeded', error=None)
            run.update(status='succeeded', finished_at=utcnow())
            run['metrics']['elapsed_s'] = round(monotonic() - started, 3)
            with service.repository.connect() as db:
                service.repository.save(db, 'runs', run)
        reviewed = get_ontology(service, run['reviewed_ontology_version_id'])
        expected = {c['id'] for c in base['candidates']} | {c['id'] for c in candidates}
        assert {c['id'] for c in reviewed['candidates']} == expected
        assert reviewed['status'] == 'reviewed' and run['metrics']['llm_calls'] == 0
        for source in sources.values():
            current = service.version(source['source_id'], source['source_version_id'])['version']
            assert current['latest_parse_run_id'] == source['latest_parse_run_id']
        return dict(run_id=run_id, reused=reused, ontology_version_id=reviewed['id'],
                    schema_hash=reviewed['schema_hash'], changeset_id=run['changeset_id'],
                    origin='manual', review_note=config['review_note'], candidate_count=len(reviewed['candidates']),
                    added_candidate_ids=[c['id'] for c in candidates], llm_calls=0,
                    source_version_ids=run['input_version_ids'], registry_source_version_id=sources['csv']['source_version_id'],
                    sources=sources, block_ids=[b['id'] for b in blocks],
                    selected_block_ids={name: [b['id'] for b in group] for name, group in selected.items()},
                    excluded_blocks=excluded, cqs=cqs)
    except Exception as exc:
        if run and run['status'] != 'succeeded':
            run.update(status='failed', finished_at=utcnow())
            run['units'][0].update(status='failed', error=str(exc))
            with service.repository.connect() as db:
                service.repository.save(db, 'runs', run)
        raise
    finally:
        service.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-path', type=Path, default=Path(settings.KNOWLEDGE_DB_PATH))
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/knowledge/k4_schema_supplement.json')
    parser.add_argument('--base-ontology-version-id')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/knowledge/pilot_v1/k4_prepared.json')
    args = parser.parse_args()
    result = prepare(args.db_path, args.config, args.base_ontology_version_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('run_id', 'reused', 'ontology_version_id', 'candidate_count', 'llm_calls')}, ensure_ascii=False))
    print('선택 블록:', {k: len(v) for k, v in result['selected_block_ids'].items()}, '| 제외:', len(result['excluded_blocks']))


if __name__ == '__main__':
    main()
