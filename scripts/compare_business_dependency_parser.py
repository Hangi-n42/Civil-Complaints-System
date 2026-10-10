"""Six frozen paired calls at 12288 context; unchanged #643 task plus parser data."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

import business_dependency_parser as parser
import compare_business_direct_structure as old

OUT, ROOT = parser.OUT, parser.ROOT
read, write, sha = old.read, old.write, old.sha
prior = old.prior
IDS = ['c47', 'c13', 'c46']
BOUNDARY = ('자동 통사 분석이며 업무 조건·의무의 의미 정답이 아니다. 기존 원문·부모·제목·필드 관계를 함께 읽는다. '
            '원문 블록/후보 필드를 각각 분석했고 그 사이의 의존 연결은 생성하지 않았다. '
            'head=0은 sentence의 통사 root, 나머지는 같은 sentence word id다. '
            '주소는 각 원형 문자열의 반열린 문자 위치다. lemma는 원문 주소가 아니다. '
            'shared_token_word_tsv는 Token과 Word가 표면·주소·id까지 1:1인 경우만 공유한 무손실 표다. '
            '각 행의 id/token_index는 1부터 행순서, feats는 명시된 공통값이다. '
            '열은 start,end,text,lemma,upos,xpos,head,deprel이며 탭으로 구분한다. '
            'separate는 별개 token/word 배열이고 exact_span=null은 주소 대응 실패다. '
            'uncovered는 토큰이 덮지 않은 원문이며 공백 여부를 따로 기록한다.')


def prepare():
    assert not (OUT / 'prepared.json').exists()
    old.check()
    parser.selfcheck()
    records = read(OUT / 'parsed.json')
    encoded = [parser.compact(r) for r in records]
    for record, value in zip(records, encoded):
        for original, sentence in zip(record['mapped']['sentences'], value['sentences']):
            assert parser.expand_sentence(sentence) == (original['tokens'], original['words'])
        assert record['mapped']['uncovered'] == value['uncovered']
    saved = read(old.OUT / 'run/judgment_requests.json')
    results = read(old.OUT / 'run/result.json')['records']
    rows, baselines = [], []
    for ident in IDS:
        base = next(r for r in saved if r['id'] == ident and r['task'] == 'plain')
        response = next(r for r in results if r['id'] == ident and r['task'] == 'plain')
        raw = old.OUT / 'run' / (ident + '_plain_response.json')
        assert sha(raw) == response['raw_sha256']
        prefix, user = base['prompt'].split('<|im_start|>user\n')
        original, suffix = user.split('<|im_end|>', 1)
        field = dict(parser='Stanza 1.15.0 ko kaist_nocharlm', semantic_status='unverified',
                     format=BOUNDARY, documents=[r for r in encoded if r['address']['kind'] == 'source'
                                                or r['address'].get('case_id') == ident])
        assert original.endswith('}')
        changed = original[:-1] + ', "independent_dependency_parse":' + json.dumps(field, ensure_ascii=False, separators=(',', ':')) + '}'
        decoded = json.loads(changed)
        assert decoded.pop('independent_dependency_parse') == field and decoded == json.loads(original)
        prompt = prefix + '<|im_start|>user\n' + changed + '<|im_end|>' + suffix
        rows.append(dict(id=ident, task='dependency', prompt=prompt))
        baselines.append(dict(**base, response=response, raw_path=str(raw.relative_to(ROOT))))
    write(OUT / 'baselines.json', baselines)
    rows = [dict(id=r['id'], task='plain', prompt=r['prompt']) for r in baselines] + rows
    write(OUT / 'prompts.json', rows)
    write(OUT / 'criteria.json', dict(expected={i: read(old.OUT / 'criteria.json')['expected'][i] for i in IDS},
          reason_rubric={i: read(old.OUT / 'criteria.json')['rubric'][i] for i in IDS},
          gates=['All three are development exposed; no general performance claim.',
                 'Require actual c47 scope-error detection and preservation of c13/c46.',
                 'Read evidence, error span, reason and source_state; label alone is insufficient.',
                 'No repaired parsing, no new judge, no retries, no calculator, six calls: new A3/B3.',
                 'Failures and unresolved cases remain in denominator.']))
    write(OUT / 'exposure.json', dict(development_cases=IDS,
          already_exposed=['K01', 'K02', 'NLC-C04', 'NLC-C05', 'A02', 'SL-01', 'SL-02', 'SL-03',
                           'AR01-AR03', 'BI01-BI04', 'KR01-KR04'],
          unused_confirmation_cases_in_this_run=[],
          decision='No new confirmation authored before development comparison; only consider after meaningful effect.',
          evidence_files=[str(p.relative_to(ROOT)) for p in (ROOT / 'data/knowledge/evaluations').glob('*/confirmation*/inputs.json')]))
    write(OUT / 'prepared.json', dict(at=time.time(), max_calls=6, context=12288,
          code={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'scripts/business_dependency_parser.py']},
          files={n: sha(OUT / n) for n in ['parsed.json', 'parser_config.json', 'model_files.json',
                 'baselines.json', 'prompts.json', 'criteria.json', 'exposure.json', 'execution_authorization.json']}))


def check():
    old.check()
    frozen = read(OUT / 'prepared.json')
    assert all(sha(ROOT / n) == h for n, h in frozen['code'].items())
    assert all(sha(OUT / n) == h for n, h in frozen['files'].items())


def preflight():
    assert not (OUT / 'freeze.json').exists()
    check()
    assert read(OUT / 'execution_authorization.json')['compute_allocated']
    identity = read(prior.previous.OUT / 'runtime_identity.json')
    for key in ['engine', 'gguf']:
        assert sha(Path(identity[key + '_path'])) == identity[key + '_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models']
    props = prior.previous.prior.base.api('/props')
    old_props = read(old.OUT / 'props.json')
    write(OUT / 'runtime_comparison.json', dict(previous=old_props, current=props,
          declared_change='Context 8192 to 12288 for both new arms; engine/GGUF/sampling/output reserve unchanged.'))
    for base in read(OUT / 'baselines.json'):
        recreated = prior.request_row(dict(id=base['id'], prompt=base['prompt']))
        assert recreated['request'] == base['request'] and recreated['input_tokens'] == base['input_tokens']
    requests = []
    settings = read(prior.OUT / 'settings.json')
    for row in read(OUT / 'prompts.json'):
        ids = prior.previous.prior.base.api('/tokenize', dict(content=row['prompt'], add_special=False, parse_special=True))['tokens']
        if len(ids) + settings['n_predict'] >= 12288:
            raise ValueError('context_budget:' + str(len(ids)))
        requests.append(dict(row, input_tokens=len(ids), request=dict(settings, prompt=ids)))
    write(OUT / 'requests.json', requests)
    write(OUT / 'props.json', props)
    write(OUT / 'freeze.json', dict(at=time.time(), max_calls=6, context=12288,
          files={n: sha(OUT / n) for n in ['prepared.json', 'requests.json', 'props.json', 'runtime_comparison.json']},
          runtime_identity=identity, baseline_reuse=False, exact_old_A_requests_rerun_at_new_context=True))
    print([(r['id'], r['task'], r['input_tokens'], r['request']['n_predict']) for r in requests], flush=True)


def run():
    check()
    assert all(sha(OUT / n) == h for n, h in read(OUT / 'freeze.json')['files'].items())
    assert prior.previous.prior.base.api('/props') == read(OUT / 'props.json')
    dest = OUT / 'run'
    dest.mkdir()
    cases = {c['id']: c for c in read(old.OUT / 'inputs.json')}
    result = dict(calls=0, records=[], semantic_review='pending')
    start = time.monotonic()
    for row in read(OUT / 'requests.json'):
        record = dict(id=row['id'], task=row['task'], input_tokens=row['input_tokens'], contract_pass=False)
        result['records'].append(record)
        result['calls'] += 1
        assert result['calls'] <= 6
        write(dest / 'result.json', result)
        before = time.monotonic()
        try:
            raw = prior.previous.prior.base.call('/completion', row['request'])
            path = dest / (row['id'] + '_' + row['task'] + '_response.json')
            path.write_bytes(raw)
            response = json.loads(raw)
            record.update(raw_sha256=sha(path), timings=response.get('timings'),
                          stop_type=response.get('stop_type'), truncated=response.get('truncated'))
            if response.get('stop_type') != 'eos' or response.get('truncated'):
                raise ValueError('incomplete_generation')
            answer = json.loads('{' + response['content'], object_pairs_hook=prior.previous.strict_object)
            record['answer'] = answer
            record['parsed'] = prior.previous.parse_final(answer, cases[row['id']])
            record['label'] = prior.previous.prior.MAPPING[answer['label']]
            record['contract_pass'] = True
        except (OSError, ValueError, KeyError, TypeError) as error:
            record['error'] = repr(error)
        record['elapsed_s'] = time.monotonic() - before
        result['wall_s'] = time.monotonic() - start
        write(dest / 'result.json', result)
        print(row['id'], row['task'], record['contract_pass'], record.get('label'), record.get('error'), flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare', 'preflight', 'run', 'check'])
    globals()[cli.parse_args().mode]()
