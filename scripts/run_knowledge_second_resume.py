"""Bounded authority E/R, existing endpoint repair, and one extra-neighbor comparison."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from time import monotonic
from unittest.mock import patch

import httpx
import jsonschema
from app.knowledge import discovery_analysis as a2, discovery_grounding as engine
from app.knowledge import discovery_synthesis as synthesis, discovery_scope as scope
from app.knowledge.service import KnowledgeService, encode
from scripts.run_knowledge_a6 import write, digest
from scripts.run_knowledge_meaning_probe import configure
from scripts.run_knowledge_neighbor_comparison import clean_run, group_for


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def neighbor_packets(run,case,concept,by,cm):
    primary=case['relations'][0]['id'];extra=case['relations'][1]['id']
    candidates=[case['relations'][0],*concept['observations']]
    ctx,deps,terms=synthesis.context_for(candidates,by,cm)
    ctx['design_relation_ids']=[primary];ctx,deps=scope.source_context(ctx,deps,by)
    owner=dict(id='extra-neighbor',primary_candidate_ids=[primary])
    ctx,deps,terms=synthesis.neighbor_context(run,'builder',ctx,terms,owner,by,cm)
    assert ctx['conceptualization_context']['selected_relation_ids']==[primary,extra]
    primary_packet,extra_packet=ctx['relation_neighbors']
    assert primary_packet['endpoints']['object']==extra_packet['endpoints']['object']
    assert len(extra_packet['endpoints']['object'])==5
    off=deepcopy(ctx);off['relation_neighbors']=[deepcopy(primary_packet)]
    off['conceptualization_context']['selected_relation_ids']=[primary]
    packets=[]
    for arm,context in [('N0',off),('N1',ctx)]:
        bound=a2.segments.bind(context,'extra-neighbor','builder:extra-neighbor',stable=True)
        _,prompt=a2.make_prompt(run,'builder',bound,deps,terms,'extra-neighbor')
        packets.append(dict(arm=arm,context=context,deps=deps,supplied=terms,prompt=prompt))
    left=json.loads(packets[0]['prompt'].split('\nINPUT:\n')[1])
    right=json.loads(packets[1]['prompt'].split('\nINPUT:\n')[1])
    assert extra not in json.dumps(left,ensure_ascii=False)
    right['relation_neighbors'].pop()
    right['conceptualization_context']['selected_relation_ids']=[primary]
    assert left==right, 'Only the complete extra packet and its selected ID may differ'
    return packets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--source-db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['grounding','binding','neighbor'],required=True)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();root=args.output
    prior_path=args.baseline/'n_builder_v2/inputs.json';prior=read(prior_path)
    configure(prior['run']['recipe']);a2.settings.KNOWLEDGE_DISCOVERY_NEIGHBORS=args.mode=='neighbor'
    if not args.execute:
        root.mkdir(parents=True,exist_ok=False)
        case=deepcopy(next(c for c in prior['cases'] if c['id']=='authority'))
        with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as db:
            original=json.loads(db.execute('SELECT payload FROM runs WHERE id=?',(case['source_run'],)).fetchone()[0])
        raw=deepcopy(next(u for u in original['analysis_units'] if u['id']==case['source_unit']))
        assert raw['status']=='succeeded' and raw['attempts'] and a2.profile.digest(raw)==case['relation_provenance']['unit_hash']
        assert raw['output']['relations']==case['relations']
        run=clean_run(prior['run']);run['recipe']=a2.recipe(dict(model_calls=32,model_seconds=57600,additional_rounds=0,revisions=1,searches=0))
        run['model_identity']=a2.model_identity(run['recipe'])
        raw['diagnostic_import']=dict(source_run_id=case['source_run'],source_unit_hash=a2.profile.digest(raw),
            note='Actual succeeded Relation imported with its attempts; not a zero-attempt projection')
        raw['group_id']='authority';run['analysis_units']=[raw];run['frontier']=[group_for(case)]
        by={b['id']:b for b in prior['blocks']};cm=a2.profile.contexts(prior['blocks'])
        data=dict(run=run,blocks=prior['blocks'],case=case,mode=args.mode)
        sources=[prior_path,args.source_db]
        if args.mode=='neighbor':
            concept_path=args.baseline/'n_v3/execution/authority_N0.json';sources.append(concept_path)
            concept=read(concept_path)['concept'];assert concept
            data['packets']=neighbor_packets(run,case,concept,by,cm)
            data['concept_provenance']=dict(path=str(concept_path),sha256=digest(concept_path),new_concept_calls=0)
        else:
            builder_path=args.baseline/'n_builder_v2/execution/authority_N1.json';sources.append(builder_path)
            saved=read(builder_path)
            builder=deepcopy(next(u for u in saved['run']['analysis_units'] if u['stage']=='builder' and u['status']=='succeeded'))
            builder['diagnostic_import']=dict(path=str(builder_path),sha256=digest(builder_path),unapproved=True)
            run['analysis_units'].append(builder);taxonomy=deepcopy(builder['output'])
            group=dict(id=builder['group_id'],round=0,status='taxonomy_generated',candidates=deepcopy(case['relations']),
                primary_candidate_ids=[r['id'] for r in case['relations']],design_candidate_ids=[],
                design_candidates=deepcopy(taxonomy['observations']+taxonomy['modeled_relations']),
                analysis_group_ids=['authority'],builder_tool_context=dict(terms={}))
            run['candidate_groups']=[group];data['group']=group;data['taxonomy']=taxonomy
            a2.finish(run,prior['blocks'],set(by))
            if args.mode=='grounding':
                cases_path=args.baseline/'core_cases.json';sources.append(cases_path)
                question=next(c['question'] for c in read(cases_path)['cases'] if c['id']=='priority_authority')
                context=dict(requirement=dict(id='authority-local',kind='cq',question=question),requirement_scope='제3항 권한의 작은 원문 대조',
                    blocks=[dict(ref=case['block_id'],text=by[case['block_id']]['text'],span=[0,len(by[case['block_id']]['text'])])])
                ctx=engine.source_packet(run,context,by)
                assert len(ctx['unapproved_relations'])==2
                data['packets']=[dict(context=ctx,deps=[case['block_id']],supplied={},stage='context')]
            else:
                ctx,deps,terms=synthesis.review_context(run,group,taxonomy,by,cm)
                data['packets']=[dict(context=b['context'],deps=b['dependency_ids'],supplied=b['supplied'],stage='critic')
                    for b in synthesis.review_batches(ctx,deps,terms,by,cm)]
                assert len(data['packets'])==3
        checks=[]
        for n,packet in enumerate(data['packets']):
            stage=packet.get('stage','builder');ctx=deepcopy(packet['context'])
            if ctx.get('review_component'): ctx['review_bundle_id']='preflight'
            bound=a2.segments.bind(ctx,run['id'],stage+':preflight',stable=True)
            mapping,prompt=a2.make_prompt(run,stage,bound,packet['deps'],packet['supplied'])
            _,schema,_,_=a2.response_contract(run,stage,bound,packet['supplied'],mapping,sorted(a2.raw_refs(bound)))
            jsonschema.Draft202012Validator.check_schema(schema)
            size=a2.input_size(run,stage,ctx,packet['deps'],packet['supplied'])
            assert size['input_chars']<=size['input_chars_limit'] and size['request_input_bytes']<=size['input_bytes_limit'],size
            checks.append(dict(stage=stage,**size));write(root/f'packet_{n}.json',dict(prompt=prompt,schema=schema))
        write(root/'inputs.json',data)
        maximum={'grounding':4,'binding':16,'neighbor':2}[args.mode]
        runtime=[*Path('app/knowledge').glob('*.py'),Path(__file__),Path('app/core/config.py'),
            Path('scripts/run_knowledge_neighbor_comparison.py'),Path('scripts/run_knowledge_meaning_probe.py')]
        write(root/'freeze.json',dict(inputs_sha256=digest(root/'inputs.json'),sources={str(p.resolve()):digest(p) for p in sources},
            runtime_hashes={str(p.resolve()):digest(p) for p in runtime},checks=checks,max_http=maximum,max_seconds=1800*maximum,
            criteria=['Preserve minister/LH and governor/local corporation branch pairs, article 49, housing purpose, local circumstances and exceptions',
                'No external details or legal inclusion invented; no forced support of raw hypotheses',
                'Repair requires actual current binding refutation, unchanged normal subject/source and actual post-review',
                'N compares only primary r1 output with identical Concept/source; extra r2 is not a new primary success',
                'No retry/tuning after same failure; independent N still runs; no whole-CQ/A3 success without prerequisites'],
            semantic_retries=0,development_exposed=True))
        print(json.dumps(dict(prepared=True,mode=args.mode,checks=checks),ensure_ascii=False));return
    data=read(root/'inputs.json');frozen=read(root/'freeze.json');run=data['run'];blocks=data['blocks'];by={b['id']:b for b in blocks};cm=a2.profile.contexts(blocks)
    assert data['mode']==args.mode and digest(root/'inputs.json')==frozen['inputs_sha256']
    assert all(digest(Path(p))==h for p,h in {**frozen['sources'],**frozen['runtime_hashes']}.items())
    assert run['recipe']==a2.recipe(run['recipe']['budgets']) and run['model_identity']==a2.model_identity(run['recipe'])
    output=root/'execution';output.mkdir(exist_ok=False)
    with sqlite3.connect(args.source_db.resolve().as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(output/'knowledge.db') as db: src.backup(db)
    service=KnowledgeService(output/'knowledge.db')
    with service.repository.connect() as db: db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
    original=a2.model_call;post=httpx.AsyncClient.post;calls=[];active={};started=monotonic()
    async def observed(client,url,**kwargs):
        if str(url).endswith('/api/generate'): write(active['path']/'http_request.json',kwargs['json'])
        response=await post(client,url,**kwargs)
        if str(url).endswith('/api/generate'): (active['path']/'http_response.json').write_bytes(response.content)
        return response
    async def measured(prompt,schema,stage,current,timeout):
        assert len(calls)<frozen['max_http'] and monotonic()-started<frozen['max_seconds']
        assert all(digest(Path(p))==h for p,h in frozen['runtime_hashes'].items())
        path=output/f'call_{len(calls)+1:02d}';path.mkdir();active['path']=path
        row=dict(stage=stage,path=str(path));calls.append(row);start=monotonic()
        write(path/'input.json',dict(prompt=prompt,schema=schema))
        try:
            result=await original(prompt,schema,stage,current,min(timeout,frozen['max_seconds']-(monotonic()-started)))
            write(path/'model_response.json',result);return result
        finally:
            row['elapsed_s']=round(monotonic()-start,3);write(path/'timing.json',row);print(json.dumps(row),flush=True)
    try:
        with patch.object(a2,'model_call',measured),patch.object(httpx.AsyncClient,'post',observed):
            if args.mode=='neighbor':
                for packet in data['packets']:
                    result=a2.call(service,run,'builder','extra-'+packet['arm'],packet['context'],packet['deps'],by,packet['supplied'])
                    write(output/(packet['arm']+'.json'),dict(output=result,unit=run['analysis_units'][-1]))
            elif args.mode=='binding':
                group=run['candidate_groups'][0];taxonomy=data['taxonomy']
                ctx,deps,terms=synthesis.review_context(run,group,taxonomy,by,cm)
                review=synthesis.focused_reviews(service,run,group,ctx,deps,terms,by,cm,revised=True,revision_key='before')
                write(output/'before_review.json',dict(review=review,group=group))
                if review:
                    synthesis.revise(service,run,group,review,taxonomy,by,cm)
                a2.finish(run,blocks,a2.allowed_ids(service,blocks));a2.save(service,run)
                write(output/'after.json',dict(run=run))
            else:
                packet=data['packets'][0];ctx=packet['context']
                value=a2.call(service,run,'context','authority-source',ctx,packet['deps'],by,{})
                source=run['analysis_units'][-1];source['grounding_context']=deepcopy(ctx)
                write(output/'source.json',dict(output=value,unit=source))
                if value:
                    candidates=data['taxonomy']['observations']+data['taxonomy']['modeled_relations'];terms={c['id']:c for c in candidates}
                    rctx=dict(meaning_phase='representation',requirement=ctx['requirement'],blocks=ctx['blocks'],
                        unapproved_relations=ctx['unapproved_relations'],source_assessment=value,
                        source_receipt=dict(unit_id=source['id'],assessment_hash=value['assessment_hash']),candidates=candidates)
                    result=a2.call(service,run,'requirements','authority-expression',rctx,packet['deps'],by,terms)
                    write(output/'expression.json',dict(output=result,unit=run['analysis_units'][-1]))
                    if result:
                        d=engine.descriptor('representation','authority-expression',rctx,packet['deps'],terms)
                        changed=engine.challenge(service,run,d,result,by)
                        write(output/'challenge.json',dict(changed=changed,requests=result['source_challenges'],unit=run['analysis_units'][-1]))
                        if changed:
                            current=run['analysis_units'][-1]
                            rctx.update(source_assessment=current['output'],source_receipt=dict(unit_id=current['id'],assessment_hash=current['output']['assessment_hash']),blocks=current['grounding_context']['blocks'])
                            result=a2.call(service,run,'requirements','authority-expression-after',rctx,sorted(a2.raw_refs(rctx)),by,terms)
                            write(output/'expression_after.json',dict(output=result,unit=run['analysis_units'][-1]))
                a2.save(service,run)
            write(output/'result.json',dict(run=run))
    finally:
        service.shutdown()
        write(output/'receipt.json',dict(calls=calls,new_http=len(calls),elapsed_s=round(monotonic()-started,3),
            source_unchanged=all(digest(Path(p))==h for p,h in frozen['sources'].items()),
            runtime_unchanged=all(digest(Path(p))==h for p,h in frozen['runtime_hashes'].items())))


if __name__=='__main__': main()
