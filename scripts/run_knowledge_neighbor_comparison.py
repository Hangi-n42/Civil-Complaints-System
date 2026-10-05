"""Frozen N0/N1 source-neighbor comparison using actual saved Relation calls."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
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


def clean_run(prior):
    run=deepcopy(prior)
    for name in list(run):
        if name.startswith('diagnostic_'): run.pop(name)
    run.update(id=uuid4().hex,status='running',finished_at=None,error=None,analysis_units=[],candidate_groups=[],
        recovery_requests=[],frontier=[],result={},tool_events=[],search_cache={},extra_requests=[],
        role_time_estimates={},metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0,searches=0))
    run.pop('candidate_identity',None)
    run['recipe']=a2.recipe(dict(model_calls=16,model_seconds=28800,additional_rounds=0,revisions=1,searches=0))
    return run


def concept_context(case,blocks):
    by={b['id']:b for b in blocks};block=by[case['block_id']];span=case['primary_span']
    views=[dict(ref=block['id'],span=span,text=block['text'][slice(*span)],analysis_target=True)]
    if span!=[0,len(block['text'])]:
        views.append(dict(ref=block['id'],span=[0,len(block['text'])],text=block['text'],context_only=True,analysis_target=False))
    context=dict(blocks=views,reviewed_base=[],comparison_terms=[],selection_reason='동결한 직접 정의/역할 대조',
        focus_spans=[dict(block_id=block['id'],span=span)])
    return scope.source_context(context,[block['id']],by)[0]


def group_for(case):
    return dict(id=case['id'],block_ids=[case['block_id']],segments=[],roles=['concept','relation'],round=0,
        status='raw_provided',reason='동결한 독립 개념화 대조',analysis_grounded=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();root=args.output
    source=json.loads(args.input.read_text());configure(source['run']['recipe'])
    if not args.execute:
        root.mkdir(parents=True,exist_ok=False)
        cases=[dict(id='definitions',block_id='2641967317ad4690b7e90a099987e208',primary_span=[0,628],
            source_run='d5715251ada74d7280d190b1f1a6ca2c',source_unit='relation:sg_49f88c1a962b6c1a157b'),
            dict(id='authority',block_id='1e4c6a6dfc69410b923e15b9e748efa4',primary_span=[0,539],
            source_run='9481868d35d44f46a8a1dd46d9239889',source_unit='relation:recovery_64b4024e73916b4a6873')]
        with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as db:
            for case in cases:
                original=json.loads(db.execute('SELECT * FROM runs WHERE id=?',(case['source_run'],)).fetchone()[1])
                unit=next(u for u in original['analysis_units'] if u['id']==case['source_unit'])
                assert unit['status']=='succeeded' and unit['attempts']
                rows=[deepcopy(c) for c in unit['output']['relations'] if case['block_id'] in c['evidence_ids']]
                # Extracted natural statements only; no fixed normal candidate or reviewed answer.
                assert all(not c['subject'].startswith('dc_') and not c['object'].startswith('dc_') for c in rows)
                case.update(relations=rows,relation_provenance=dict(run_id=original['id'],unit_id=unit['id'],
                    unit_hash=a2.profile.digest(unit),attempts=deepcopy(unit['attempts'])),
                    builder_batches=[[c['id'] for c in rows[i:i+2]] for i in range(0,len(rows),2)])
        run=clean_run(source['run']);run['model_identity']=a2.model_identity(run['recipe'])
        write(root/'inputs.json',dict(run=run,blocks=source['blocks'],cases=cases))
        checks=[]
        for case in cases:
            for arm in ('N0','N1'):
                trial=deepcopy(run);trial['recipe']['neighbor_contract']='disabled' if arm=='N0' else 'relation-neighbors-v1'
                trial['frontier']=[group_for(case)]
                trial['analysis_units']=[dict(id=case['source_unit'],stage='relation',status='succeeded',output=dict(relations=case['relations']))]
                by={b['id']:b for b in source['blocks']};cm=a2.profile.contexts(source['blocks'])
                context=concept_context(case,source['blocks'])
                context,deps,supplied=synthesis.neighbor_context(trial,'concept',context,{},dict(id=case['id']),by,cm)
                size=a2.input_size(trial,'concept',context,deps,supplied)
                bound=a2.segments.bind(context,trial['id'],'concept:',stable=True)
                mapping,_=a2.make_prompt(trial,'concept',bound,deps,supplied)
                _,schema,_,_=a2.response_contract(trial,'concept',bound,supplied,mapping,sorted(a2.raw_refs(bound)))
                jsonschema.Draft202012Validator.check_schema(schema)
                assert size['input_chars']<=size['input_chars_limit'] and size['request_input_bytes']<=size['input_bytes_limit'],size
                checks.append(dict(case=case['id'],arm=arm,size=size,selected=context.get('conceptualization_context',{}).get('selected_relation_ids',[])))
        criteria=dict(required=['주분석 직접 정의의 공공임대 범위·건설/매입 차이와 국소 부정 보존',
            '권한 주체별 공급 조건·지역 실정·제1/2항 예외·지방공사 제49조/주택사업목적 한정 보존',
            '모든 신규 후보의 유형/역할·끝점·조건·근거 위치와 중복 검수'],
            prohibited=['미제공 별표/대통령령의 내용 확정','국민임대와 공공임대의 법적 포함 추정','이름만 같은 역할/개체 통합',
                '보완 원문에서 새로 추출한 후보를 주분석 범위 성과로 집계'],
            interpretation='개발 노출 자료의 제한 선택효과 비교. 순서 인과효과/사람 효용/실제 교정 효과 아님')
        write(root/'freeze.json',dict(input_sha256=digest(root/'inputs.json'),source_input_sha256=digest(args.input),source_db_sha256=digest(args.source_db),
            runtime_hashes={str(p.resolve()):digest(p) for p in [*Path('app/knowledge').glob('*.py'),Path(__file__),Path('scripts/run_knowledge_meaning_probe.py'),Path('app/core/config.py')]},
            criteria=criteria,checks=checks,max_http=sum(2*(1+len(c['builder_batches'])) for c in cases),
            max_seconds=1800*sum(2*(1+len(c['builder_batches'])) for c in cases),
            call_plan=[dict(case=c['id'],arm=a,concept_calls=1,builder_batches=c['builder_batches']) for c in cases for a in ('N0','N1')],
            shared_relation_new_http=0,shared_relation_logical_cost='Each arm includes its original saved Relation attempt; not new HTTP',
            semantic_retries=0,development_exposed=True))
        print(json.dumps(dict(prepared=True,checks=checks),ensure_ascii=False));return
    frozen=json.loads((root/'freeze.json').read_text());data=json.loads((root/'inputs.json').read_text())
    assert digest(root/'inputs.json')==frozen['input_sha256'] and digest(args.source_db)==frozen['source_db_sha256']
    assert digest(args.input)==frozen['source_input_sha256']
    assert a2.model_identity(data['run']['recipe'])==data['run']['model_identity']
    output=root/'execution';output.mkdir(exist_ok=False)
    with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(output/'knowledge.db') as db: src.backup(db)
    service=KnowledgeService(output/'knowledge.db');blocks=data['blocks'];by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    original=a2.model_call;post=httpx.AsyncClient.post;calls=[];active={};started=monotonic();outcomes=[]
    async def observed(client,url,**kwargs):
        if str(url).endswith('/api/generate'): write(active['path']/'http_request.json',kwargs['json'])
        response=await post(client,url,**kwargs)
        if str(url).endswith('/api/generate'): (active['path']/'http_response.json').write_bytes(response.content)
        return response
    async def measured(prompt,schema,stage,run,timeout):
        assert len(calls)<frozen['max_http'] and monotonic()-started<frozen['max_seconds']
        assert all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())
        path=output/f'call_{len(calls)+1:02d}';path.mkdir();active['path']=path
        row=dict(case=active['case'],arm=active['arm'],stage=stage,path=str(path));calls.append(row);start=monotonic()
        write(path/'input.json',dict(prompt=prompt,schema=schema))
        try:
            result=await original(prompt,schema,stage,run,timeout);write(path/'model_response.json',result);return result
        finally:
            row['elapsed_s']=round(monotonic()-start,3);write(path/'timing.json',row);print(json.dumps(row),flush=True)
    try:
        with patch.object(a2,'model_call',measured),patch.object(httpx.AsyncClient,'post',observed):
            for case in data['cases']:
                for arm in ('N0','N1'):
                    active.update(case=case['id'],arm=arm);run=deepcopy(data['run']);run['id']=uuid4().hex
                    a2.settings.KNOWLEDGE_DISCOVERY_NEIGHBORS=arm=='N1'
                    run['recipe']['neighbor_contract']='disabled' if arm=='N0' else 'relation-neighbors-v1'
                    run['frontier']=[group_for(case)]
                    run['analysis_units']=[dict(id=case['source_unit'],stage='relation',status='succeeded',group_id=case['id'],
                        output=dict(relations=deepcopy(case['relations'])),dependency_ids=[case['block_id']],attempts=[],
                        diagnostic_import=case['relation_provenance'])]
                    with service.repository.connect() as db: db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
                    owner=dict(id=case['id']);ctx=concept_context(case,blocks)
                    ctx,deps,terms=synthesis.neighbor_context(run,'concept',ctx,{},owner,by,cm)
                    concept=a2.call(service,run,'concept',case['id'],ctx,deps,by,terms)
                    builders=[]
                    for number,ids in enumerate(case['builder_batches']):
                        candidates=[r for r in case['relations'] if r['id'] in ids]+(concept or {}).get('observations',[])
                        ctx,deps,terms=synthesis.context_for(candidates,by,cm)
                        ctx['design_relation_ids']=ids
                        ctx,deps=scope.source_context(ctx,deps,by)
                        group=dict(id=case['id']+f':builder:{number}',primary_candidate_ids=ids)
                        ctx,deps,terms=synthesis.neighbor_context(run,'builder',ctx,terms,group,by,cm)
                        result=a2.call(service,run,'builder',group['id'],ctx,deps,by,terms)
                        builders.append(dict(group=group,output=result))
                    record=dict(case=case['id'],arm=arm,run=run,concept_owner=owner,concept=concept,builders=builders)
                    write(output/f'{case["id"]}_{arm}.json',record);outcomes.append(record)
        # Evaluation copies omit arm/neighbor-selection metadata; key stays separate.
        mapping={}
        (output/'blind').mkdir()
        for number,row in enumerate(outcomes):
            label=f'sample_{number+1:02d}';mapping[label]=dict(case=row['case'],arm=row['arm'])
            write(output/'blind'/f'{label}.json',dict(case=row['case'],concept=row['concept'],builders=[b['output'] for b in row['builders']]))
        write(output/'blind_key.json',mapping)
    finally:
        service.shutdown();write(output/'receipt.json',dict(calls=calls,new_http=len(calls),elapsed_s=round(monotonic()-started,3),
            source_unchanged=digest(args.source_db)==frozen['source_db_sha256'],runtime_unchanged=all(digest(Path(n))==h for n,h in frozen['runtime_hashes'].items())))


if __name__=='__main__': main()
