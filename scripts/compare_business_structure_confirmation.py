"""Separate-source paired confirmation; frozen direct selection and judge instructions."""
import argparse
import json
from pathlib import Path
import time

import compare_business_direct_structure as original
import business_direct_source_inputs as adapter

prior,ROOT,read,write,sha=original.prior,original.ROOT,original.read,original.write,original.sha
OUT=original.OUT/'confirmation'


def prompt(case,spans,structure=None):
    payload=dict(case)
    if structure is not None:payload['physical_structure']=structure
    text=adapter.selection.prompt(payload,spans)
    marker='<|im_end|>\n<|im_start|>user'
    text=text.replace(marker,'\n'+adapter.STRUCTURE_BOUNDARY+marker,1)
    left,body=text.split('<|im_start|>user\n');old,right=body.split('<|im_end|>',1)
    compact=json.dumps(json.loads(old),ensure_ascii=False,separators=(',',':'))
    assert json.loads(compact)==json.loads(old)
    return left+'<|im_start|>user\n'+compact+'<|im_end|>'+right


def prepare():
    assert not (OUT/'prepared.json').exists()
    original.check()
    blind=read(OUT/'author_cases_blind.json')
    source=(OUT/'source.txt').read_text()
    cases=[dict(id=c['id'],raw=c['raw'],blocks=[dict(id='seoul-bike-33719',text=source)],
                source=dict(url=read(OUT/'source_receipt.json')['url'])) for c in blind]
    assert len({c['id'] for c in cases})==len(cases)
    assert set(read(OUT/'criteria.json')['expected'])=={c['id'] for c in cases}
    block=dict(id='research:'+sha(OUT/'source.txt')+':seoul-bike-33719',text=source,
               source_version_id='research-text-sha256:'+sha(OUT/'source.txt'),parse_run_id=None,
               locator=dict(kind='saved_research_text_projection',source_html_sha256=sha(OUT/'source.html')))
    originals={c['id']:{'seoul-bike-33719':block} for c in cases}
    provided={c['id']:adapter.views(c,originals[c['id']]) for c in cases}
    structure=read(OUT/'physical_structure.json')
    for c in cases:
        def payload(text):return json.loads(text.split('<|im_start|>user\n')[1].split('<|im_end|>')[0])
        plain=payload(prompt(c,[]));structured=payload(prompt(c,[],structure))
        assert structured.pop('physical_structure')==structure and plain==structured
    write(OUT/'inputs.json',cases);write(OUT/'originals.json',originals);write(OUT/'provided.json',provided)
    write(OUT/'prompts.json',[dict(id=c['id'],task='select',prompt=adapter.selector_prompt(c,provided[c['id']])) for c in cases])
    (OUT/'settings.json').write_bytes((original.OUT/'settings.json').read_bytes())
    files=['source.html','source.txt','fragment.html','source_receipt.json','physical_structure.json','physical_structure_audit.json',
           'author_cases_blind.json','criteria.json','agreement_review.json','inputs.json','originals.json','provided.json','prompts.json','settings.json','prepare_source.py']
    write(OUT/'prepared.json',dict(at=time.time(),max_calls=3*len(cases),files={n:sha(OUT/n) for n in files},
          code={**read(original.OUT/'prepared.json')['code'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},
          order='direct selectors, then plain and structured with same selections; no retry',
          disclosure='New source serializes original cells once, adds table identity; both payloads JSON-minified without changing values. No AR re-expression or cross-source causal pooling.'))


def check():
    original.check();frozen=read(OUT/'prepared.json')
    assert all(sha(OUT/n)==h for n,h in frozen['files'].items())
    assert all(sha(ROOT/n)==h for n,h in frozen['code'].items())


def preflight():
    assert not (OUT/'freeze.json').exists()
    check();assert read(OUT/'execution_authorization.json')['compute_allocated']
    props=prior.previous.prior.base.api('/props');old=read(original.OUT/'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old.items() if k!='media_marker'}
    rows=[prior.request_row(r) for r in read(OUT/'prompts.json')]
    capacities=[]
    for c in read(OUT/'inputs.json'):
        for task in ['plain','structured']:
            row=prior.request_row(dict(id=c['id'],task=task,prompt=prompt(c,[],read(OUT/'physical_structure.json') if task=='structured' else None)))
            capacities.append(dict(id=c['id'],task=task,input_tokens=row['input_tokens']))
    write(OUT/'requests.json',rows);write(OUT/'props.json',props);write(OUT/'candidate_capacity.json',capacities)
    write(OUT/'freeze.json',dict(at=time.time(),max_calls=read(OUT/'prepared.json')['max_calls'],files={n:sha(OUT/n) for n in
          ['prepared.json','requests.json','props.json','candidate_capacity.json','execution_authorization.json']}))


def run():
    check();assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert prior.previous.prior.base.api('/props')==read(OUT/'props.json')
    dest=OUT/'run';dest.mkdir();cases={c['id']:c for c in read(OUT/'inputs.json')}
    originals=read(OUT/'originals.json');provided=read(OUT/'provided.json')
    result=dict(calls=0,records=[],semantic_review='pending');start=time.monotonic()
    def save():result['wall_s']=time.monotonic()-start;write(dest/'result.json',result)
    def call(row):
        record=dict(id=row['id'],task=row['task'],input_tokens=row['input_tokens'],contract_pass=False,
                    request_sha256=prior.text_hash(json.dumps(row['request'],ensure_ascii=False)))
        result['records'].append(record);result['calls']+=1;assert result['calls']<=read(OUT/'freeze.json')['max_calls'];save()
        before=time.monotonic()
        try:
            raw=prior.previous.prior.base.call('/completion',row['request']);path=dest/(row['id']+'_'+row['task']+'_response.json');path.write_bytes(raw)
            response=json.loads(raw);record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('stop_type')!='eos' or response.get('truncated'):raise ValueError('incomplete_generation')
            answer=json.loads('{'+response['content'],object_pairs_hook=prior.previous.strict_object);record['answer']=answer
            if row['task']=='select':record['parsed']=adapter.restore(answer,cases[row['id']],originals[row['id']],provided[row['id']])
            else:
                record['parsed']=prior.previous.parse_final(answer,cases[row['id']]);record['label']=prior.previous.prior.MAPPING[answer['label']]
            record['contract_pass']=True
        except (OSError,ValueError,KeyError,TypeError) as error:record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;save()
        print(row['id'],row['task'],record['contract_pass'],record.get('label'),record.get('error'),flush=True)
    for row in read(OUT/'requests.json'):call(row)
    dynamic=[]
    for task in ['plain','structured']:
        for selected in [r for r in result['records'] if r['task']=='select' and r['contract_pass']]:
            ident=selected['id'];spans=selected['parsed']['selected_source_spans']
            try:row=prior.request_row(dict(id=ident,task=task,prompt=prompt(cases[ident],spans,read(OUT/'physical_structure.json') if task=='structured' else None)))
            except ValueError as error:
                result['records'].append(dict(id=ident,task=task,contract_pass=False,called=False,error=repr(error)));save();continue
            dynamic.append(dict(row,selection_raw_sha256=selected['raw_sha256'],selected_source_spans=spans));write(dest/'judgment_requests.json',dynamic);call(row)
    save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['prepare','check','preflight','run'])
    globals()[parser.parse_args().mode]()
