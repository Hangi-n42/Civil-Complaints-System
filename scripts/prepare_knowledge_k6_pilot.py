"""Prepare manually reviewed schema and proposed K6 facts; never activate.

Reuses the existing local K5 snapshot and parsed pilot blocks. Output fact IDs must be
reviewed through the normal decisions API before creating explicit test snapshots.
This is manual development curation, not a measurement of automatic extraction.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.core.config import settings
from app.knowledge import ontology_schema as ontology, extraction_store as store, extraction, snapshots
from app.knowledge.service import KnowledgeService, encode, utcnow

ACTOR='codex-source-review'
NOTE='K6 개발용 원문 대조 보충; AI 검수이며 현업 인간 승인이 아님'


def prepare():
    with sqlite3.connect(settings.KNOWLEDGE_DB_PATH) as db:
        if any(json.loads(r[0]).get('status') in {'running','queued','cancel_requested'} for r in db.execute('SELECT payload FROM runs')):
            raise ValueError('진행 중인 지식 작업 종료 후 실행하세요.')
    service=KnowledgeService(settings.KNOWLEDGE_DB_PATH)
    try:
        with service.repository.connect() as db:
            snapshot=service.repository.get(db,'snapshots','8fc330a1085f44b4813466e015fdd549')
            all_blocks={r['id']:json.loads(r['payload']) for r in db.execute('SELECT id,payload FROM blocks')}
        def block(i):return all_blocks[i]
        pdf=block('5950d00be00d4c9ab94b143d2f4b8bf3')
        doc=[block(i) for i in ['9202618cb6ac4e11918a2b27d4bac9fd','def60355511a43fb86e5ee6728e70ea0','4c43cac77de543f49b73f156c6cadcbb']]
        question=block('8aa71308fa384096ab963ea2951960c0');qa=block('83c7d7c19531474c90249915a6c6b4ef')
        csv=block('d31d60424a5b49ea97ee11d20788e39f')
        def definition(i,kind,name,description,b,domain=None,range='string'):
            return dict(id=i,kind=kind,name=name,definition=description,inclusion=description,
                exclusion='문서 범위 밖의 개인 자격·실시간 상태는 제외',domain_id=domain,range=range,
                required=False,multivalued=False,enum_values=[],evidence=[dict(evidence_id=b['evidence_id'],quote=b['text'])],cq_ids=['K6-SOURCE'])
        candidates=[definition('BuildingCount','attribute','동수','자료에 명시한 건물 동수',pdf,'CONCEPT_001','integer'),
            definition('EligibilityType','concept','우선공급 자격 유형','문서 해당 행의 우선공급 자격 유형',doc[0]),
            definition('RequiredDocument','concept','제출서류','해당 자격에서 안내한 제출서류',doc[1]),
            definition('IssuingBody','concept','발급기관','해당 서류의 문서상 발급처',doc[2]),
            definition('RequiresDocument','relation','필요 서류','해당 자격 유형에서 안내하는 서류',doc[1],'EligibilityType','RequiredDocument'),
            definition('IssuedBy','relation','발급기관','해당 서류의 안내상 발급처',doc[2],'RequiredDocument','IssuingBody'),
            definition('QAItem','concept','Q&A 항목','등록 문서 안의 번호가 있는 질문과 설명',question),
            definition('QAExplanation','attribute','설명','Q&A 원문이 제시한 조건을 포함한 설명',qa,'QAItem')]
        run=dict(id=uuid4().hex,kind='ontology',origin='manual',status='succeeded',units=[],
            base_ontology_version_id=snapshot['ontology_version_id'],frozen_blocks=[pdf,*doc,question,qa],
            cqs=[dict(id='K6-SOURCE',question='자료에 명시된 대상·수량·필요 서류·발급기관·Q&A 설명을 어떻게 보존하는가?')],
            input_version_ids=sorted({b['source_version_id'] for b in [pdf,*doc,question,qa]}),
            metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0),started_at=utcnow(),finished_at=utcnow())
        with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
        published=ontology.publish(service,run,candidates)
        # Definition choices below were explicitly reviewed against the frozen original blocks.
        reviewed=ontology.decide(service,published['changeset_id'],dict(expected_changeset_revision=0,actor=ACTOR,
            decisions=[dict(candidate_id=c['id'],action='accept',reason=NOTE) for c in candidates]))
        oid=reviewed['reviewed_ontology_version_id']; schema=ontology.get_ontology(service,oid)
        results={}
        def publish(name,blocks,entities,links,assertions,evidence):
            blocks=list({b['id']:b for b in blocks}.values())
            run=dict(id=uuid4().hex,kind='extract',origin='manual',status='succeeded',units=[],ontology_version_id=oid,
                ontology_candidates=schema['candidates'],frozen_blocks=blocks,entities=entities,
                input_version_ids=sorted({b['source_version_id'] for b in blocks}),
                metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0),started_at=utcnow(),finished_at=utcnow(),review_note=NOTE)
            with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(run['id'],encode(run)))
            result=store.publish_unit(service,run,{'id':'manual-source-replay'},links,assertions,evidence,entities)
            run['changeset_id']=result['changeset_id']
            with service.repository.connect() as db:service.repository.save(db,'runs',run)
            results[name]=dict(run_id=run['id'],changeset_id=result['changeset_id'],ontology_version_id=oid,
                counts=result['counts'],source_version_ids=run['input_version_ids'])
        # Revalidate only A-5 quantity/type facts against their frozen original blocks.
        entity=next(e for e in snapshot['entities'].values() if e.get('official_id')=='C02748')
        old=[a for a in snapshot['assertions'].values() if a.get('subject_id')==entity['id'] and a['predicate_id'] in {'ATTRIBUTE_003','ATTRIBUTE_004'}]
        links=[deepcopy(snapshot['links'][i]) for i in sorted({a['subject_link_id'] for a in old})]
        mapping={l['id']:uuid4().hex for l in links}
        for l in links:l.update(id=mapping[l['id']],local_candidate_key=uuid4().hex)
        assertions=deepcopy(old)
        for a in assertions:a.update(id=uuid4().hex,local_candidate_key=uuid4().hex,subject_link_id=mapping[a['subject_link_id']],ontology_version_id=oid,origin='manual-source-replay')
        ev_ids=set().union(*(snapshots._evidence_ids(a) for a in [*old,*links])) | set(entity['evidence_ids'])
        evs=[snapshot['evidence'][i] for i in ev_ids]; blocks=[all_blocks[e['block_id']] for e in evs]
        for b,raw,quote,unit in [(pdf,'5개동','5개동','개동'),(csv,'6','동수: 6','동')]:
            link=next(l for l in links if l['scope'].get('source_version_id')==b['source_version_id'])
            ev=extraction.align(b,quote);evs.append(ev);blocks.append(b)
            assertions.append(dict(id=uuid4().hex,local_candidate_key=uuid4().hex,subject_link_id=link['id'],object_link_id=None,
                predicate_id='BuildingCount',value=5 if b==pdf else 6,raw_value=raw,unit=unit,
                scope=dict(source_version_id=b['source_version_id'],description='PDF 단지 현황의 동수' if b==pdf else 'CSV 단지정보의 동수'),
                evidence_ids=[ev['id']],field_evidence=dict(value=[ev['id']],scope=[ev['id']]),ontology_version_id=oid,origin='manual'))
        # PDF column role comes from its same-table headers; preserve them in frozen input.
        blocks += [b for b in all_blocks.values() if extraction.contract.table_key(b)==extraction.contract.table_key(pdf) and b['locator'].get('row')==0]
        publish('DEV-03',blocks,[entity],links,assertions,evs)
        # General document identity is registered through the same public service as the UI.
        local=[]
        for concept,b,name in [('EligibilityType',doc[0],doc[0]['text']),('RequiredDocument',doc[1],doc[1]['text']),('IssuingBody',doc[2],doc[2]['text']),('QAItem',question,'Q7')]:
            local.append(store.register_local_entity(service,dict(ontology_version_id=oid,concept_id=concept,name=name,
                source_version_id=b['source_version_id'],evidence_ids=[b['evidence_id']],actor=ACTOR,reason=NOTE)))
        def link_for(e,b):
            return dict(id=uuid4().hex,local_candidate_key=uuid4().hex,mention=e['name'],concept_id=e['concept_id'],target_entity_id=e['id'],
                method='manual',scope={'source_version_id':b['source_version_id']},evidence_ids=[b['evidence_id']])
        links=[link_for(e,b) for e,b in zip(local[:3],doc)]
        facts=[]
        for index,predicate in enumerate(['RequiresDocument','IssuedBy']):
            ids=[b['evidence_id'] for b in doc]
            facts.append(dict(id=uuid4().hex,local_candidate_key=uuid4().hex,subject_link_id=links[index]['id'],object_link_id=links[index+1]['id'],
                predicate_id=predicate,value=None,scope={'source_version_id':doc[0]['source_version_id'],'description':doc[0]['locator']['table_caption']},
                conditions=['중소기업근로자 우선공급 안내 해당 행'],exceptions=[],evidence_ids=ids,
                field_evidence=dict(object=[doc[index+1]['evidence_id']],scope=ids,conditions=ids),ontology_version_id=oid,origin='manual'))
        headers=[b for b in all_blocks.values() if extraction.contract.table_key(b)==extraction.contract.table_key(doc[0]) and b['locator'].get('row')==0]
        publish('NEW-01',doc+headers,local[:3],links,facts,[])
        link=link_for(local[3],question)
        fact=dict(id=uuid4().hex,local_candidate_key=uuid4().hex,subject_link_id=link['id'],object_link_id=None,predicate_id='QAExplanation',
            value=qa['text'],raw_value=qa['text'],scope={'source_version_id':qa['source_version_id'],'description':'2026 LH Q&A 임대주택 Q7의 설명'},
            evidence_ids=[qa['evidence_id']],field_evidence={'value':[qa['evidence_id']],'scope':[qa['evidence_id']]},ontology_version_id=oid,origin='manual')
        publish('NEW-02',[question,qa],[local[3]],[link],[fact],[])
        return dict(origin='manual-source-review',human_domain_expert_reviewed=False,active_snapshot_unchanged=snapshot['id'],tasks=results)
    finally:service.shutdown()


if __name__=='__main__':
    result=prepare();out=ROOT/'data/knowledge/pilot_v1/k6_prepared.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
