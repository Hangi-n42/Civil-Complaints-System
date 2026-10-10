"""Probe supplied-token probabilities using unchanged native full-vocabulary output."""
import gzip
import json
import math
from pathlib import Path
import time

import compare_business_selected_source as selection

api = selection.prior.previous.prior.base
OUT = selection.OUT.parent / 'b_probe/http_v2'
TEXT = '토큰 검사: 가 나 다 731.'


def normalize(response, target, vocab=248320, sampled_id=None):
    values = response['completion_probabilities'][0]['top_logprobs']
    scores = {row['id']: row['logprob'] for row in values}
    assert len(values) == len(scores) == vocab and set(scores) == set(range(vocab))
    assert all(math.isfinite(v) for v in scores.values())
    assert len(response['completion_probabilities']) == len(response['tokens']) == 1
    peak = max(scores.values())
    log_mass = peak + math.log(math.fsum(math.exp(v-peak) for v in scores.values()))
    greedy = max(scores, key=scores.get)
    assert response['tokens'][0] == (greedy if sampled_id is None else sampled_id)
    return dict(target_id=target, greedy_id=greedy, non_greedy=target != greedy,
                raw_logprob=scores[target], raw_log_mass=log_mass, raw_mass=math.exp(log_mass),
                normalized_logprob=scores[target]-log_mass,
                normalized_mass=math.fsum(math.exp(v-log_mass) for v in scores.values()),
                vocabulary=vocab, full_unique_coverage=True, finite=True)


def main():
    assert not OUT.exists()
    OUT.mkdir()
    tokenized = api.api('/tokenize', dict(content=TEXT, add_special=True, parse_special=True))
    plain = api.api('/tokenize', dict(content=TEXT, add_special=False, parse_special=True))
    ids = tokenized['tokens']
    assert len(ids) > 6
    settings = dict(selection.read(selection.prior.OUT/'settings.json'), n_predict=1, n_probs=248320)
    assert api.api('/detokenize', dict(tokens=ids))['content'] == TEXT
    assert api.api('/tokenize', dict(content='1', add_special=False, parse_special=True))['tokens'] == [16]
    requests = [dict(position=i, variant=variant, target_id=ids[i], request=dict(settings, prompt=ids[:i],
                     **({'logit_bias':[[16,1000]]} if variant == 'sentinel' else {})))
                for i, variant in [(5,'unbiased'),(5,'sentinel'),(11,'unbiased'),(11,'sentinel')]
                + [(i,'sentinel') for i in [1,2,3,4,6]]]
    selection.write(OUT/'freeze.json', dict(at=time.time(), text=TEXT, token_ids=ids,
          tokenization=tokenized, without_auto_special=plain, requests=requests,
          script_sha256=selection.sha(Path(__file__)),
          semantics='Six supplied target positions plus two fixed control prefixes. All prefixes are exact original IDs, never sampled output. Sentinel16 only makes generated text complete UTF-8; target probabilities are read from full pre-sampling vocabulary. Raw natural text, no ChatML. Double logsumexp renormalization, not raw-logit access.',
          criterion='At least two non-greedy supplied targets at positions1..6, exact prefix/target identity, full finite unique vocabulary, normalized mass tolerance1e-12. All-vocabulary sentinel/unbiased control difference tolerance1e-6 nats fixed before output; not semantic evaluation.'))
    result = dict(records=[], calls=0)
    started = time.monotonic()
    for row in requests:
        result['calls'] += 1
        selection.write(OUT/'result.json', result)
        before = time.monotonic()
        raw = api.call('/completion', row['request'])
        path = OUT/(str(row['position'])+'_'+row['variant']+'_response.json.gz')
        path.write_bytes(gzip.compress(raw, mtime=0))
        response = json.loads(raw)
        assert not response['truncated'] and response['timings']['prompt_n'] == len(row['request']['prompt'])
        record = dict(row, **normalize(response, row['target_id'], sampled_id=16 if row['variant']=='sentinel' else None), raw_sha256=selection.prior.text_hash(raw.decode()),
                      gzip_sha256=selection.sha(path), raw_bytes=len(raw), gzip_bytes=path.stat().st_size,
                      timings=response['timings'], stop_type=response['stop_type'], elapsed_s=time.monotonic()-before)
        result['records'].append(record)
        result['wall_s'] = time.monotonic()-started
        selection.write(OUT/'result.json', result)
        print(row['position'], record['target_id'], record['greedy_id'], record['normalized_logprob'], flush=True)
    result['controls'] = []
    for position in [5, 11]:
        distributions = []
        for variant in ['unbiased','sentinel']:
            response = json.loads(gzip.decompress((OUT/(str(position)+'_'+variant+'_response.json.gz')).read_bytes()))
            distributions.append({r['id']:r['logprob'] for r in response['completion_probabilities'][0]['top_logprobs']})
        difference = max(abs(distributions[0][i]-distributions[1][i]) for i in distributions[0])
        result['controls'].append(dict(position=position, full_vocabulary_max_abs_logprob_difference=difference,
                                       tolerance=1e-6, passed=difference<=1e-6))
    result['technical_gate'] = (sum(r['non_greedy'] for r in result['records']
                                    if r['position']<=6 and r['variant']=='sentinel') >= 2
                                and all(r['passed'] for r in result['controls']))
    assert all(abs(r['normalized_mass']-1) < 1e-12 for r in result['records'])
    selection.write(OUT/'result.json', result)


if __name__ == '__main__':
    main()
