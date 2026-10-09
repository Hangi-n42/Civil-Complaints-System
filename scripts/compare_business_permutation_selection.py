"""One frozen six-mapping mean-logprob diagnostic; never writes product state."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import time

import compare_business_label_selection as base
from compare_business_nli import read, write, sha

ROOT=base.ROOT
OLD=base.OUT
OUT=OLD.parent/'business_permutation_selection_20261009'
LABELS=('supported','unsupported','contradicted')
MAPPINGS={''.join(v[0].upper() for v in values):dict(zip(base.TOKENS,values))
          for values in itertools.permutations(LABELS)}
REUSED={'SUC':'primary','UCS':'rotation'}
TOLERANCE=1e-12


def aggregate(rows):
    if len(rows)!=6 or {r['mapping'] for r in rows}!=set(MAPPINGS):
        return dict(label=None,status='unresolved',error='missing_or_duplicate_mapping')
    if any(r.get('status')!='completed' for r in rows):
        return dict(label=None,status='unresolved',error='invalid_mapping_response')
    contributions={label:[] for label in LABELS}
    for row in rows:
        scores=row.get('selection',{}).get('option_logprobs',{})
        if set(scores)!=set(base.TOKENS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in scores.values()):
            return dict(label=None,status='unresolved',error='invalid_scores')
        for code,label in MAPPINGS[row['mapping']].items():contributions[label].append(scores[code])
    means={label:math.fsum(values)/6 for label,values in contributions.items()}
    ranked=sorted(means,key=means.get,reverse=True);margin=means[ranked[0]]-means[ranked[1]]
    return dict(label=ranked[0] if margin>TOLERANCE else None,
                status='completed' if margin>TOLERANCE else 'unresolved',
                mean_logprobs=means,margin=margin,contributions=contributions,correctness_probability=False)


def gate(cases,criteria,confirmation=False):
    indexed={r['id']:r for r in cases};expected=criteria['expected']
    correct=[id for id,label in expected.items() if label is not None and indexed.get(id,{}).get('label')==label]
    unresolved=[id for id in expected if indexed.get(id,{}).get('label') is None]
    complete=set(indexed)==set(expected)
    protected=list(expected) if confirmation else criteria['protected']
    damaged=[id for id in protected if id not in correct]
    gains=[] if confirmation else [id for id in criteria['both_A_wrong'] if id in correct]
    return dict(correct=correct,denominator=sum(v is not None for v in expected.values()),
                unresolved=unresolved,damaged_protected=damaged,gains=gains,complete=complete,
                passed=complete and not damaged and (confirmation or bool(gains)))


def verify_reuse():
    import numpy as np
    frozen=read(OLD/'freeze.json');inputs=read(OLD/'inputs.json');records=[]
    assert all(sha(OLD/n)==h for n,h in frozen['files'].items())
    for key,phase in REUSED.items():
        result=read(OLD/phase/'result.json');assert result['complete']
        existing={r['id']:r for r in result['cases'] if r['arm']=='B'}
        preflight={r['id']:r for r in read(OLD/phase/'preflight.json') if r['arm']=='B'}
        for case in inputs:
            id=case['id'];row=existing[id];stem=f'{id}_B';folder=OLD/phase
            assert (OLD/'prompts'/f'{phase}_{stem}.txt').read_text()==base.prompt(case,'B',MAPPINGS[key])
            request=read(folder/f'{stem}_request.json')
            assert request==dict(base.SETTINGS,prompt=preflight[id]['tokens'],n_predict=1,n_probs=frozen['B_vocab'])
            path=folder/f'{stem}_response.json.gz';assert sha(path)==row['gzip_sha256']
            with gzip.open(path,'rb') as stream:raw=stream.read()
            assert hashlib.sha256(raw).hexdigest()==row['raw_response_sha256']
            response=json.loads(raw);assert not response['truncated'] and row['status']=='completed'
            selection=base.select(response,frozen['B_vocab'],allow_ties=True)
            assert {k:v for k,v in selection.items() if k!='option_tie'}==row['selection']
            npz=OLD/row['distribution_path'];assert sha(npz)==row['distribution_sha256']
            values=np.load(npz)
            assert values['ids'].tolist()==[v['id'] for v in response['completion_probabilities'][0]['top_logprobs']]
            assert values['logprobs'].tolist()==[v['logprob'] for v in response['completion_probabilities'][0]['top_logprobs']]
            records.append(dict(id=id,mapping=key,status='completed',selection=selection,reused=True,
                response_path=str(path.relative_to(ROOT)),gzip_sha256=sha(path),raw_response_sha256=row['raw_response_sha256'],
                request_path=str((folder/f'{stem}_request.json').relative_to(ROOT)),request_sha256=sha(folder/f'{stem}_request.json'),
                original_timing=row['timings'],original_elapsed_s=row['elapsed_s']))
    write(OUT/'reuse.json',dict(records=records,verified_responses=len(records),formula_not_applied=True))


def freeze():
    assert not (OUT/'freeze.json').exists()
    old=read(OLD/'freeze.json');inputs=read(OLD/'inputs.json');expected=read(OLD/'criteria.json')['expected']
    reviews=[read(OLD/n) for n in ['source_output_review.json','rotation_source_output_review.json']]
    protected=[id for id,label in expected.items() if label is not None and any(next(c for c in r['cases'] if c['id']==id)['semantic_label']==label for r in reviews)]
    assert set(protected)=={'c13','c46','c11','H01','H02','H04','H05','H06','H08','A01','A02','K01'}
    write(OUT/'inputs.json',inputs);write(OUT/'confirmation_inputs.json',read(OLD/'confirmation_inputs.json'))
    write(OUT/'criteria.json',dict(expected=expected,protected=protected,both_A_wrong=['c47','H03','K02'],ambiguity=['H07'],
        gate='Preserve all 12 cases correct in either old A; fix at least one of c47/H03/K02. Unresolved remains in denominator.',
        confirmation_expected=read(OLD/'confirmation_materials/reconciliation.json')['expected'],
        confirmation_gate='Only if development passes: A6 plus B36; require aggregate B6/6. A6/6 is no extra superiority evidence.',not_model_input=True))
    (OUT/'prompts').mkdir()
    for phase,cases in [('development',inputs),('confirmation',read(OUT/'confirmation_inputs.json'))]:
        for case in cases:
            for key,mapping in MAPPINGS.items():(OUT/'prompts'/f"{phase}_{case['id']}_{key}_B.txt").write_text(base.prompt(case,'B',mapping))
            if phase=='confirmation':(OUT/'prompts'/f"{phase}_{case['id']}_SUC_A.txt").write_text(base.prompt(case,'A',MAPPINGS['SUC']))
    own=[p for p in OUT.iterdir() if p.is_file()]+sorted((OUT/'prompts').glob('*.txt'))
    old_files=[OLD/n for n in ['freeze.json','runtime_identity.json','source_output_review.json','rotation_source_output_review.json','confirmation_materials/reconciliation.json','confirmation_materials/cases_blind.json']]
    write(OUT/'freeze.json',dict(issue=633,baseline_head='57fcad9bf41c2e194e9a8c47fa04897fa6e878a5',created_at=time.time(),
        mappings=MAPPINGS,reused=REUSED,formula='L(y)=fsum(logp(code_for_y|mapping) for all six mappings)/6; argmax only',
        tolerance=TOLERANCE,tolerance_kind='absolute nats, relative 0; not semantic confidence threshold',
        invalid='Invalid/missing/truncated distribution or aggregate margin<=tolerance is unresolved; per-mapping ties remain valid contributions and are recorded.',
        settings=base.SETTINGS,engine_argv=old['engine_argv'],context_tokens=old['context_tokens'],B_vocab=old['B_vocab'],
        extra_call_limits=dict(development=64,confirmation_A=6,confirmation_B=36,total=106),
        files={str(p.relative_to(ROOT)):sha(p) for p in own+old_files},
        code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(base.__file__),Path(base.__file__).with_name('compare_business_nli.py')]}))


def run(phase):
    frozen=read(OUT/'freeze.json');identity=read(OLD/'runtime_identity.json')
    assert all(sha(ROOT/n)==h for n,h in {**frozen['files'],**frozen['code']}.items())
    assert sha(Path(identity['engine_path']))==identity['engine_sha256'] and sha(Path(identity['gguf_path']))==identity['gguf_sha256']
    approval=read(OUT/f'{phase}_authorization.json');assert approval['freeze_sha256']==sha(OUT/'freeze.json') and approval['coordinator_authorized']
    if phase=='confirmation':
        development=read(OUT/'development/result.json');assert development['complete'] and development['gate']['passed']
    folder=OUT/phase;folder.mkdir();write(folder/'props.json',base.api('/props'))
    cases=read(OUT/('inputs.json' if phase=='development' else 'confirmation_inputs.json'))
    criteria=read(OUT/'criteria.json');jobs=[];preflight=[]
    for case in cases:
        keys=[k for k in MAPPINGS if phase!='development' or k not in REUSED]
        specs=[(k,'B') for k in keys]+([('SUC','A')] if phase=='confirmation' else [])
        for key,arm in specs:
            stem=f"{case['id']}_{key}_{arm}";text=(OUT/'prompts'/f'{phase}_{stem}.txt').read_text()
            tokens=base.api('/tokenize',dict(content=text,add_special=False,parse_special=True))['tokens']
            for code,token in base.TOKENS.items():
                assert base.api('/tokenize',dict(content=text+code,add_special=False,parse_special=True))['tokens']==tokens+[token]
                assert base.api('/detokenize',dict(tokens=[token]))['content']==code
            assert len(tokens)+2048<frozen['context_tokens']
            jobs.append((case,key,arm,tokens));preflight.append(dict(id=case['id'],mapping=key,arm=arm,prompt_tokens=len(tokens)))
    write(folder/'preflight.json',preflight);write(folder/'started.json',dict(at=time.time(),freeze_sha256=sha(OUT/'freeze.json'),calls_planned=len(jobs)))
    rows=list(read(OUT/'reuse.json')['records']) if phase=='development' else [];a_rows=[]
    for case,key,arm,tokens in jobs:
        stem=f"{case['id']}_{key}_{arm}";record=dict(id=case['id'],mapping=key,arm=arm,reused=False);start=time.monotonic()
        request=dict(base.SETTINGS,prompt=tokens,n_predict=1 if arm=='B' else 2048,n_probs=frozen['B_vocab'] if arm=='B' else 0)
        write(folder/f'{stem}_request.json',request)
        try:
            raw=base.call('/completion',request)
            path=folder/(stem+'_response.json'+('.gz' if arm=='B' else ''))
            with (gzip.open(path,'wb',compresslevel=1) if arm=='B' else path.open('wb')) as stream:stream.write(raw)
            record.update(raw_response_sha256=hashlib.sha256(raw).hexdigest(),response_path=str(path.relative_to(ROOT)),stored_sha256=sha(path))
            response=json.loads(raw);record.update(timings=response.get('timings'),truncated=response.get('truncated'),stop_type=response.get('stop_type'))
            if response.get('truncated') or (arm=='A' and response.get('stop_type')=='limit'):raise ValueError('generation_incomplete')
            if arm=='B':record['selection']=base.select(response,frozen['B_vocab'],allow_ties=True)
            else:
                answer=json.loads(base.PREFIX+response['content']);label=answer.get('label')
                record['explicit_label']=label;record['semantic_label']=MAPPINGS[key].get(label,label if label in LABELS else None)
                record['answer']=answer
                try:base.parse_a(response['content'],case,MAPPINGS[key]);record['contract_pass']=True
                except (ValueError,KeyError,TypeError) as exc:record.update(contract_pass=False,contract_error=str(exc))
            record['status']='completed'
        except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:record.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        record['elapsed_s']=time.monotonic()-start
        (rows if arm=='B' else a_rows).append(record)
        aggregated=[dict(id=c['id'],**aggregate([r for r in rows if r['id']==c['id']])) for c in cases]
        criterion=criteria if phase=='development' else dict(expected=criteria['confirmation_expected'])
        new_calls=sum(not r.get('reused') for r in rows)+len(a_rows);complete=new_calls==len(jobs)
        verdict=gate(aggregated,criterion,phase=='confirmation');verdict['passed'] &= complete
        write(folder/'result.json',dict(phase=phase,rows=rows,A_rows=a_rows,cases=aggregated,
            gate=verdict,new_calls=new_calls,complete=complete))
        print(json.dumps({k:v for k,v in record.items() if k not in ['selection','answer']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['reuse','freeze','development','confirmation']);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.mode=='reuse':verify_reuse()
    elif args.mode=='freeze':freeze()
    else:run(args.mode)
