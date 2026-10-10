"""Independent implementation of Wu et al. (2024), official repository score.

E = log p(x + ' ' + y) - log p(x + EOS) - log p(y + ' ' + y) + log p(y + EOS).
https://github.com/ZhaofengWu/entailment-from-lm/tree/58ed848cc744f645b17c2f062d2a6f0c54650951
Only exactly identical token-prefix terms cancel. Full source remains in context.
"""
import argparse
import gzip
import json
import math
from pathlib import Path
import time

import probe_business_sentence_probability as probe

s = probe.selection
OUT = s.OUT.parent/'b_semantic'


def terms_for(tokens):
    terms, cancellation, prefixes = [], [], {}
    for positive, negative in [('xy','x_eos'),('y_eos','yy')]:
        a,b = tokens[positive],tokens[negative]
        n=0
        while n<min(len(a),len(b)) and a[n]==b[n]:
            n+=1
        cancellation.append(dict(positive=positive,negative=negative,lcp_tokens=n,
                                 cancelled_scored_positions=max(n-1,0)))
        for name,sign in [(positive,1),(negative,-1)]:
            for position in range(max(n,1),len(tokens[name])):
                prefix=tokens[name][:position]
                key=s.prior.text_hash(json.dumps(prefix,separators=(',',':')))
                if key in prefixes:
                    assert prefixes[key]['tokens']==prefix
                else:
                    prefixes[key]=dict(tokens=prefix,targets=[])
                target=tokens[name][position]
                if target not in prefixes[key]['targets']:
                    prefixes[key]['targets'].append(target)
                terms.append(dict(sequence=name,position=position,prefix_key=key,target_id=target,coefficient=sign))
    return terms,cancellation,prefixes


def selfcheck():
    # Unequal tokenization at a concatenation boundary must not cancel by character length.
    tokens=dict(xy=[1,2,30,4],x_eos=[1,2,3,9],yy=[7,8,70,8],y_eos=[7,8,9])
    terms,cancellation,prefixes=terms_for(tokens)
    assert [r['lcp_tokens'] for r in cancellation]==[2,2]
    def value(prefix,target):
        return -math.log(1+sum((i+1)*t for i,t in enumerate(prefix))+target)
    full=sum(sign*sum(value(ids[:i],ids[i]) for i in range(1,len(ids)))
             for name,sign in [('xy',1),('x_eos',-1),('yy',-1),('y_eos',1)] for ids in [tokens[name]])
    reduced=sum(t['coefficient']*value(prefixes[t['prefix_key']]['tokens'],t['target_id']) for t in terms)
    assert math.isclose(full,reduced,abs_tol=1e-12)
    plan=s.read(OUT/'token_plan.json')
    merged={}
    for row in plan['inputs']:
        terms,cancellation,prefixes=terms_for(row['tokens'])
        assert terms==row['terms'] and cancellation==row['cancellation']
        for key,prefix in prefixes.items():
            if key not in merged:
                merged[key]=prefix
            else:
                assert merged[key]['tokens']==prefix['tokens']
                for target in prefix['targets']:
                    if target not in merged[key]['targets']:
                        merged[key]['targets'].append(target)
    assert merged==plan['prefixes'] and len(merged)==585
    print('Exact prefix cancellation matches four complete sums, boundary divergence retained; all frozen terms and prefix targets rebuilt.')


def freeze():
    assert not (OUT/'freeze.json').exists()
    s.check_prepared()
    selfcheck()
    props=probe.api.api('/props')
    for row in s.read(OUT/'token_plan.json')['inputs']:
        x,y=row['x'],row['y']
        texts=dict(xy=x+' '+y,x_eos=x+props['eos_token'],yy=y+' '+y,y_eos=y+props['eos_token'])
        for name,text in texts.items():
            for add_special in [True,False]:
                assert probe.api.api('/tokenize',dict(content=text,add_special=add_special,parse_special=True))['tokens']==row['tokens'][name]
    settings=dict(s.read(s.prior.OUT/'settings.json'),n_predict=1,n_probs=248320,logit_bias=[[16,1000]])
    s.write(OUT/'settings.json',settings)
    s.write(OUT/'props.json',props)
    s.write(OUT/'freeze.json',dict(at=time.time(),max_calls=585,
          code={str(Path(__file__).relative_to(s.ROOT)):s.sha(Path(__file__)),
                str(Path(probe.__file__).relative_to(s.ROOT)):s.sha(Path(probe.__file__))},
          files={n:s.sha(OUT/n) for n in ['token_plan.json','input_identity.json','criteria.json','settings.json','props.json','execution_authorization.json']},
          technical_probe_freeze_sha256=s.sha(probe.OUT/'freeze.json'),
          formula='logp(x SPACE y)-logp(x EOS)-logp(y SPACE y)+logp(y EOS)',
          scoring='All terms exclude first token and sum without length averaging; score direction larger=support. Whole structured source JSON; no ChatML. Only exact token-LCP cancellation; no four full logp claim. Native float pre-sampling probabilities are double-renormalized per full vocabulary.',
          retention='Full vocabulary gzip local only; hashes and target scores may be published.'))


def run():
    s.check_prepared()
    freeze=s.read(OUT/'freeze.json')
    assert all(s.sha(OUT/n)==h for n,h in freeze['files'].items())
    assert all(s.sha(s.ROOT/n)==h for n,h in freeze['code'].items())
    assert probe.api.api('/props')==s.read(OUT/'props.json')
    assert s.read(OUT/'execution_authorization.json')['compute_allocated']
    plan=s.read(OUT/'token_plan.json')
    dest=OUT/'run'
    dest.mkdir()
    result=dict(calls=0,records=[],semantic_assessment='pending')
    started=time.monotonic()
    for key,prefix in plan['prefixes'].items():
        result['calls']+=1
        assert result['calls']<=freeze['max_calls']
        record=dict(prefix_key=key,input_tokens=len(prefix['tokens']),status='started')
        result['records'].append(record)
        s.write(dest/'result.json',result)
        before=time.monotonic()
        request=dict(s.read(OUT/'settings.json'),prompt=prefix['tokens'])
        raw=probe.api.call('/completion',request)
        path=dest/(key+'.json.gz')
        path.write_bytes(gzip.compress(raw,mtime=0))
        record.update(raw_sha256=s.prior.text_hash(raw.decode()),gzip_sha256=s.sha(path),
                      raw_bytes=len(raw),gzip_bytes=path.stat().st_size)
        s.write(dest/'result.json',result)
        response=json.loads(raw)
        assert not response['truncated'] and response['timings']['prompt_n']==len(prefix['tokens'])
        scores=[probe.normalize(response,target,sampled_id=16) for target in prefix['targets']]
        assert all(abs(r['normalized_mass']-1)<1e-12 for r in scores)
        record.update(status='completed',targets=scores,timings=response['timings'],stop_type=response['stop_type'],
                      elapsed_s=time.monotonic()-before)
        result['wall_s']=time.monotonic()-started
        s.write(dest/'result.json',result)
        print(result['calls'],len(prefix['tokens']),key[:12],record['elapsed_s'],flush=True)
    scores={(r['prefix_key'],t['target_id']):t['normalized_logprob'] for r in result['records'] for t in r['targets']}
    result['case_scores']=[dict(id=row['id'],E=math.fsum(t['coefficient']*scores[t['prefix_key'],t['target_id']] for t in row['terms'])) for row in plan['inputs']]
    result['wall_s']=time.monotonic()-started
    s.write(dest/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['selfcheck','freeze','run'])
    globals()[parser.parse_args().mode]()
