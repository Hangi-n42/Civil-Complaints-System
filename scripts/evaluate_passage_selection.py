"""Replay stored source-passage rankings; never call an embedding or QA model.

The old BM25 consumer policy and raw top-k are recorded separately. This measures
the shared selector, not new retrieval/model quality. Missing arms stay missing.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import graph_retrieval as gr
from app.knowledge.discovery_profile import FrozenIndex


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def reader(candidates, hits, origin):
    selected = {h['block_id'] for h in hits}
    context = [{k: deepcopy(v) for k, v in c.items() if k != 'linked_claim_ids'}
               for c in candidates if c['id'] in selected]
    return dict(context=context, source_context=gr.source_context(origin['blocks'], context, origin['recipe']['options']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-output', type=Path, nargs='+', required=True,
                        help='Original outputs, oldest first; opened read-only')
    parser.add_argument('--question-ids', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records, origins = {}, {}
    for directory in args.baseline_output:
        with sqlite3.connect(directory.joinpath('knowledge.db').resolve().as_uri() + '?mode=ro', uri=True) as db:
            for qid in args.question_ids:
                for path in sorted(directory.glob(qid + '_*.json')):
                    data = json.loads(path.read_text())
                    run_id = data['result']['run_id']
                    run = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (run_id,)).fetchone()[0])
                    query = run['query']
                    origin = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (query['source_run_id'],)).fetchone()[0])
                    if qid in origins and digest(origins[qid]) != digest(origin):
                        raise ValueError('Stored extraction changed between arms: ' + qid)
                    origins[qid] = origin
                    records[qid, query['retrieval'], query['graph_variant']] = dict(run=run, file=str(path))
    if set(origins) != set(args.question_ids):
        raise ValueError('Unknown question ID')
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = {}
    for path in [ROOT/'app/knowledge'/name for name in
                 ('autoschema.py', 'graph_retrieval.py', 'business_use.py', 'discovery_profile.py')] + [Path(__file__)]:
        target = args.output/'executed_code'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        frozen[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
    summary = []
    for qid, origin in origins.items():
        seed = next(r['run'] for key, r in records.items() if key[0] == qid)
        query = seed['query']
        snapshot = dict(id='run:' + origin['id'], claims=[c for c in origin['claims']
            if not c.get('superseded_by') and not c.get('extraction_error')], concepts=origin['concepts'],
            blocks=origin['blocks'], include_unlinked_blocks=True)
        _, _, passages, _ = gr.build(snapshot, 'full')
        candidates = gr.passage_candidates(passages)
        index = FrozenIndex(candidates, preserve_numbers=True)
        text = query['question'] + '\n' + '\n'.join(query['choices'])
        allowed = {c['id'] for c in candidates}
        for retrieval, variant in [('bm25', 'full'), ('dense', 'entity_event'),
                                   ('hipporag2', 'entity_event'), ('hipporag2', 'full')]:
            record = records.get((qid, retrieval, variant))
            if retrieval == 'bm25':
                ranked = index.rank(text, allowed)
                legacy = index.search(text, allowed, query['limit'])
            elif record:
                stored = record['run']
                for field in ('question', 'choices', 'limit', 'source_run_id'):
                    assert stored['query'][field] == query[field], field
                assert stored['recipe'] == seed['recipe'] and stored['model_identity'] == seed['model_identity']
                ranking = stored['graph_retrieval']['ranked_passages']
                assert {p['id'] for p in ranking} == set(passages)
                assert all(p['evidence'] == passages[p['id']]['evidence'] and
                           p['claim_ids'] == passages[p['id']]['claim_ids'] for p in ranking)
                ranked = [dict(block_id=p['id'], file_id=p['evidence']['source_version_id'], score=p['score']) for p in ranking]
                legacy = ranked[:query['limit']]
            else:
                summary.append(dict(question_id=qid, retrieval=retrieval, variant=variant,
                    status='missing_stored_ranking', new_model_calls=0))
                continue
            selected, trace = gr.select_passages(candidates, ranked, origin['blocks'], origin['recipe']['options'], query['limit'])
            before = reader(candidates, ranked[:query['limit']], origin)
            after = reader(candidates, selected, origin)
            result = dict(question_id=qid, retrieval=retrieval, variant=variant, query=query,
                origin_sha256=digest(origin), model_identity=seed['model_identity'], recipe=seed['recipe'],
                ranking_origin=record['file'] if record else 'raw_bm25_recomputed_cpu',
                stored_run_id=record['run']['id'] if record else None, raw_top_k=ranked[:query['limit']],
                legacy_selected=legacy, selected=selected, selection=trace,
                raw_reader=before, selected_reader=after, raw_reader_sha256=digest(before),
                selected_reader_sha256=digest(after), new_model_calls=0,
                interpretation='Stored ranks replay only; changed reader requires new QA; no quality score')
            write(args.output/f'{qid}_{retrieval}_{variant}.json', result)
            summary.append(dict(question_id=qid, retrieval=retrieval, variant=variant, status='rank_replayed',
                changed_ids=len({h['block_id'] for h in selected} - {h['block_id'] for h in ranked[:query['limit']]}),
                reader_equal=result['raw_reader_sha256'] == result['selected_reader_sha256'], new_model_calls=0))
    write(args.output/'summary.json', dict(selection_contract=gr.SELECTION_CONTRACT, code_hashes=frozen,
        question_ids=args.question_ids, baseline_outputs=[str(p) for p in args.baseline_output], items=summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
