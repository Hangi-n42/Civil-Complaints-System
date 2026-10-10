"""Research-only official Task Calibration scores on existing native label distributions."""
from copy import deepcopy
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

import compare_business_label_selection as base
import compare_business_entailment_boundary as prior
from business_dependency_parser import read, write

ROOT = prior.ROOT
OUT = ROOT / 'data/knowledge/evaluations/business_task_calibration_20261010'
IDS = ['K01', 'K02', 'c13', 'c46', 'c47', 'H02', 'H03', 'A02', 'NLC-C04']
MAPPING = base.MAPPINGS['primary']
VOCAB = 248320
sha = prior.sha


def input_view(case, view):
    result = deepcopy(case)
    if view == 'premise':
        result['raw'] = {}
    elif view == 'hypothesis':
        for field in ['blocks', 'source_parents', 'source_versions', 'source']:
            if field in result:
                result[field] = type(result[field])()
    elif view != 'both':
        raise ValueError('unknown_view')
    return result


def logadd(a, b):
    peak = max(a, b)
    return peak + math.log1p(math.exp(min(a, b) - peak))


def log_options(scores):
    if len(scores) != 3 or not all(math.isfinite(x) for x in scores.values()):
        raise ValueError('invalid_option_logprobs')
    peak = max(scores.values())
    normalizer = peak + math.log(math.fsum(math.exp(v - peak) for v in scores.values()))
    return {k: v - normalizer for k, v in scores.items()}


def calibrate(both, premise, hypothesis):
    if set(both) != set(premise) or set(both) != set(hypothesis):
        raise ValueError('different_options')
    a, b, c = (log_options(x) for x in [both, premise, hypothesis])
    epsilon = math.log(1e-10)
    # Official eval.py: a * log((a*a + 1e-10)/(b*c + 1e-10)); no fitted weight.
    scores = {k: math.exp(a[k]) * (logadd(2 * a[k], epsilon) - logadd(b[k] + c[k], epsilon))
              for k in a}
    ordered = sorted(scores, key=scores.get, reverse=True)
    margin = scores[ordered[0]] - scores[ordered[1]]
    return dict(scores=scores, code=None if margin <= 1e-12 else ordered[0], margin=margin,
                option_probabilities={view: {k: math.exp(v) for k, v in row.items()}
                                      for view, row in [('both', a), ('premise', b), ('hypothesis', c)]})


def selfcheck():
    probabilities = [[.55, .35, .1], [.8, .1, .1], [.8, .1, .1]]
    inputs = [{str(i): math.log(v) for i, v in enumerate(row)} for row in probabilities]
    actual = calibrate(*inputs)
    for i, (a, b, c) in enumerate(zip(*probabilities)):
        official = a * math.log((a*a + 1e-10) / (b*c + 1e-10))
        assert math.isclose(actual['scores'][str(i)], official, rel_tol=0, abs_tol=1e-12)
    tiny = {'1': -1000., '2': -1001., '3': -2000.}
    assert all(math.isfinite(x) for x in calibrate(tiny, tiny, tiny)['scores'].values())
    assert calibrate(*[{'1': 0., '2': 0., '3': 0.}] * 3)['code'] is None
    case = dict(id='same', raw={'Event': 'candidate'}, blocks=[{'text': 'source'}],
                source_parents=[{'child': 'parent'}], source_versions=[{'title': 'heading'}], source={'url': 'origin'})
    assert input_view(case, 'both') == case
    p = input_view(case, 'premise'); h = input_view(case, 'hypothesis')
    assert p['raw'] == {} and {k:v for k,v in p.items() if k != 'raw'} == {k:v for k,v in case.items() if k != 'raw'}
    assert h == dict(id='same', raw=case['raw'], blocks=[], source_parents=[], source_versions=[], source={})
    assert case['raw'] == {'Event': 'candidate'} and case['blocks'] == [{'text': 'source'}]
    print('Official epsilon formula, tiny scores, ties and exact input deletion checks passed')


def prepare():
    assert not (OUT / 'prepared.json').exists()
    cases = {c['id']: c for c in read(prior.LABELS / 'inputs.json')}
    cases.update({c['id']: c for c in read(prior.PERM / 'confirmation_inputs.json')})
    rows = []
    for ident in IDS:
        case = cases[ident]
        if ident == 'NLC-C04':
            folder, stem = prior.PERM / 'confirmation', ident + '_SUC_B'
            prompt_path = prior.PERM / 'prompts' / f'confirmation_{ident}_SUC_B.txt'
            record = next(r for r in read(folder / 'result.json')['rows'] if r['id'] == ident and r['mapping'] == 'SUC')
        else:
            folder, stem = prior.LABELS / 'primary', ident + '_B'
            prompt_path = prior.LABELS / 'prompts' / f'primary_{ident}_B.txt'
            record = next(r for r in read(folder / 'result.json')['cases'] if r['id'] == ident and r['arm'] == 'B')
        assert prompt_path.read_text(encoding='utf-8') == base.prompt(case, 'B', MAPPING)
        request = read(folder / f'{stem}_request.json')
        assert {k:v for k,v in request.items() if k != 'prompt'} == dict(base.SETTINGS, n_predict=1, n_probs=VOCAB)
        response_path = folder / f'{stem}_response.json.gz'
        raw = gzip.decompress(response_path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == record['raw_response_sha256']
        response = json.loads(raw)
        assert not response['truncated']
        selection = base.select(response, VOCAB)
        rows.append(dict(id=ident, case=case, baseline=dict(prompt_path=str(prompt_path), request_path=str(folder / f'{stem}_request.json'),
            response_path=str(response_path), raw_sha256=record['raw_response_sha256'], selection=selection,
            timings=response['timings'], historical_elapsed_s=record['elapsed_s']),
            views={view: input_view(case, view) for view in ['premise', 'hypothesis']}))
    write(OUT / 'inputs.json', rows)
    write(OUT / 'criteria.json', dict(issue=650, ids=IDS, expected=dict(K01='supported', K02='unsupported', c13='supported',
        c46='supported', c47='unsupported', H02='contradicted', H03='unsupported', A02='unsupported', **{'NLC-C04':'unsupported'}),
        primary_gate='At least one original-score error corrected; every original-score correct label and normal/contradiction/missing-reference control preserved. Invalid/tied scores are not U.',
        followup='Only after gain and preservation: one frozen UCS mapping on these same cases for both original and TC scores; no all-permutation sweep.',
        formula='a * log((a*a + 1e-10)/(b*c + 1e-10)); a,b,c each normalized across same three options',
        ties='TC top score gap <=1e-12 is unresolved; numeric precision rule, not a confidence threshold',
        mapping=MAPPING, bias_inputs='Not product missing-evidence decisions; no gold assigned',
        new_primary_calls=18, reused_both_distributions=9, all_development_exposed=True))
    files = [OUT / 'inputs.json', OUT / 'criteria.json', OUT / 'official/receipts.json']
    files += [Path(r['baseline'][k]) for r in rows for k in ['prompt_path', 'request_path', 'response_path']]
    code = [Path(__file__), Path(base.__file__), ROOT / 'scripts/business_dependency_parser.py']
    write(OUT / 'prepared.json', dict(at=time.time(), base_commit='c79d1e05e6bcd8456a06b22f8e527dce90317251',
        files={str(p):sha(p) for p in files}, code={str(p):sha(p) for p in code}))


def check():
    prepared = read(OUT / 'prepared.json')
    assert all(sha(Path(p)) == h for p,h in {**prepared['files'], **prepared['code']}.items())


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check()
    props = base.api('/props')
    old = read(prior.OUT / 'baseline_props.json')
    assert {k:v for k,v in props.items() if k != 'media_marker'} == {k:v for k,v in old.items() if k != 'media_marker'}
    requests = []
    for row in read(OUT / 'inputs.json'):
        case = row['case']
        both_ids = base.api('/tokenize', dict(content=base.prompt(case, 'B', MAPPING), add_special=False, parse_special=True))['tokens']
        assert both_ids == read(Path(row['baseline']['request_path']))['prompt']
        for view, masked in row['views'].items():
            prompt = base.prompt(masked, 'B', MAPPING)
            assert all(marker not in prompt for marker in [props['media_marker'], old['media_marker']])
            tokens = base.api('/tokenize', dict(content=prompt, add_special=False, parse_special=True))['tokens']
            for code, token in base.TOKENS.items():
                assert base.api('/tokenize', dict(content=prompt+code, add_special=False, parse_special=True))['tokens'] == tokens + [token]
            assert len(tokens) + 1 < 8192
            requests.append(dict(id=row['id'], view=view, prompt=prompt, input_tokens=len(tokens),
                                 request=dict(base.SETTINGS, prompt=tokens, n_predict=1, n_probs=VOCAB)))
    write(OUT / 'requests.json', requests); write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), max_calls=18, files={n:sha(OUT/n) for n in ['prepared.json','requests.json','props.json']},
                                  official_revision='1159a5be1777c5c43933340697512f3a188fcf4a'))
    print('Frozen TC requests:', len(requests), 'input tokens:', sum(r['input_tokens'] for r in requests))


def run():
    check()
    assert all(sha(OUT/n) == h for n,h in read(OUT/'freeze.json')['files'].items())
    assert base.api('/props') == read(OUT/'props.json')
    dest = OUT/'run'; dest.mkdir()
    result = dict(calls=0, records=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT/'requests.json'):
        record = dict(id=row['id'], view=row['view'], input_tokens=row['input_tokens'])
        result['records'].append(record); result['calls'] += 1
        write(dest/'result.json',result)
        before = time.monotonic()
        try:
            raw = base.call('/completion',row['request'])
            path = dest/f"{row['id']}_{row['view']}_response.json.gz"
            with gzip.open(path,'wb',compresslevel=1) as stream: stream.write(raw)
            response = json.loads(raw)
            record.update(raw_sha256=hashlib.sha256(raw).hexdigest(), gzip_sha256=sha(path), timings=response.get('timings'),
                          truncated=response.get('truncated'), stop_type=response.get('stop_type'))
            if response.get('truncated'): raise ValueError('input_truncated')
            record['selection'] = base.select(response,VOCAB,allow_ties=True)
            record['status'] = 'completed'
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(status='failed', error=repr(error))
        record['elapsed_s'] = time.monotonic()-before
        result['wall_s'] = time.monotonic()-start
        write(dest/'result.json',result)
        print(row['id'],row['view'],record['status'],flush=True)
    indexed = {(r['id'],r['view']):r for r in result['records']}
    comparisons = []
    for row in read(OUT/'inputs.json'):
        original = row['baseline']['selection']
        item = dict(id=row['id'], original_label=MAPPING[original['code']], tc_label=None)
        try:
            calibrated = calibrate(original['option_logprobs'],*[indexed[row['id'],v]['selection']['option_logprobs'] for v in ['premise','hypothesis']])
            item.update(calibrated=calibrated,tc_label=MAPPING.get(calibrated['code']))
        except (ValueError,KeyError,TypeError) as error:item['error']=repr(error)
        comparisons.append(item)
    write(OUT/'comparison.json',comparisons)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['selfcheck','prepare','preflight','run'])
    globals()[cli.parse_args().mode]()
