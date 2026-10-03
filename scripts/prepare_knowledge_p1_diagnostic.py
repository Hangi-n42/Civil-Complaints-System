"""Two observation packets on preserved N3/D5 sources; capture only, no generation."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,sqlite3
from unittest.mock import patch
from app.knowledge import discovery_analysis as a2,discovery_synthesis as synthesis,discovery_profile as profile,discovery_segments as segments
from app.knowledge.service import KnowledgeService
from app.generation.service import GenerationService

root=Path('data/knowledge/semantic_p1_preflight_20261003')
read=lambda p:json.loads(Path(p).read_text())
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ref(p):return dict(path=str(p),sha256=sha256(Path(p).read_bytes()).hexdigest())
parent_path=Path('data/knowledge/semantic_n3_20261003/correction_once/result.json')
d5_path=Path('data/knowledge/semantic_d5_20261001/current_changed/result.json')
old=read('data/knowledge/semantic_n3_preflight_20261003/diagnostic_inputs.json');parent=read(parent_path);d5=read(d5_path)
run=deepcopy(old['run']);run['cqs']=[q for q in d5['run']['cqs'] if q['id']=='C1']+run['cqs']
a2.settings.KNOWLEDGE_DISCOVERY_REVIEW_MODEL='gemma4:31b-it-q4_K_M'
run['recipe']=a2.recipe(dict(model_calls=2,model_seconds=600,searches=0,additional_rounds=0,revisions=0))
run['model_identity']=a2.model_identity(run['recipe'])
assert all(v['digest']=='6316f0629137b426c9d9b853ffc4c8209589f30ee39aebede6285096c0ff47e7' for v in run['model_identity'].values())
rows={c['id']:c for c in parent['run']['result']['observations']}
first=[deepcopy(rows[i]) for i in ('dc_4cb7f4df36ce42ce9c3136a74b234416','dc_67b5157d740e4ff9a04ec2cff2b63fe0')]
normal=deepcopy(next(c for c in d5['run']['result']['observations'] if c['id']=='dc_9b3317b75f0a404b853eeb30bab18b9a'))
changed=deepcopy(normal);changed['id']='eval_7f8cd934ff9d4b688a403ea0d694e020'
old_clause='주택을 공급받은 자가 해당 주택을 처분하려는 경우';new_clause='주택을 공급받는 즉시'
assert normal['definition'].count(old_clause)==1
changed['definition']=changed['definition'].replace(old_clause,new_clause)
assert {k for k in normal if normal[k]!=changed[k]}=={'id','definition'}
source_db=Path('data/knowledge/semantic_n3_20261003/correction_once/knowledge.db')
package=dict(source_db=str(source_db),run=run,taxonomy=dict(hierarchies=[]),cases=[]);records=[]
for identifier,candidates in [('D-1',first),('D-2',[normal,changed])]:
    db=root/(identifier+'.db');assert not db.exists()
    with sqlite3.connect(source_db.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(db) as target:source.backup(target)
    service=KnowledgeService(db);trial=deepcopy(run);calls=[]
    try:
        blocks=a2.load_blocks(service,trial);by_id={b['id']:b for b in blocks};contexts=profile.contexts(blocks)
        for c in candidates:
            for e in c['evidence_refs']:
                b=by_id[e['block_id']];assert b['text'][e['span'][0]:e['span'][1]]==e['quote']
                assert b['source_version_id']==e['source_version_id'] and b['parse_run_id']==e['parse_run_id']
        group=dict(id='o1_'+identifier,candidates=deepcopy(candidates),primary_candidate_ids=[c['id'] for c in candidates],
            design_candidates=[],design_candidate_ids=[],builder_tool_context=dict(terms={}),analysis_group_ids=[],round=0,status='review_issues_generated')
        context,deps,supplied=synthesis.review_context(trial,group,package['taxonomy'],by_id,contexts)
        batches=synthesis.review_batches(context,deps,supplied,by_id,contexts);assert len(batches)==1
        batch=batches[0];context,deps,supplied=batch['context'],batch['dependency_ids'],batch['supplied']
        assert context['review_focus']=='observations' and context['review_scope']['missing_meanings_allowed'] is False
        # Keep candidate fingerprints identical to their persisted group records.
        assert all(supplied[c['id']]==c for c in group['candidates'])
        assert synthesis.fits(trial,'critic',context,deps,supplied)
        async def capture(instance,prompt,**kwargs):
            assert len(prompt)<=trial['recipe']['input_chars']
            assert len(prompt.encode())+kwargs['num_predict']<=kwargs['num_ctx']
            calls.append(dict(component='observations',key=trial['analysis_units'][-1]['group_id'],prompt_sha256=sha256(prompt.encode()).hexdigest(),
                schema_sha256=profile.digest(kwargs['response_schema']),model_options={k:kwargs[k] for k in ('model','temperature','num_ctx','num_predict','think')},
                prompt_chars=len(prompt),prompt_utf8_bytes=len(prompt.encode()),conservative_context_bound=len(prompt.encode())+kwargs['num_predict']))
            (root/('prompt_'+identifier+'.txt')).write_text(prompt);write(root/('schema_'+identifier+'.json'),kwargs['response_schema'])
            raise ValueError('preflight only; HTTP 0')
        with patch.object(GenerationService,'call_ollama',capture),patch.object(a2,'model_identity',lambda _:run['model_identity']):
            synthesis.focused_reviews(service,trial,group,context,deps,supplied,by_id,contexts,blocks=blocks)
        assert len(calls)==1 and not any(u['status']=='succeeded' for u in trial['analysis_units'])
        package['cases'].append(dict(id=identifier,split_review=True,group=group,context=context,deps=deps,supplied=supplied,components=calls))
        records.append(dict(case=identifier,calls=calls,candidate_ids=group['primary_candidate_ids'],
            primary_source_spans=context['review_scope']['primary_source_spans'],source_views=[dict(block_id=v['ref'],span=v.get('span'),chars=len(v['text'])) for v in segments.originals(context)]))
    finally:service.shutdown()
write(root/'diagnostic_inputs.json',package)
write(root/'preflight.json',dict(actual_model_calls=0,recipe=run['recipe'],cases=records,originals=[ref(parent_path),ref(d5_path),ref(source_db)],
    evaluation_variant=dict(original_id=normal['id'],copy_id=changed['id'],changed_fields=['id','definition'],old_clause=old_clause,new_clause=new_clause,
        original_definition=normal['definition'],changed_definition=changed['definition'],not_new_generation=True,not_unseen_holdout=True),
    note='Original candidate/source files unchanged. Original candidate citation handles retained; current source handles are bound separately. Expected judgments are absent from generation input.',
    adjacent_definition='D5 source span [820,1112] contains neighboring public housing district definition; it is preserved as source, not attributed to the profit-sharing housing definition.'))
print(json.dumps(records,ensure_ascii=False,indent=2))

proof=[]
for case in ('D-1','D-2'):
    for name in ('prompt_'+case+'.txt','schema_'+case+'.json'):
        previous=Path('data/knowledge/semantic_o1_preflight_20261003')/name
        current=root/name
        assert previous.read_bytes()==current.read_bytes(),name
        proof.append(dict(name=name,sha256=ref(current)['sha256'],identical=True))
write(root/'wire_equivalence.json',dict(actual_model_calls=0,files=proof))
