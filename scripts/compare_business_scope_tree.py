"""SG-DT-inspired finite scope diagnostic. Automatic structures are not ground truth."""
import argparse
import asyncio
from dataclasses import asdict
from itertools import product
from pathlib import Path
import sys
import json

from compare_business_nli import read, write, sha
from compare_business_natlogic import object_schema as obj, array_schema as arr

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/knowledge/evaluations/business_nli_20261009'
OUT=ROOT/'data/knowledge/evaluations/business_scope_tree_20261009'
MODEL='qwen3.8:27b-q4_K_M'
KINDS=['none','required_item','obligation','permission','prohibition','procedure','fact','other']
RELATIONS=['equivalent','source_implies_claim','claim_implies_source','disjoint','independent','unknown']
PARSE=(
    '주어진 각 문서를 서로 독립적으로 조건-효과 분기로 해석한다. 다른 문서나 외부 사실로 보완하거나 정정하지 않는다. '
    '원문에 연결된 SG-DT의 제한 변형이다. 최종 참거짓/지지 판정은 하지 않는다. '
    'atoms의 id는 반드시 document.id+":"로 시작하고 문서 전체에서 유일하다. kind는 condition/effect이다. '
    '각 atom은 실제 블록의 정확한 연속 인용 refs와 조건/효과의 의미 meaning을 가진다. '
    '인용에 없는 생략 주체를 만들지 않는다. 부모 제목이 조건이나 구비 맥락을 정하면 실제 부모 refs도 보존한다. '
    'condition은 적용 주체/전제/경우/시점의 Boolean 명제다. effect는 조건이 성립할 때의 행위/구비항목/사실이며 '
    '주체·행위·대상·수량·시점·순서·날인·양태 등 실제 한정 의미를 빠짐없이 유지한다. '
    '여러 구비항목의 포함/요구는 서로 다른 effect로 나눠 일부 항목만 말한 후보도 비교 가능하게 한다. '
    '구비품목(required_item), 의무(obligation), 허용(permission), 금지(prohibition), 절차(procedure), 사실(fact)를 구별한다. '
    '단순 구비품목에 반납/제출 등 원문에 없는 행위나 must를 보태지 않는다. 명시된 시간·순서는 효과 안에 보존한다. '
    'condition의 modality는 none, effect는 none이 아닌 실제 양태다. '
    'branches의 guard는 OR-of-AND이다. 바깥 배열의 각 항은 OR, 안의 literal들은 AND이다. '
    'literal은 condition atom의 id와 positive(true=명제성립,false=명제부정)이다. 조건없음은 [[]]다. '
    '조건 미해석을 빈조건으로 만들지 않는다. 각 branch effects에는 해당 guard가 적용되는 effect id만 넣는다. '
    '예외/부정은 실제 원문이 그 적용을 제외할 때에만 negative literal로 나타내며, 예외 밖에 원문 없는 효과를 만들지 않는다. '
    '조건부 의무는 조건 밖 면제/금지를 뜻하지 않는다. 명시 대체효과가 없으면 예외 branch의 효과를 발명하지 않는다. '
    '구비 문서 괄호의 조건/대체 대상도 그 항목에만 붙이며 다른 항목 전체로 퍼뜨리지 않는다. '
    '각 block은 coverage에 한번 나타내고 extracted/context/unresolved 및 이유를 남긴다. '
    '제목도 필요한 맥락으로 사용하고 참조/논리/양태를 보존할 수 없으면 status=unsupported, reason으로 남긴다. '
    '산술·복잡시간·미해석참조·중첩양태 등 이 Boolean 조건-효과로 보존 불가한 표현은 unsupported다. '
    '반드시 모든 실제 효과와 연결 조건을 포함하고 쓰지 않는 atom은 만들지 않는다. status=complete는 형식 선언일 뿐이다.')
ALIGN=(
    '자동 추출된 source와 claim 구조의 atom 의미만 대응시킨다. 구조/조건 귀속을 고치거나 최종 후보판정을 하지 않는다. '
    '조건 대응은 source condition에서 claim condition으로의 방향이다. equivalent는 양방향, '
    'source_implies_claim은 원문조건이 후보조건을 함의, claim_implies_source는 반대, disjoint는 양립불가, '
    'independent는 서로 제약 없는 별개 조건이다. 모호하면 unknown이다. 모든 원문-후보 condition 조합을 한번씩 출력한다. '
    'effects는 각 claim effect마다 모든 source effect id를 entails/opposes/unrelated/unknown 중 정확히 한 목록에 넣는다. '
    'entails는 조건을 제외한 효과 명제 자체에서 source가 claim을 함의할 때다. 조건 적용 여부는 이후 계산한다. '
    '효과 대응에는 주체·행위·대상·수량·시점·순서·양태·괄호 한정을 함께 보존한다. '
    '원문이 더 상세하고 후보가 참인 일부만 말한 경우 단방향 함의를 허용하되 구비와 의무를 자동 동치로 묶지 않는다. '
    'required_item에 반납의무를 보태거나 permission을obligation으로 바꾸지 않는다. '
    'opposes는 같은 대상/시점/의미에서 실제 명시적 부정/양태 충돌이 있을 때만이다. '
    '자료 부족, 다른 항목, 빠진 조건은 반증이 아니다. 원문 조건 밖 금지/면제를 만들지 않는다. '
    '모델이 파싱을 잘못한 것을 발견해도 정정하지 않고 unknown과 이유에 남긴다. 각 대응의 reason을 남긴다.')


def schemas():
    s={'type':'string'}
    ref=obj(dict(block_id=s,quote=s))
    atom=obj(dict(id=s,kind={'type':'string','enum':['condition','effect']},meaning=s,
        modality={'type':'string','enum':KINDS},refs=arr(ref)))
    literal=obj(dict(atom=s,positive={'type':'boolean'}))
    branch=obj(dict(id=s,guard=arr(arr(literal)),effects=arr(s)))
    doc=obj(dict(id=s,status={'type':'string','enum':['complete','unsupported']},reason=s,
        atoms=arr(atom),branches=arr(branch),coverage=arr(obj(dict(block_id=s,
        status={'type':'string','enum':['extracted','context','unresolved']},reason=s)))))
    mapping=obj(dict(condition_links=arr(obj(dict(source=s,claim=s,
        relation={'type':'string','enum':RELATIONS},reason=s))),
        effect_links=arr(obj(dict(claim=s,entails=arr(s),opposes=arr(s),unrelated=arr(s),unknown=arr(s),reason=s)))))
    return obj(dict(documents=arr(doc))),mapping


def validate(doc, original):
    if doc['status']!='complete': raise ValueError('parser_unsupported')
    blocks={b['id']:b['text'] for b in original['blocks']}
    covered=[x['block_id'] for x in doc['coverage']]
    if len(covered)!=len(blocks) or set(covered)!=set(blocks): raise ValueError('block_coverage')
    if any(x['status']=='unresolved' for x in doc['coverage']): raise ValueError('coverage_unresolved')
    atoms={a['id']:a for a in doc['atoms']}
    if len(atoms)!=len(doc['atoms']) or not atoms: raise ValueError('atom_ids')
    used=set()
    for a in atoms.values():
        if not a['id'].startswith(doc['id']+':') or not a['refs']: raise ValueError('atom_address')
        if (a['kind']=='condition') != (a['modality']=='none'): raise ValueError('modality_kind')
        for r in a['refs']:
            if r['block_id'] not in blocks or not r['quote'] or blocks[r['block_id']].count(r['quote'])!=1:
                raise ValueError('nonunique_or_absent_span')
    if not doc['branches']: raise ValueError('empty_branches')
    if len({b['id'] for b in doc['branches']})!=len(doc['branches']): raise ValueError('branch_ids')
    for b in doc['branches']:
        if not b['guard'] or not b['effects']: raise ValueError('empty_guard_or_effect')
        for term in b['guard']:
            for lit in term:
                if lit['atom'] not in atoms or atoms[lit['atom']]['kind']!='condition': raise ValueError('condition_reference')
                if type(lit['positive']) is not bool: raise ValueError('condition_polarity')
                used.add(lit['atom'])
        for e in b['effects']:
            if e not in atoms or atoms[e]['kind']!='effect': raise ValueError('effect_reference')
            used.add(e)
    if used!=set(atoms): raise ValueError('unused_atoms')
    return atoms


def active(guard, world):
    return any(all(world[x['atom']]==x['positive'] for x in term) for term in guard)


def relation_holds(link, world):
    a,b=world[link['source']],world[link['claim']]
    return {'equivalent':a==b,'source_implies_claim':not a or b,
        'claim_implies_source':not b or a,'disjoint':not(a and b),'independent':True}[link['relation']]


def compare(source, claim, mapping):
    sc={a['id'] for a in source['atoms'] if a['kind']=='condition'}
    cc={a['id'] for a in claim['atoms'] if a['kind']=='condition'}
    se={a['id'] for a in source['atoms'] if a['kind']=='effect'}
    ce={a['id'] for a in claim['atoms'] if a['kind']=='effect'}
    links=[x for x in mapping['condition_links'] if x['claim'] in cc]
    effects=[x for x in mapping['effect_links'] if x['claim'] in ce]
    if len(links)!=len(sc)*len(cc) or {(x['source'],x['claim']) for x in links}!=set(product(sc,cc)):
        raise ValueError('condition_mapping_coverage')
    if len(effects)!=len(ce) or {x['claim'] for x in effects}!=ce: raise ValueError('effect_mapping_coverage')
    if any(x['relation']=='unknown' for x in links): raise ValueError('condition_mapping_unknown')
    for e in effects:
        partition=sum((e[k] for k in ['entails','opposes','unrelated','unknown']),[])
        if len(partition)!=len(se) or set(partition)!=se: raise ValueError('effect_partition')
        if e['unknown']: raise ValueError('effect_mapping_unknown')
    ids=sorted(sc|cc)
    if len(ids)>12: raise ValueError('condition_capacity')
    worlds=[dict(zip(ids,bits)) for bits in product([False,True],repeat=len(ids))]
    worlds=[w for w in worlds if all(relation_holds(x,w) for x in links)]
    if not worlds: raise ValueError('inconsistent_conditions')
    trace=[]
    for b in claim['branches']:
        applicable=[w for w in worlds if active(b['guard'],w)]
        if not applicable: raise ValueError('vacuous_claim_guard')
        for cid in b['effects']:
            e=next(x for x in effects if x['claim']==cid)
            support=[s for s in source['branches'] if set(s['effects']) & set(e['entails'])]
            oppose=[s for s in source['branches'] if set(s['effects']) & set(e['opposes'])]
            covered=[w for w in applicable if any(active(s['guard'],w) for s in support)]
            conflicts=[w for w in applicable if any(active(s['guard'],w) for s in oppose)]
            if any(w in conflicts for w in covered): raise ValueError('inconsistent_effects')
            missing=[w for w in applicable if w not in covered]
            trace.append(dict(branch=b['id'],effect=cid,applicable_worlds=len(applicable),
                supported_worlds=len(covered),opposed_worlds=len(conflicts),supporting_branches=[s['id'] for s in support],
                scope_witness=missing[0] if missing else None,
                verdict='S' if not missing else 'R' if len(conflicts)==len(applicable) else 'N'))
    return dict(status='calculated',verdict='S' if all(t['verdict']=='S' for t in trace) else
        'R' if any(t['verdict']=='R' for t in trace) else 'N',world_count=len(worlds),trace=trace)


def freeze():
    assert not (OUT/'freeze.json').exists()
    packet=read(BASE/'source_packet.json');inputs=read(BASE/'inputs.json')
    write(OUT/'inputs.json',dict(source=dict(id='source',blocks=packet['blocks'],source_parents=packet['source_parents']),
        claims=[dict(id=p['id'],blocks=[dict(id=p['id'],text=p['hypothesis'])],source_parents=[]) for p in inputs]))
    write(OUT/'criteria.json',dict(expected=dict(c13='S',c46='S',c47='N',c11='S'),
        gate='All exact labels AND source-faithful automatic structures/mapping required; status complete is not semantic validation.',
        exposure='Four development-exposed cases; no downstream if failed.',
        failures='Unknown/unsupported/empty/contract failures stay in denominator, never counted as detected errors.'))
    sys.path.insert(0,str(ROOT))
    from app.generation.model_client import ModelClient
    identity=ModelClient(dict(provider='ollama',endpoint='http://localhost:11434')).identities({'review':MODEL},{'review':49152})
    write(OUT/'freeze.json',dict(model=MODEL,identity=identity,context_tokens=49152,max_tokens=12288,think=False,temperature=0,timeout=1800,
        maximum_calls=3,parse_instruction=PARSE,alignment_instruction=ALIGN,schemas=schemas(),condition_limit=12,
        reference_revision='bd56aff7eb9518db02b10e189576331f271564cc',reference_license='CC BY 4.0; independent diagnostic, no upstream code copied',
        method='SG-DT-inspired automatic source/claim parsing plus directional atom mapping and finite guard inclusion; not NormBench reproduction.',
        files={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'inputs.json',OUT/'criteria.json',BASE/'inputs.json',BASE/'source_packet.json',
            Path(__file__),ROOT/'scripts/compare_business_nli.py',ROOT/'scripts/compare_business_natlogic.py',
            ROOT/'app/generation/model_client.py',ROOT/'app/generation/service.py']}))


async def run():
    sys.path.insert(0,str(ROOT))
    from app.generation.model_client import ModelClient,ModelRequest
    f=read(OUT/'freeze.json'); data=read(OUT/'inputs.json')
    assert all(sha(ROOT/p)==v for p,v in f['files'].items())
    assert not (OUT/'started.json').exists()
    client=ModelClient(dict(provider='ollama',endpoint='http://localhost:11434'))
    assert client.identities({'review':MODEL},{'review':49152})==f['identity']
    write(OUT/'started.json',dict(freeze_sha256=sha(OUT/'freeze.json')))
    calls=[];result=dict(cases=[],gate_passed=False)
    async def call(stage,instruction,context,schema):
        req=ModelRequest(stage,MODEL,[dict(role='system',content=instruction),dict(role='user',content=json.dumps(context,ensure_ascii=False))],
            schema=schema,max_tokens=f['max_tokens'],context_tokens=f['context_tokens'],think=f['think'],timeout=f['timeout'])
        rec=dict(request=asdict(req)); calls.append(rec);write(OUT/'calls.json',calls)
        rec['response']=await client.generate(req);write(OUT/'calls.json',calls)
        print(stage,rec['response']['failure_kind'],rec['response']['elapsed_s'],flush=True)
        if rec['response']['failure_kind']: raise ValueError(rec['response']['failure_kind'])
        return rec['response']['parsed']
    try:
        parse_schema,mapping_schema=schemas()
        sources=await call('scope_parse_source',PARSE,dict(documents=[data['source']]),parse_schema)
        write(OUT/'source_structure.json',sources)
        claims=await call('scope_parse_claims',PARSE,dict(documents=data['claims']),parse_schema)
        write(OUT/'claim_structures.json',claims)
        if len(sources['documents'])!=1 or sources['documents'][0]['id']!='source': raise ValueError('source_coverage')
        source=sources['documents'][0]
        source_error=None
        try: validate(source,data['source'])
        except (ValueError,KeyError,TypeError) as exc: source_error=str(exc)
        valid=[]
        for original in data['claims']:
            record=dict(id=original['id'],status='pending',verdict=None);result['cases'].append(record)
            selected=[d for d in claims['documents'] if d['id']==original['id']]
            try:
                if source_error: raise ValueError('source:'+source_error)
                if len(selected)!=1: raise ValueError('claim_coverage')
                validate(selected[0],original);valid.append(selected[0])
            except (ValueError,KeyError,TypeError) as exc: record.update(status='unsupported_or_contract_failure',error=str(exc))
        # Preserve the fixed third request even when validation failed; invalid structures cannot pass calculation.
        mapping=await call('scope_map_atoms',ALIGN,dict(source=sources,claims=claims,
            original_source=data['source'],original_claims=data['claims']),mapping_schema)
        write(OUT/'atom_mapping.json',mapping)
        for claim in valid:
            record=next(r for r in result['cases'] if r['id']==claim['id'])
            try: record.update(compare(source,claim,mapping))
            except (ValueError,KeyError,TypeError) as exc: record.update(status='unresolved',error=str(exc))
        expected=read(OUT/'criteria.json')['expected']
        result['label_gate_passed']=len(result['cases'])==len(expected) and all(r['verdict']==expected[r['id']] for r in result['cases'])
        result['semantic_gate']='Pending raw structure and mapping review; not inferred from complete/status or label equality.'
    except (ValueError,KeyError,TypeError) as exc: result['execution_error']=str(exc)
    finally:
        present={r['id'] for r in result['cases']}
        result['cases'].extend(dict(id=x['id'],status='not_completed',verdict=None) for x in data['claims'] if x['id'] not in present)
        result['calls']=len(calls)
        result['cost']=dict(input_tokens=sum(c.get('response',{}).get('prompt_eval_count') or 0 for c in calls),
            output_tokens=sum(c.get('response',{}).get('eval_count') or 0 for c in calls),
            elapsed_s=sum(c.get('response',{}).get('elapsed_s') or 0 for c in calls))
        write(OUT/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run'])
    args=parser.parse_args();OUT.mkdir(exist_ok=True,parents=True)
    freeze() if args.mode=='freeze' else asyncio.run(run())
