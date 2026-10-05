"""Compare role design before the actual failure, with identical source/targets and no later types."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import sqlite3
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

import httpx
import jsonschema
from app.knowledge import discovery_analysis as a2, discovery_synthesis as synthesis, discovery_scope as scope
from app.knowledge.service import KnowledgeService, encode
from scripts.run_knowledge_a6 import digest, write
from scripts.run_knowledge_meaning_probe import configure
from scripts.run_knowledge_neighbor_comparison import clean_run, group_for


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def payload(prompt):
    return json.loads(prompt.split('\nINPUT:\n')[1])


def compare(left, right):
    """Only connected-relation packets/selection metadata and their standard instruction differ."""
    a, b = payload(left['prompt']), payload(right['prompt'])
    assert 'relation_neighbors' not in a and b['relation_neighbors']
    b.pop('relation_neighbors'); b.pop('conceptualization_context')
    assert a == b
    assert left['schema'] == right['schema']
    intro = left['prompt'].split('\nINPUT:\n')[0]
    richer = right['prompt'].split('\nINPUT:\n')[0]
    start = richer.index('\nrelation_neighbors는')
    end = richer.index('본문 공유는 개체 동일성 판정이 아니다.\n', start)
    end += len('본문 공유는 개체 동일성 판정이 아니다.\n')
    assert intro == richer[:start] + richer[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--source-db', type=Path, required=True)
    parser.add_argument('--criteria', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(); root = args.output
    prior = read(args.baseline / 'inputs.json')
    configure(prior['run']['recipe'])
    a2.settings.KNOWLEDGE_DISCOVERY_NEIGHBORS = True
    if not args.execute:
        root.mkdir(parents=True, exist_ok=False)
        by = {b['id']: b for b in prior['blocks']}; cm = a2.profile.contexts(prior['blocks'])
        packets = []; sources = [args.baseline/'inputs.json', args.source_db, args.criteria]
        for name, index in [('authority', 1), ('definitions', 2)]:
            case = deepcopy(next(c for c in prior['cases'] if c['id'] == name))
            historical = args.baseline/'execution'/f'{name}_N1.json'
            sources.append(historical)
            # The failed Concept supplied no types to the later role-design failure.
            assert read(historical)['concept'] is None
            with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro', uri=True) as db:
                original = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (case['source_run'],)).fetchone()[0])
            raw = deepcopy(next(u for u in original['analysis_units'] if u['id'] == case['source_unit']))
            assert raw['status'] == 'succeeded' and raw['attempts']
            assert a2.profile.digest(raw) == case['relation_provenance']['unit_hash']
            assert [r for r in raw['output']['relations'] if case['block_id'] in r['evidence_ids']] == case['relations']
            run = clean_run(prior['run']); run['analysis_units'] = [raw]
            run['frontier'] = [group_for(case)]
            run['model_identity'] = a2.model_identity(run['recipe'])
            targets = case['relations'] if name == 'authority' else [case['relations'][index]]
            base, deps, supplied = synthesis.context_for(targets, by, cm)
            base['design_relation_ids'] = [r['id'] for r in targets]
            base, deps = scope.source_context(base, deps, by)
            base['comparison_terms'] = []
            owner = dict(id=name, primary_candidate_ids=[case['relations'][index]['id']])
            rich, deps, terms = synthesis.neighbor_context(run, 'builder', base, supplied, owner, by, cm)
            assert terms == supplied and base['reviewed_base'] == [] and base['unapproved_observations'] == []
            assert rich['blocks'] == base['blocks'], 'Selector must not add or cut original text'
            selected = rich['conceptualization_context']['selected_relation_ids']
            expected = [r['id'] for r in case['relations']] if name == 'authority' else [case['relations'][index]['id']]
            assert set(selected) == set(expected)
            if name == 'authority':
                anchors = [n['endpoints']['object'] for n in rich['relation_neighbors']]
                assert anchors[0] == anchors[1] and anchors[0][-2:] == [329, 380]
            pair = []
            for arm, context in [('A', base), ('B', rich)]:
                run = deepcopy(run); run['id'] = uuid4().hex
                bound = a2.segments.bind(context, run['id'], 'builder:'+name, stable=True)
                mapping, prompt = a2.make_prompt(run, 'builder', bound, deps, terms)
                _, schema, _, _ = a2.response_contract(run, 'builder', bound, terms, mapping, sorted(a2.raw_refs(bound)))
                jsonschema.Draft202012Validator.check_schema(schema)
                size = a2.input_size(run, 'builder', context, deps, terms)
                assert size['input_chars'] <= size['input_chars_limit'] and size['request_input_bytes'] <= size['input_bytes_limit'], size
                row = dict(case=name, arm=arm, run=deepcopy(run), context=context, deps=deps,
                           supplied=terms, prompt=prompt, schema=schema, size=size, selection=owner)
                pair.append(row)
            compare(*pair)
            packets.extend(pair if name == 'authority' else pair[::-1])
        write(root/'inputs.json', dict(blocks=prior['blocks'], packets=packets))
        runtime = [*Path('app/knowledge').glob('*.py'), Path(__file__), Path('app/core/config.py'),
                   Path('scripts/run_knowledge_neighbor_comparison.py'), Path('scripts/run_knowledge_meaning_probe.py')]
        write(root/'freeze.json', dict(inputs_sha256=digest(root/'inputs.json'), criteria=read(args.criteria),
            sources={str(p.resolve()): digest(p) for p in sources},
            runtime_hashes={str(p.resolve()): digest(p) for p in runtime}, max_http=4, max_seconds=7200,
            semantic_retries=0, shared_relation_new_http=0, development_exposed=True))
        print(json.dumps([dict(case=p['case'], arm=p['arm'], **p['size']) for p in packets])); return
    data = read(root/'inputs.json'); frozen = read(root/'freeze.json')
    assert digest(root/'inputs.json') == frozen['inputs_sha256']
    assert all(digest(Path(p)) == h for p,h in {**frozen['sources'], **frozen['runtime_hashes']}.items())
    out = root/'execution'; out.mkdir(exist_ok=False)
    (out/'blind').mkdir()
    with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(out/'knowledge.db') as db:
        src.backup(db)
    service = KnowledgeService(out/'knowledge.db'); by = {b['id']: b for b in data['blocks']}
    original = a2.model_call; post = httpx.AsyncClient.post; calls = []; active = {}; outputs = []; started = monotonic()
    async def observed(client, url, **kwargs):
        if str(url).endswith('/api/generate'):
            request = kwargs['json']; expected = active['packet']
            assert request['prompt'] == expected['prompt'] and request['format'] == expected['schema']
            write(active['path']/'http_request.json', request)
        response = await post(client, url, **kwargs)
        if str(url).endswith('/api/generate'):
            (active['path']/'http_response.json').write_bytes(response.content)
        return response
    async def measured(prompt, schema, stage, run, timeout):
        assert len(calls) < frozen['max_http'] and monotonic()-started < frozen['max_seconds']
        assert all(digest(Path(p)) == h for p,h in frozen['runtime_hashes'].items())
        p = active['packet']; assert prompt == p['prompt'] and schema == p['schema']
        path = out/f'call_{len(calls)+1:02d}'; path.mkdir(); active['path'] = path
        row = dict(case=p['case'], arm=p['arm'], stage=stage, path=str(path)); calls.append(row); start = monotonic()
        try:
            result = await original(prompt, schema, stage, run, min(timeout, frozen['max_seconds']-(monotonic()-started)))
            write(path/'model_response.json', result); return result
        finally:
            row['elapsed_s'] = round(monotonic()-start, 3); write(path/'timing.json', row); print(json.dumps(row), flush=True)
    try:
        with patch.object(a2, 'model_call', measured), patch.object(httpx.AsyncClient, 'post', observed):
            for p in data['packets']:
                run = deepcopy(p['run']); active['packet'] = p
                # Each condition starts from exactly the same historical upstream state.
                with service.repository.connect() as db:
                    db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
                assert run['model_identity'] == a2.model_identity(run['recipe'])
                assert run['recipe'] == a2.recipe(run['recipe']['budgets'])
                value = a2.call(service, run, 'builder', p['case'], p['context'], p['deps'], by, p['supplied'])
                row = dict(case=p['case'], arm=p['arm'], output=value, unit=run['analysis_units'][-1])
                write(out/f'{p["case"]}_{p["arm"]}.json', row); outputs.append(row)
        random.SystemRandom().shuffle(outputs)
        key = {}
        for n,row in enumerate(outputs):
            label = f'sample_{n+1}'; key[label] = dict(case=row['case'], arm=row['arm'])
            write(out/'blind'/f'{label}.json', dict(case=row['case'], output=row['output'],
                status=row['unit']['status'], error=row['unit'].get('error')))
        write(out/'blind_key.json', key)
    finally:
        service.shutdown()
        write(out/'receipt.json', dict(calls=calls, new_http=len(calls), elapsed_s=round(monotonic()-started,3),
            source_unchanged=all(digest(Path(p)) == h for p,h in frozen['sources'].items()),
            runtime_unchanged=all(digest(Path(p)) == h for p,h in frozen['runtime_hashes'].items())))


if __name__ == '__main__':
    main()
