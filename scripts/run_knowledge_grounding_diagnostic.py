"""Freeze then evaluate source/expression/join on an unchanged supplied candidate snapshot."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

import httpx
from app.knowledge import discovery_analysis as a2, discovery_grounding as engine
from app.knowledge.service import KnowledgeService, encode
from scripts.run_knowledge_a6 import write, digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();root=args.output
    payload=json.loads(args.input.read_text(encoding='utf-8'));prior=payload['run'];old=prior['recipe']
    settings=a2.settings
    settings.STRUCTURING_MODEL=old['models']['draft'];settings.KNOWLEDGE_DISCOVERY_REVIEW_MODEL=old['models']['review']
    settings.KNOWLEDGE_DISCOVERY_THINK=old['think'];settings.KNOWLEDGE_DISCOVERY_INPUT_CHARS=old['input_chars']
    settings.KNOWLEDGE_DISCOVERY_NUM_CTX=old['num_ctx'];settings.KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX=old['requirements_num_ctx']
    settings.KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT=old['requirements_num_predict'];settings.KNOWLEDGE_DESIGN_TIMEOUT=old['call_timeout']
    freeze=root/'freeze.json';inputs=root/'inputs.json'
    if not args.execute:
        root.mkdir(parents=True,exist_ok=False)
        run=deepcopy(prior);run.update(id=uuid4().hex,status='running',finished_at=None,stop_reason=None,
            metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0,searches=0),role_time_estimates={})
        run['recipe']=a2.recipe(dict(model_calls=8,model_seconds=14400,additional_rounds=0,revisions=1,searches=0))
        run['model_identity']=a2.model_identity(run['recipe'])
        run['diagnostic_provenance']=dict(source_run_id=prior['id'],source_input_sha256=digest(args.input),mode='fixed_candidates_no_repair',semantic_retries=0)
        for k in ('error','changeset_id','execution_order'): run.pop(k,None)
        write(inputs,dict(run=run,blocks=payload['blocks']))
        by={b['id']:b for b in payload['blocks']}
        descriptors=engine.plan(run,run['result'],by)
        preflight=[dict(id=d['id'],stage=d['stage'],ready=d['ready'],**a2.input_size(run,d['stage'],d['context'],d['deps'],d['supplied'])) for d in descriptors]
        write(freeze,dict(inputs_sha256=digest(inputs),sources={str(p.resolve()):digest(p) for p in (args.input,args.source_db)},
            runtime_hashes={str(p.resolve()):digest(p) for p in [*Path('app/knowledge').glob('*.py'),Path(__file__),Path('app/core/config.py')]},
            recipe=run['recipe'],model_identity=run['model_identity'],preflight=preflight,max_http=8,max_seconds=14400,
            criteria=['No unsupported construction/legal inclusion recovery','Preserve supported selection duties and authority separately from missing external detail',
                'Fixed 19 candidates are unchanged; no repair success claimed','Missing detection and wrong-endpoint repair require separate executions',
                'One source re-entry, no semantic retry or parameter tuning; stop on repeated semantic bottleneck']))
        print(json.dumps(dict(prepared=True,run_id=run['id'],preflight=preflight),ensure_ascii=False));return
    frozen=json.loads(freeze.read_text());data=json.loads(inputs.read_text());run=data['run'];blocks=data['blocks'];by={b['id']:b for b in blocks}
    assert digest(inputs)==frozen['inputs_sha256']
    assert all(digest(Path(n))==h for n,h in {**frozen['sources'],**frozen['runtime_hashes']}.items())
    assert a2.recipe(run['recipe']['budgets'])==run['recipe'] and a2.model_identity(run['recipe'])==run['model_identity']
    output=root/'execution';output.mkdir(exist_ok=False)
    with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(output/'knowledge.db') as target: source.backup(target)
    service=KnowledgeService(output/'knowledge.db')
    with service.repository.connect() as db: db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
    call=a2.model_call;post=httpx.AsyncClient.post;calls=[];active={};before=deepcopy(run['result']);start=monotonic()
    async def observed(client,url,**kwargs):
        if str(url).endswith('/api/generate'): write(active['path']/'http_request.json',kwargs['json'])
        response=await post(client,url,**kwargs)
        if str(url).endswith('/api/generate'): (active['path']/'http_response.json').write_bytes(response.content)
        return response
    async def measured(prompt,schema,stage,current,timeout):
        assert len(calls)<frozen['max_http'] and monotonic()-start<frozen['max_seconds']
        assert all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())
        path=output/f'call_{len(calls)+1:02d}';path.mkdir();active['path']=path
        row=dict(stage=stage,path=str(path),elapsed_s=0);calls.append(row);write(path/'input.json',dict(prompt=prompt,schema=schema));started=monotonic()
        try:
            result=await call(prompt,schema,stage,current,timeout);write(path/'model_response.json',result);return result
        finally:
            row['elapsed_s']=round(monotonic()-started,3);write(path/'timing.json',row);print(json.dumps(row),flush=True)
    try:
        with patch.object(a2,'model_call',measured),patch.object(httpx.AsyncClient,'post',observed):
            engine.assess(service,run,blocks,by,a2.profile.contexts(blocks),rechecked=True)
        a2.finish(run,blocks,a2.allowed_ids(service,blocks));a2.save(service,run)
        write(output/'result.json',dict(run=run))
        assert all(run['result'][f]==before[f] for f in ('observations','relations'))
    finally:
        service.shutdown()
        write(output/'receipt.json',dict(calls=calls,http_calls=len(calls),elapsed_s=round(monotonic()-start,3),
            source_unchanged=all(digest(Path(n))==h for n,h in frozen['sources'].items()),
            runtime_unchanged=all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())))


if __name__=='__main__': main()
