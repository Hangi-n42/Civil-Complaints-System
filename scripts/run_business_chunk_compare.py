"""Frozen small chunk-size comparison through the existing product service."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
import shutil
import sqlite3
import sys
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import autoschema
from app.knowledge.business_models import BusinessRunRequest
from app.knowledge.service import KnowledgeService, utcnow
from app.generation.model_client import ModelClient, configuration
from app.core.config import settings


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope-probe', action='store_true', help='One local list after the recorded Scope/context failures; not another chunk-size comparison')
    args = parser.parse_args()
    base = ROOT / 'data/knowledge/evaluations/autoschemakg_business_20261006'
    original = base / 'busan_v1/knowledge.db'
    output = base / ('u2_scope_probe_v2' if args.scope_probe else 'u1_chunk_size_v1')
    original_hash = sha256(original.read_bytes()).hexdigest()
    with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True) as source:
        parents = [json.loads(row[0]) for row in source.execute('SELECT payload FROM runs')]
        if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in parents):
            raise ValueError('Source DB must be terminal')
        parent = next(r for r in parents if r['id'] == '899f5a8f82ac46b59c074a088c1ed5a7')
        # Frozen contiguous public common/sale-document section, selected before generation.
        selected_indices = [8, 23, 24, 32, 33, 34, 35, 36, 37] if args.scope_probe else [8, *range(23, 38)]
        blocks = [parent['blocks'][n] for n in selected_indices]
        versions = list(dict.fromkeys(b['source_version_id'] for b in blocks))
        raw_versions = [json.loads(source.execute('SELECT payload FROM versions WHERE id=?', (v,)).fetchone()[0]) for v in versions]
        requests = [BusinessRunRequest(source_version_ids=versions, requirement_ids=['busan-R03'],
            block_ids=[b['id'] for b in blocks],
            selection_reason=('기존 실패 원문의 매매 구비서류 하위 목록 전체와 상위 제목: Scope 단순화/원문 순서/기본 항목 문맥 보완의 결합 확인'
                              if args.scope_probe else '공개 공통/매매 구비서류 절과 상위 제목의 고정 국소 청크 크기 비교'),
            extraction_target_chars=size, context_tokens=49152, extraction_tokens=12288,
            source_tokens=4096, review_tokens=4096, representation_tokens=8192,
            timeout=1800, think=False, repair=False, conceptualize=False,
            model=settings.STRUCTURING_MODEL, review_model=settings.KNOWLEDGE_REVIEW_MODEL)
            for size in ((200,) if args.scope_probe else (1000, 200))]
        plans = [dict(request=r.model_dump(), chunks=autoschema.chunks(blocks, r.context_tokens,
                    r.extraction_tokens, r.extraction_target_chars)) for r in requests]
        config = configuration()
        identity = ModelClient(config).identities(dict(draft=requests[0].model, review=requests[0].review_model),
                                                  dict(draft=49152, review=49152))
        output.mkdir(exist_ok=False)
        with sqlite3.connect(output/'knowledge.db') as target:
            source.backup(target)
    raw_files = []
    for version in raw_versions:
        old = original.parent / version['relative_raw_path']
        new = output / version['relative_raw_path']
        assert sha256(old.read_bytes()).hexdigest() == version['sha256']
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
        raw_files.append(dict(path=version['relative_raw_path'], sha256=version['sha256']))
    code_hashes = {}
    for path in [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
                 ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py', Path(__file__)]:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        target = output/'executed_code'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        code_hashes[str(relative)] = sha256(path.read_bytes()).hexdigest()
    freeze = dict(recorded_at=utcnow(), original_database=str(original), original_database_sha256=original_hash,
        parent_run_id=parent['id'], original_parent_sha256=sha256(json.dumps(parent,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        block_ids=[b['id'] for b in blocks], source_chars=sum(len(b['text']) for b in blocks),
        source_blocks=blocks, raw_files=raw_files, plans=plans, code_hashes=code_hashes,
        model_identity=identity, generation=config, product_entrypoint='KnowledgeService.start_business',
        scope_contract=autoschema.SCOPE_CONTRACT, extraction_contract=autoschema.VERSION,
        gold_reference_loaded=False,
        variables=(['Scope contract', 'mention identity', 'source order', 'direct list base+note context']
                   if args.scope_probe else ['extraction_target_chars']),
        scope=('One local list after observed contract/context failures; combined correction, not a chunking effect.'
               if args.scope_probe else 'Small common/sale-document extraction comparison; not a full quality/QA score.'),
        output_reservation_reason='Both arms use 12288 to accommodate original rows plus new explicit source/mention/scope records; no failed-call capacity sweep.',
        conceptualization='deferred equally in both arms; actual concept/repair/QA linkage evaluated separately under U2-U5')
    write_new(output/'freeze.json', freeze)
    assert sha256(original.read_bytes()).hexdigest() == original_hash
    service = KnowledgeService(output/'knowledge.db')
    try:
        results = []
        for name, request in zip(('probe',) if args.scope_probe else ('large', 'small'), requests):
            assert all(sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in code_hashes.items())
            execution = service.start_business(request)
            write_new(output/(name+'_started.json'), execution)
            previous = None
            while True:
                run = service.run(execution['run_id'])
                state = (run['status'], len(run['units']), run['units'][-1]['stage'] if run['units'] else None)
                if state != previous:
                    print(json.dumps(dict(arm=name, run_id=run['id'], state=state)), flush=True)
                    previous = state
                if run['status'] not in {'queued', 'running', 'cancel_requested'}:
                    write_new(output/(name+'_result.json'), run)
                    results.append(dict(arm=name, run_id=run['id'], status=run['status'],
                        claims=len(run['claims']), metrics=run['metrics'], extraction_complete=run.get('extraction_complete')))
                    break
                sleep(1)
        assert all(sha256((ROOT/p).read_bytes()).hexdigest() == h for p,h in code_hashes.items())
        assert sha256(original.read_bytes()).hexdigest() == original_hash
        write_new(output/'terminal.json', dict(recorded_at=utcnow(), results=results, code_files_unchanged=len(code_hashes),
            original_database_unchanged=True, semantic_quality_verified=False))
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
