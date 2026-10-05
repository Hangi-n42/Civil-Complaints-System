"""Immutable source meanings and separate representation receipts, not a truth engine."""
from copy import deepcopy
from typing import Any, Literal

from pydantic import Field

from .discovery_models import Record, Relation
from . import discovery_profile as profile, discovery_scope as scope, discovery_review as reviews

CONTRACT = 'grounded-meanings-v1'


class SourceMeaning(Record):
    local_ref: str
    meaning: str
    applies_to: str
    statement_type: Relation.model_fields['statement_type'].annotation = 'unresolved'
    judgment_kind: Literal['source_content','case_application','derived_link'] = 'source_content'
    local_negation: str = ''
    relation_kind: Literal['definition','obligation','authority','reference','comparison','identity','inheritance','other']
    conditions: str
    exceptions: str
    time: str
    negation: Literal['affirmed','negated']
    applicability: Literal['required','not_applicable','unknown'] = Field(description='현재 질문에서 표현해야 하는 의미인지. 구체 사례의 규칙 적용 조건 충족 여부와 다름.')
    source_status: Literal['supported','refuted','unknown']
    source_refs: list[str]
    missing_source: str = Field(description='미제공 자료의 실제 문서명/조항명. 상태값이나 none이 아님; 해당 없으면 빈 문자열.')
    availability: Literal['provided','internal_unselected','external_missing','capacity','ambiguous']
    read_block_ids: list[str] = Field(default_factory=list)
    premise_refs: list[str]
    premises_complete: bool
    reason: str
    supersedes: str = ''


class Grounding(Record):
    meanings: list[SourceMeaning] = Field(min_length=1, max_length=32)
    examined_source_refs: list[str]
    reason: str


class Location(Record):
    candidate_ref: str
    field: Literal['definition','subject','predicate','object','conditions','exceptions','time','negation','structure','role_source']


class Challenge(Record):
    meaning_key: str
    reason: str
    proposed_meaning: str
    source_refs: list[str]


class Expression(Record):
    meaning_key: str
    status: Literal['represented','missing','incorrect','unknown']
    assertion: Literal['asserted','qualified_unknown','negated','absent']
    locations: list[Location]
    repair_fields: list[str]
    preserve_keys: list[str]
    role: Literal['concept','relation']
    reason: str


class Representation(Record):
    checks: list[Expression]
    source_challenges: list[Challenge]
    reason: str


class Connection(Record):
    meaning_key: str
    premises_complete: bool
    scope_consistent: bool
    expression_consistent: bool
    reason: str


class Join(Record):
    connections: list[Connection]
    source_challenges: list[Challenge]
    reason: str


class GroundingEnvelope(Grounding):
    meanings: list[Any] = Field(min_length=1, max_length=32)


class RepresentationEnvelope(Representation):
    checks: list[Any]
    source_challenges: list[Any]


class JoinEnvelope(Join):
    connections: list[Any]
    source_challenges: list[Any]


OUTPUTS = dict(grounding=Grounding, representation=Representation, join=Join)
ENVELOPES = dict(grounding=GroundingEnvelope, representation=RepresentationEnvelope, join=JoinEnvelope)
PROMPTS = dict(
    grounding='''원문 근거 판단만 수행한다. 한 항목은 하나의 판정 대상이다.
필드 책임: applicability는 이 질문에 답하기 위해 표현해야 하는 의미인지다(required=필요, not_applicable=질문 밖, unknown=관련성 불명). 외부 상세 미확정이나 실제 사례 조건 미확인은 필요한 의미를 질문 밖으로 만들지 않는다. applies_to에는 실제 원문의 대상·업무·범위를 쓰며 질문 ID만 쓰지 않는다.
relation_kind는 주된 관계 뜻이다: definition=대상 정의, obligation=의무, authority=권한/허용, reference=다른 자료를 참조하는 사실, comparison=대비, identity=대상 동일성, inheritance=범위 포함, other=그 밖. 분류값은 설명문과 일치해야 하고 단어/참조자료가 같다는 이유로 identity가 아니다.
missing_source는 필요한 실제 문서명/조항명이다. external_missing 같은 상태값은 availability에만 쓴다. 알려진 내부 block_id가 있으면 외부 미제공으로 표시하지 않는다.
supersedes는 실제 제공된 이전 meaning_key를 바꾸는 경우만 그 키이며 최초 판정/교체 없음은 빈 문자열이다. none/null 같은 문자열이나 새 local_ref를 이전키로 쓰지 않는다.
정의 속 자격 한정과 주체별 조건·예외는 의미 본문 또는 조건에 보존한다. 근거 주소에 조건 문장이 있다는 이유만으로 결과에서 생략하지 않는다. reason은 원문과의 대응/공백만 짧게 쓴다.
judgment_kind를 먼저 구분한다: source_content는 원문이 정한 정의/규칙의 내용, case_application은 특정 사례 사실이 규칙의 조건을 충족하는지, derived_link는 여러 의미에서 도출하는 연결이다. 실제 사례 입력이 없는데 규칙 내용을 사례 적용 문제로 바꾸지 않는다.
statement_type은 기존 원명제의 definition/rule/instance/design_proposal/unresolved 구분이다. 원명제 단서가 있더라도 미승인 해석이며 원문과 대조한다.
source_content의 조건부 의무/권한은 조건을 conditions에 보존한 규칙 자체를 판단한다. 그 규칙의 존재와 특정 사례에서 조건 충족/외부 세부기준의 내용은 별개의 판정 대상이다. 참조된 상세 내용이 없으면 상세만 별도 unknown으로 남긴다.
negation은 meaning의 주된 명제 극성, source_status는 그 명제가 원문으로 지지/반증/미확정인지다. 둘을 서로 변환하지 않는다. 긍정 정의/의무/허용은 affirmed이며 정의 안의 국소 부정이나 예외 문구를 명제 전체 부정으로 확대하지 않는다. local_negation에는 실제 부정 구절을 그대로 적고 없으면 빈 문자열로 둔다. source_refs에는 그 구절과 한정을 포함한다.
자료의 위치와 의미 충분성을 구분한다. input_inventory에 있는 자료를 외부 미제공이라고 하지 않는다. selected=false인 정확한 자료가 필요하면 internal_unselected/read_block_ids, 목록에 없고 필요한 외부자료가 특정되면 external_missing/missing_source, 원문을 읽고도 명제 성립을 못 정하면 ambiguous다. 제목 일치는 조문 내용의 증거가 아니다.
현재 생성 후보와 그 표현 유무는 제공되지 않는다. 업무 요구는 사실 근거가 아니다.
원문이 직접 뒷받침하는 의미, 필요한 문서 간 연결, 참조 사실과 외부 상세를 별개 의미로 분해하라.
공통 단어/행위만으로 동일성이나 법적 상속을 확정하지 않는다. 특정 관계의 성립에 반드시 필요한 AND 전제만 premise_refs로 연결한다.
OR/예외/부정은 한 복합 의미 본문에 보존하며 양쪽을 AND 전제로 만들지 않는다. 전제 목록이 충분한 이유를 reason에 쓰고 불명확하면 premises_complete=false.
원문에 있는 의무/권한/참조 사실은 외부 상세 미제공과 별개로 지지할 수 있다. unknown을 refuted로 바꾸지 않는다.
가설을 반박한 것과 모든 경우의 부정 증명을 구분한다. 참조 상세 미제공은 external_missing, 읽어도 판정 불가는 ambiguous. input_inventory의 내부 자료가 더 필요하면 internal_unselected와 정확한 block_id를 read_block_ids에 기록한다. 제목의 유사성만으로 문서 동일성을 확정하지 않는다.
local_ref는 이번 응답에서 유일하며 premise_refs는 이번 local_ref 또는 제공된 meaning_key만 사용한다.
검토할 가설은 근거가 아니다. 모든 원문 구간을 검토해 examined_source_refs에 기록한다.
source_challenge 재판정 시 해당 의미와 직접 의존 전제만 수정하며 기존 의미를 교체하면 supersedes에 그 meaning_key를 적는다.''',
    representation='''고정된 원문 판정과 현재 후보 표현을 같은 의미키로 대조한다. 원문 판정을 조용히 뒤집지 않는다.
원문 판정도 미승인 모델 결과다. relation_kind의 실제 관계 종류, 필수 조건/예외, applicability의 질문상 필요성, missing_source의 실제 자료명을 원문·질문과 대조하라. 오류를 발견하면 해당 키에 source_challenge를 제출하며, 형식 통과나 원문 주소만으로 기존 판단을 신뢰하지 않는다. applicability는 특정 사례의 조건 충족 여부가 아니다.
모든 meaning_key에 한 번씩 checks를 작성한다. 원문에 지지되는 정상 의미의 실제 표현 위치를 확인하고 빠진 경우 missing, 잘못 표현했으면 incorrect이다.
unknown 원문 의미는 확정 사실처럼 주장하는지(asserted), 적절히 미확정 표시했는지(qualified_unknown), 부정했는지(negated), 아예 없는지(absent)를 구분한다.
원문을 다시 읽어 판정 자체의 모순/새 필수 전제를 발견하면 source_challenges로 해당 키/이유/새 의미/근거를 제출한다. 원문판정의 supported는 표현의 supported가 아니다.
잘못된 위치와 수정할 필드만 지정하고, 같은 후보에서 유지할 독립 정상 의미키를 preserve_keys에 남긴다. 원문 문구와 동등한 표현은 누락이 아니다.
역할 참조만으로 외부 자격/권리나 법적 포함이 주장되었다고 간주하지 말고 실제 후보 필드를 읽는다. 후보 없으면 locations=[], assertion=absent이다.''',
    join='''업무 요구의 마지막 연결 검수다. 입력에는 관련 의미/전제/원문/표현 위치와 전체 조사 범위가 있다.
각 의미의 직접 전제, 관계 종류, 범위/시점, 실제 현재 표현을 다시 확인하라. 부분 supported 개수를 합산하지 않는다.
모든 의미키에 connections를 작성하되 독립 의미는 빈 전제도 가능하다. 새로운 필수 전제나 원문 판정 모순이면 source_challenges로 해당 키를 돌려보낸다.
자료 미제공으로 확정 불가한 연결은 그대로 유지한다. 전체 범위 미조사나 용량 부족을 자료 부재 또는 완료로 표시하지 않는다.''')


def enabled(run):
    return run.get('recipe',{}).get('meaning_contract') == CONTRACT


def body(row, requirement):
    value={k:deepcopy(row.get(k,SourceMeaning.model_fields[k].default)) for k in ('meaning','applies_to','relation_kind','conditions','exceptions','time','negation','statement_type','judgment_kind','local_negation')}
    value['requirement']=deepcopy(requirement)
    value['source_addresses']=sorted((dict(source_version_id=e['source_version_id'],parse_run_id=e['parse_run_id'],block_id=e['block_id'],span=e['span']) for e in row.get('evidence_refs',[])),key=profile.digest)
    return value


def validate_source(row, previous):
    if not row['meaning'].strip() or not row['applies_to'].strip(): raise ValueError('의미와 적용 범위 필요')
    if row['source_status']!='unknown' and not row.get('evidence_refs'): raise ValueError('원문 지지/반증에는 실제 근거 필요')
    if row['availability']=='external_missing' and (not row['missing_source'].strip() or row['missing_source'] in {'external_missing','provided','internal_unselected','capacity','ambiguous','none','null'}): raise ValueError('외부 자료 부재에는 구체 자료명 필요')
    if row['availability']=='external_missing' and row.get('read_block_ids'): raise ValueError('지정된 내부 원문 주소를 외부 미제공으로 표시할 수 없음')
    if row['availability']!='external_missing' and row['missing_source']: raise ValueError('제공/모호/용량 상태를 외부 자료 부재로 표시할 수 없음')
    if not row['reason'].strip(): raise ValueError('원문 판정 이유 필요')
    if row['supersedes'] and row['supersedes'] not in previous: raise ValueError('범위 밖 이전 의미 교체')


def grounding(output, context):
    examined=set(output['examined_source_refs']);expected=set(context['expected_source_refs'])
    if not examined<=expected: raise ValueError('근거 판정의 원문 조사 범위 밖 참조')
    if examined!=expected:
        from .discovery_segments import originals
        views=originals(context)
        def covered(view):
            start,end=view.get('span',[0,len(view['text'])])
            for a,b in sorted(v.get('span',[0,len(v['text'])]) for v in views if v['source_ref'] in examined and v['ref']==view['ref']):
                if a<=start: start=max(start,b)
            return start>=end
        if not views or not all(covered(v) for v in views): raise ValueError('근거 판정의 원문 조사 범위 누락')
    previous={m['meaning_key']:m for m in context.get('previous_meanings',[])}
    aliases={};rows=[]
    for row in output['meanings']:
        if not row['local_ref'] or row['local_ref'] in aliases: raise ValueError('의미 local_ref 누락/중복')
        validate_source(row,previous)
        canonical=body(row,context['requirement']);key='m_'+profile.digest(canonical)
        aliases[row['local_ref']]=key
        rows.append(dict(deepcopy(row),meaning_key=key,body=canonical))
    if len({m['meaning_key'] for m in rows})!=len(rows): raise ValueError('동일 의미 본문 중복')
    replaced={m['supersedes']:m['meaning_key'] for m in rows if m['supersedes']}
    supplied_keys={m['meaning_key'] for m in rows}
    rows += [deepcopy(m) for k,m in previous.items() if k not in replaced and k not in supplied_keys]
    known={m['meaning_key']:m for m in rows}
    for m in rows:
        refs=m.pop('premise_refs',m.get('premise_keys',[]))
        m['premise_keys']=[replaced.get(aliases.get(k,k),aliases.get(k,k)) for k in refs]
        m['validation']=[]
        if len(set(m['premise_keys']))!=len(m['premise_keys']) or any(k not in known for k in m['premise_keys']): m['validation'].append('없는/중복 전제')
    def acyclic(key,path):
        return key not in path and key in known and all(acyclic(k,path|{key}) for k in known[key]['premise_keys'])
    def supported(key,path):
        if key in path or key not in known: return False
        m=known[key]
        return not m['validation'] and m['premises_complete'] and m['source_status']=='supported' and all(supported(k,path|{key}) for k in m['premise_keys'])
    for m in rows:
        if not acyclic(m['meaning_key'],set()): m['validation'].append('순환/없는 전제')
        m['premises_current']=m['premises_complete'] and not m['validation'] and all(supported(k,set()) for k in m['premise_keys'])
        m['dependency_hash']=profile.digest({k:{f:known[k].get(f) for f in ('body','source_status','premise_keys','premises_complete')} for k in m['premise_keys'] if k in known})
    output['meanings']=rows
    output['source_fingerprint']=context['source_fingerprint']
    output['assessment_hash']=profile.digest([context['source_fingerprint'],rows])
    return output


def action(meaning, expression):
    """Only this table authorizes recovery; cause is not an LLM output."""
    if meaning['applicability']!='required': return 'not_applicable' if meaning['applicability']=='not_applicable' else 'refresh'
    if meaning.get('validation'): return 'refresh'
    status=meaning['source_status'];assertion=expression['assertion'];represented=expression['status']
    if status in {'unknown','refuted'}:
        if meaning.get('availability') in {'internal_unselected','capacity'}: return 'refresh'
        if assertion=='asserted': return 'correct'
        if status=='unknown': return 'gap' if assertion in {'absent','qualified_unknown'} else 'refresh'
        return 'refutation' if assertion in {'absent','negated'} else 'refresh'
    if not meaning.get('premises_current'): return 'refresh'
    if represented=='represented' and assertion==('negated' if meaning['negation']=='negated' else 'asserted'): return 'maintain'
    if represented=='missing' and assertion=='absent': return 'recover'
    if represented=='incorrect' and assertion!='absent': return 'correct'
    return 'refresh'


def representation(output,context,supplied,*,partial=False):
    known={m['meaning_key']:m for m in context['source_assessment']['meanings']}
    keys=[c['meaning_key'] for c in output['checks']]
    if len(keys)!=len(set(keys)) or not set(keys)<=set(known) or not partial and set(keys)!=set(known): raise ValueError('표현 대조 의미키 누락/중복/범위 밖')
    for check in output['checks']:
        if not set(check['preserve_keys'])<=known.keys(): raise ValueError('범위 밖 정상 보존 의미키')
        check['candidate_hashes']=scope.locations(dict(check,judgment='unknown',evidence_refs=known[check['meaning_key']].get('evidence_refs',[]),missing_source=known[check['meaning_key']]['reason']),supplied)
        if (check['assertion']=='absent') != (not check['locations']): raise ValueError('주장 상태와 실제 표현 위치 불일치')
        if check['status']=='represented' and not check['locations']: raise ValueError('표현 완료에는 현재 위치 필요')
        check['action']=action(known[check['meaning_key']],check)
        if check['action']=='correct' and (not check['repair_fields'] or not set(check['repair_fields'])<={p['field'] for p in check['locations']}):
            raise ValueError('부분 교정에는 잘못된 현재 필드 위치 필요')
        check['source_receipt']=deepcopy(context['source_receipt'])
    challenges(output,known)
    output['source_receipt']=deepcopy(context['source_receipt'])
    output['candidate_fingerprint']=profile.digest({i:reviews.fingerprint(c) for i,c in supplied.items()})
    return output


def challenges(output,known):
    for c in output['source_challenges']:
        if c['meaning_key'] not in known or not c['reason'].strip() or not c['proposed_meaning'].strip(): raise ValueError('범위 밖/빈 원문 재판정 요청')
        if not c.get('evidence_refs'): raise ValueError('원문 재판정에는 실제 원문 근거 필요')


def join(output,context,*,partial=False):
    known={m['meaning_key']:m for m in context['meanings']}
    keys=[c['meaning_key'] for c in output['connections']]
    if len(keys)!=len(set(keys)) or not set(keys)<=set(known) or not partial and set(keys)!=set(known): raise ValueError('결합 검수 의미키 누락/중복/범위 밖')
    challenges(output,known)
    return output


def records(decoded,context,supplied,by_id,unit_id):
    """Validate the envelope once, preserving independent records and their raw errors."""
    from collections import Counter
    from . import discovery_segments as segments
    mode=context['meaning_phase'];output=ENVELOPES[mode].model_validate(decoded).model_dump()
    if not output['reason']: raise ValueError('판정 이유 필요')
    field,model,key={'grounding':('meanings',SourceMeaning,'local_ref'),
        'representation':('checks',Expression,'meaning_key'),'join':('connections',Connection,'meaning_key')}[mode]
    if mode=='grounding':
        context=dict(context,expected_source_refs=[v['source_ref'] for v in segments.originals(context)])
        grounding(dict(output,meanings=[]),dict(context,previous_meanings=[]))  # Whole-source coverage is an envelope contract.
    errors=[];raw_rows=output[field];output[field]=[];canonical_keys=set()
    counts=Counter(r.get(key) for r in raw_rows if isinstance(r,dict) and isinstance(r.get(key),str))
    known={m['meaning_key']:m for m in context.get('source_assessment',{}).get('meanings',context.get('meanings',[]))}
    def failed(section,index,raw,error):
        errors.append(dict(id=profile.digest([unit_id,section,index,raw]),unit_id=unit_id,section=section,index=index,
            record=deepcopy(raw),reason=str(error)))
    for index,raw in enumerate(raw_rows):
        try:
            row=model.model_validate(raw).model_dump()
            if not row[key] or counts[row[key]]!=1: raise ValueError('의미 참조 누락/중복')
            segments.restore(row,by_id,segments.originals(context))
            if mode=='grounding':
                validate_source(row,{m['meaning_key']:m for m in context.get('previous_meanings',[])})
                inventory={b['block_id'] for b in context.get('input_inventory',[])}
                if not set(row['read_block_ids'])<=inventory: raise ValueError('추가 읽기 대상이 고정 입력 목록 밖')
                canonical=profile.digest(body(row,context['requirement']))
                if canonical in canonical_keys: raise ValueError('동일 의미 본문 중복')
                canonical_keys.add(canonical)
            elif mode=='representation': representation(dict(checks=[row],source_challenges=[]),context,supplied,partial=True)
            else: join(dict(connections=[row],source_challenges=[]),context,partial=True)
            output[field].append(row)
        except (ValueError,KeyError,TypeError) as error: failed(field,index,raw,error)
    if mode=='grounding':
        # Dependencies on rejected rows remain invalid; accepted syntax is not a truth judgment.
        output=grounding(output,context)
    else:
        challenges_raw=output['source_challenges'];output['source_challenges']=[]
        for index,raw in enumerate(challenges_raw):
            try:
                row=Challenge.model_validate(raw).model_dump();segments.restore(row,by_id,segments.originals(context))
                challenges(dict(source_challenges=[row]),known);output['source_challenges'].append(row)
            except (ValueError,KeyError,TypeError) as error: failed('source_challenges',index,raw,error)
        present={r[key] for r in output[field]}
        output['pending_meaning_keys']=sorted(known.keys()-present)
        if mode=='representation':
            output['source_receipt']=deepcopy(context['source_receipt'])
            output['candidate_fingerprint']=profile.digest({i:reviews.fingerprint(c) for i,c in supplied.items()})
    output['record_errors']=errors
    return output


def affected_keys(meanings,keys):
    """Only a challenged meaning and its dependents are blocked, not its siblings."""
    affected=set(keys)
    while True:
        more={m['meaning_key'] for m in meanings if set(m.get('premise_keys',[])) & affected}
        if more<=affected: return affected
        affected.update(more)


def blocked_keys(output,rows):
    keys=[c['meaning_key'] for c in output.get('source_challenges',[])]
    keys += [e['record'].get('meaning_key') for e in output.get('record_errors',[])
        if e['section']=='source_challenges' and isinstance(e['record'],dict)]
    return affected_keys(rows,keys)
