"""Freeze and probe source-meaning boundaries; never feed assessment criteria to the model."""
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
from scripts.run_knowledge_a6 import digest, write


def configure(recipe):
    for setting,key in [('KNOWLEDGE_DISCOVERY_THINK','think'),('KNOWLEDGE_DISCOVERY_INPUT_CHARS','input_chars'),
        ('KNOWLEDGE_DISCOVERY_NUM_CTX','num_ctx'),('KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX','requirements_num_ctx'),
        ('KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT','requirements_num_predict'),('KNOWLEDGE_DESIGN_TIMEOUT','call_timeout')]:
        setattr(a2.settings,setting,recipe[key])
    a2.settings.STRUCTURING_MODEL=recipe['models']['draft']
    a2.settings.KNOWLEDGE_DISCOVERY_REVIEW_MODEL=recipe['models']['review']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--reassess-output',type=Path,help='Saved actual E output to challenge through model R, not a supplied correct judgment')
    args=parser.parse_args();root=args.output
    supplied=json.loads(args.cases.read_text(encoding='utf-8'));configure(supplied['run']['recipe'])
    if not args.execute:
        root.mkdir(parents=True,exist_ok=False)
        run=deepcopy(supplied['run']);run.update(id=uuid4().hex,status='running',finished_at=None,error=None,
            metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0,searches=0),role_time_estimates={},cqs=[],scope_items=[])
        # Standalone E probes have no downstream R/join reservation; each context retains its question.
        maximum=3 if args.reassess_output else len(supplied['cases'])
        run['recipe']=a2.recipe(dict(model_calls=maximum,model_seconds=1800*maximum,additional_rounds=0,revisions=1,searches=0))
        run['model_identity']=a2.model_identity(run['recipe'])
        contexts=[];inventory=[dict(block_id=b['id'],title=b.get('title',''),source_version_id=b['source_version_id'],parse_run_id=b['parse_run_id']) for b in supplied['blocks'] if b['id'] in run['analysis_block_ids']]
        by={b['id']:b for b in supplied['blocks']}
        for case in supplied['cases']:
            views=[dict(ref=v['block_id'],span=v['span'],text=by[v['block_id']]['text'][slice(*v['span'])],analysis_target=v.get('analysis_target',True)) for v in case['views']]
            ctx=dict(meaning_phase='grounding',context_phase='grounding',requirement=dict(kind='cq',id=case['id'],question=case['question']),
                target=dict(label=case['question'],scope_kind='requirement',cq_ids=[case['id']],scope_item_ids=[]),blocks=views,
                input_inventory=[dict(b,selected=any(v['ref']==b['block_id'] for v in views)) for b in inventory],
                requirement_scope='고정된 작은 원문 판단 대조',discoveries=[],reference_availability=[])
            ctx['source_fingerprint']=a2.profile.digest(ctx);contexts.append(dict(id=case['id'],context=ctx))
        reassessment=None
        if args.reassess_output:
            old=json.loads(args.reassess_output.read_text())
            original=deepcopy(old['unit']);original['id']='context:imported-actual-source'
            if not original.get('grounding_context'):
                old_inputs=json.loads((args.reassess_output.parent.parent/'inputs.json').read_text())
                original['grounding_context']=deepcopy(next(c['context'] for c in old_inputs['cases'] if c['id']==args.reassess_output.stem))
            # New diagnostic run explicitly imports an unapproved source baseline, not its execution budget.
            original.pop('grounding_base_id',None);original.pop('grounding_actions',None)
            original['diagnostic_import']=dict(path=str(args.reassess_output),sha256=digest(args.reassess_output),
                status='unapproved prior-contract actual output, explicitly reassessed against current source')
            run['analysis_units']=[original]
            # Normal authority candidates are a control; no corrected candidate or correct E is injected.
            candidates=[c for c in supplied['run']['result']['relations'] if c['id'] in supplied['reassessment_candidate_ids']]
            ends={c[k] for c in candidates for k in ('subject','object')}
            candidates += [c for c in supplied['run']['result']['observations'] if c['id'] in ends]
            terms={c['id']:c for c in candidates}
            ctx=dict(meaning_phase='representation',requirement=deepcopy(original['grounding_context']['requirement']),blocks=deepcopy(original['grounding_context']['blocks']),
                source_assessment=deepcopy(original['output']),source_receipt=dict(unit_id=original['id'],assessment_hash=original['output']['assessment_hash']),
                candidates=deepcopy(candidates))
            contexts=[dict(id='authority_expression_before',context=ctx,supplied=terms)]
            reassessment=dict(source_unit_id=original['id'],source_path=str(args.reassess_output),source_sha256=digest(args.reassess_output))
        write(root/'inputs.json',dict(run=run,blocks=supplied['blocks'],cases=contexts,reassessment=reassessment))
        sizes=[dict(id=c['id'],**a2.input_size(run,'requirements' if reassessment else 'context',c['context'],sorted({v['ref'] for v in c['context']['blocks']}),c.get('supplied',{}))) for c in contexts]
        for size in sizes:
            assert size['input_chars']<=size['input_chars_limit'] and size['request_input_bytes']<=size['input_bytes_limit'],size
        write(root/'freeze.json',dict(input_sha256=digest(root/'inputs.json'),cases_sha256=digest(args.cases),source_db_sha256=digest(args.source_db),
            runtime_hashes={str(p.resolve()):digest(p) for p in [*Path('app/knowledge').glob('*.py'),Path(__file__),Path('app/core/config.py')]},
            recipe=run['recipe'],model_identity=run['model_identity'],sizes=sizes,max_http=maximum,max_seconds=1800*maximum,
            criteria=supplied['criteria'],semantic_retries=0,development_exposed=True))
        print(json.dumps(dict(prepared=True,cases=len(contexts),sizes=sizes),ensure_ascii=False));return
    frozen=json.loads((root/'freeze.json').read_text());data=json.loads((root/'inputs.json').read_text());run=data['run'];blocks=data['blocks'];by={b['id']:b for b in blocks}
    assert digest(root/'inputs.json')==frozen['input_sha256'] and digest(args.cases)==frozen['cases_sha256']
    assert digest(args.source_db)==frozen['source_db_sha256']
    assert a2.recipe(run['recipe']['budgets'])==run['recipe'] and a2.model_identity(run['recipe'])==run['model_identity']
    output=root/'execution';output.mkdir(exist_ok=False)
    with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(output/'knowledge.db') as target: src.backup(target)
    service=KnowledgeService(output/'knowledge.db')
    with service.repository.connect() as db: db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
    call=a2.model_call;post=httpx.AsyncClient.post;calls=[];active={};started=monotonic()
    async def observed(client,url,**kwargs):
        if str(url).endswith('/api/generate'): write(active['path']/'http_request.json',kwargs['json'])
        response=await post(client,url,**kwargs)
        if str(url).endswith('/api/generate'): (active['path']/'http_response.json').write_bytes(response.content)
        return response
    async def measured(prompt,schema,stage,current,timeout):
        assert len(calls)<frozen['max_http'] and monotonic()-started<frozen['max_seconds']
        assert all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())
        path=output/f'call_{len(calls)+1:02d}';path.mkdir();active['path']=path
        row=dict(case_id=active['case_id'],path=str(path));calls.append(row);t=monotonic()
        write(path/'input.json',dict(prompt=prompt,schema=schema))
        try:
            value=await call(prompt,schema,stage,current,timeout);write(path/'model_response.json',value);return value
        finally:
            row['elapsed_s']=round(monotonic()-t,3);write(path/'timing.json',row);print(json.dumps(row),flush=True)
    try:
        with patch.object(a2,'model_call',measured),patch.object(httpx.AsyncClient,'post',observed):
            for case in data['cases']:
                active['case_id']=case['id'];ctx=case['context'];deps=sorted({v['ref'] for v in ctx['blocks']})
                stage='requirements' if data.get('reassessment') else 'context'
                result=a2.call(service,run,stage,'meaning-probe:'+case['id'],ctx,deps,by,case.get('supplied',{}))
                write(output/(case['id']+'.json'),dict(output=result,unit=run['analysis_units'][-1]))
                if data.get('reassessment') and result:
                    d=engine.descriptor('representation','meaning-probe:'+case['id'],ctx,deps,case['supplied'])
                    active['case_id']='authority_source_challenge'
                    changed=engine.challenge(service,run,d,result,by)
                    write(output/'source_challenge.json',dict(changed=changed,requests=result.get('source_challenges',[]),unit=run['analysis_units'][-1]))
                    if changed:
                        source=run['analysis_units'][-1]
                        after=dict(deepcopy(ctx),source_assessment=deepcopy(source['output']),
                            source_receipt=dict(unit_id=source['id'],assessment_hash=source['output']['assessment_hash']),
                            blocks=deepcopy(source['grounding_context']['blocks']))
                        active['case_id']='authority_expression_after'
                        checked=a2.call(service,run,'requirements','meaning-probe:authority_expression_after',after,
                            sorted({v['ref'] for v in after['blocks']}),by,case['supplied'])
                        write(output/'authority_expression_after.json',dict(output=checked,unit=run['analysis_units'][-1]))
        write(output/'result.json',dict(run=run))
    finally:
        service.shutdown();write(output/'receipt.json',dict(calls=calls,http_calls=len(calls),elapsed_s=round(monotonic()-started,3),
            source_unchanged=digest(args.source_db)==frozen['source_db_sha256'],runtime_unchanged=all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())))


if __name__=='__main__': main()
