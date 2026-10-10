"""Compare flat literal selections with the saved baseline and interpreted links."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import compare_business_scope_confirmation as confirmation

prior = confirmation.research
ROOT, read, write, sha = prior.ROOT, prior.read, prior.write, prior.sha
OUT = ROOT / 'data/knowledge/evaluations/business_source_selection_probability_20261010/a'
IDS = ['K02', 'AR01', 'AR02', 'NLC-C04', 'NLC-C05', 'K01']
BOUNDARY = 'selected_source_spans는 자동 선택한 원문 위치와 인용이며 정답 관계나 확정된 적용 범위가 아니다. 원문 전체를 기준으로 판단한다.'
SPAN_KEYS = ['block_id', 'block_sha256', 'start_char', 'end_char', 'quote']


def project(case, links):
    blocks = {b['id']: b for b in case['blocks']}
    order = {b['id']: i for i, b in enumerate(case['blocks'])}
    spans = {}
    refs = [ref for link in links['links'] for side in ['from', 'target'] for ref in link[side]]
    refs += [ref for item in links['unresolved'] for ref in item['target']]
    for ref in refs:
        value = {key: ref[key] for key in SPAN_KEYS}
        block = blocks[value['block_id']]
        assert prior.text_hash(block['text']) == value['block_sha256']
        assert block['text'][value['start_char']:value['end_char']] == value['quote']
        key = tuple(value[k] for k in SPAN_KEYS[:-1])
        if key in spans:
            assert spans[key] == value
        spans[key] = value
    return sorted(spans.values(), key=lambda r: (order[r['block_id']], r['start_char'], r['end_char']))


def prompt(case, spans):
    text = prior.previous.prompt(dict(case, selected_source_spans=spans))
    marker = '<|im_end|>\n<|im_start|>user'
    assert text.count(marker) == 1
    return text.replace(marker, '\n' + BOUNDARY + marker, 1)


def prepare():
    assert not (OUT / 'prepared.json').exists()
    confirmation.check_prepared()
    cases = {c['id']: c for c in read(prior.OUT / 'inputs.json') + read(confirmation.OUT / 'inputs.json')}
    saved_baselines = {r['id']: r for r in read(prior.OUT / 'baselines.json')}
    records, rows = [], []
    for ident in IDS:
        folder = confirmation.OUT if ident.startswith('AR') else prior.OUT
        run = folder / ('run' if ident.startswith('AR') else 'run_b')
        raw_records = read(run / 'result.json')['records']
        b1 = next(r for r in raw_records if r['id'] == ident and r['task'] == 'links')
        a1 = next(r for r in raw_records if r['id'] == ident and r['task'] == 'judgment')
        a1_request = next(r for r in read(run / 'b2_requests.json') if r['id'] == ident)
        case = cases[ident]
        assert b1['contract_pass'] and prior.resolve_links(b1['answer'], case) == b1['parsed']
        assert a1_request['prompt'] == prior.linked_judgment_prompt(case, b1['parsed'])
        old_paths = {task: run / (ident + '_' + task + '_response.json') for task in ['links', 'judgment']}
        assert sha(old_paths['links']) == b1['raw_sha256']
        assert sha(old_paths['judgment']) == a1['raw_sha256']
        if ident.startswith('AR'):
            a0 = next(r for r in raw_records if r['id'] == ident and r['task'] == 'baseline')
            a0_prompt = next(r['prompt'] for r in read(folder / 'requests.json')
                             if r['id'] == ident and r['task'] == 'baseline')
            old_paths['baseline'] = run / (ident + '_baseline_response.json')
            assert sha(old_paths['baseline']) == a0['raw_sha256']
        else:
            old = saved_baselines[ident]
            a0, a0_prompt = old['record'], old['prompt']
            old_paths['baseline'] = ROOT / old['raw_path']
            assert sha(old_paths['baseline']) == old['raw_sha256']
        assert a0_prompt == prior.previous.prompt(case)
        spans = project(case, b1['parsed'])
        rows.append(dict(id=ident, task='selection_only', prompt=prompt(case, spans)))
        records.append(dict(id=ident, A0=a0, A1=a1, B1=b1, selected_source_spans=spans,
                            old_raw_files={str(p.relative_to(ROOT)): sha(p) for p in old_paths.values()}))
    skipped = next(r for r in read(confirmation.OUT / 'run/result.json')['records']
                   if r['id'] == 'AR03' and r['task'] == 'links')
    assert not skipped['contract_pass']
    skipped_path = confirmation.OUT / 'run/AR03_links_response.json'
    assert sha(skipped_path) == skipped['raw_sha256']
    write(OUT / 'inputs.json', [cases[i] for i in IDS])
    write(OUT / 'saved_comparison.json', records)
    write(OUT / 'prompts.json', rows)
    write(OUT / 'selection_failure.json', dict(id='AR03', B1=skipped, A2_called=False,
          status='prior_selection_address_failure', denominator_retained=True, repaired=False,
          old_raw_files={str(skipped_path.relative_to(ROOT)): sha(skipped_path)}))
    (OUT / 'settings.json').write_bytes((prior.OUT / 'settings.json').read_bytes())
    code = {**read(confirmation.OUT / 'prepared.json')['code'], str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))}
    write(OUT / 'prepared.json', dict(at=time.time(), code=code,
          files={p.name: sha(p) for p in OUT.iterdir() if p.is_file() and p.suffix in {'.json', '.md', '.txt'}},
          max_new_calls=6, panel_size=7, prior_failure_unmeasured=1,
          previous_freeze_sha256=sha(prior.OUT / 'freeze.json'),
          confirmation_freeze_sha256=sha(confirmation.OUT / 'freeze.json')))


def check_prepared():
    confirmation.check_prepared()
    p = read(OUT / 'prepared.json')
    assert all(sha(OUT / n) == h for n, h in p['files'].items())
    assert all(sha(ROOT / n) == h for n, h in p['code'].items())
    for case in read(OUT / 'saved_comparison.json'):
        assert all(sha(ROOT / n) == h for n, h in case['old_raw_files'].items())
    assert all(sha(ROOT/n)==h for n,h in read(OUT/'selection_failure.json')['old_raw_files'].items())


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check_prepared()
    assert read(OUT / 'execution_authorization.json')['compute_allocated']
    identity = read(prior.previous.OUT / 'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key+'_path'])) == identity[key+'_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as stream:
        assert not json.load(stream)['models']
    props = prior.previous.prior.base.api('/props')
    old = read(prior.OUT / 'props.json')
    assert {k:v for k,v in props.items() if k != 'media_marker'} == {k:v for k,v in old.items() if k != 'media_marker'}
    write(OUT / 'requests.json', [prior.request_row(row) for row in read(OUT / 'prompts.json')])
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), files={n:sha(OUT/n) for n in
          ['prepared.json', 'requests.json', 'props.json', 'execution_authorization.json']}, max_calls=6))


def run():
    check_prepared()
    assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert prior.previous.prior.base.api('/props') == read(OUT/'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    cases = {c['id']:c for c in read(OUT/'inputs.json')}
    result = dict(calls=0, records=[], prior_selection_failure='AR03', semantic_review='pending')
    started = time.monotonic()
    for row in read(OUT/'requests.json'):
        record = dict(id=row['id'], input_tokens=row['input_tokens'], contract_pass=False,
                      request_sha256=prior.text_hash(json.dumps(row['request'], ensure_ascii=False)))
        result['records'].append(record)
        result['calls'] += 1
        assert result['calls'] <= 6
        write(dest/'result.json', result)
        before = time.monotonic()
        try:
            raw = prior.previous.prior.base.call('/completion', row['request'])
            path = dest/(row['id']+'_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'),
                          stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('stop_type') != 'eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{'+response['content'], object_pairs_hook=prior.previous.strict_object)
            record['answer'] = prior.previous.parse_final(answer, cases[row['id']])
            record['label'] = prior.previous.prior.MAPPING[answer['label']]
            record['contract_pass'] = True
        except (OSError, ValueError, KeyError, TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic()-before
        result['wall_s'] = time.monotonic()-started
        write(dest/'result.json', result)
        print(row['id'], record['contract_pass'], record.get('label'), record.get('error'), flush=True)


def selfcheck():
    case = dict(id='test', raw={'Event':'same'}, blocks=[dict(id='b', text='same same'), dict(id='a', text='same')])
    def ref(block, start):
        return dict(block_id=block, block_sha256=prior.text_hash(next(b['text'] for b in case['blocks'] if b['id']==block)),
                    start_char=start, end_char=start+4, quote='same', precision='exact_unverified_meaning')
    links = dict(links=[dict(kind='condition', reason='generated interpretation',
                            **{'from':[ref('a',0),ref('b',5)], 'target':[ref('b',0),ref('b',5)]})],
                 unresolved=[dict(target=[ref('b',0)], reason='unresolved interpretation')])
    spans = project(case, links)
    assert [(r['block_id'],r['start_char']) for r in spans] == [('b',0),('b',5),('a',0)]
    assert all(list(r)==SPAN_KEYS for r in spans)
    text = prompt(case, spans)
    payload = json.loads(text.split('<|im_start|>user\n',1)[1].split('<|im_end|>',1)[0])
    assert payload.pop('selected_source_spans')==spans and payload==case
    assert 'generated interpretation' not in text and 'unresolved interpretation' not in text
    assert text.replace('\n'+BOUNDARY,'') == prior.previous.prompt(dict(case, selected_source_spans=spans))
    print('Exact-address dedup, distinct-location retention, source order, no interpretation and unchanged full case checked.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare','preflight','run','selfcheck'])
    globals()[parser.parse_args().mode]()
