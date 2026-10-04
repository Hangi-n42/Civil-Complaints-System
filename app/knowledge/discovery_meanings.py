"""Immutable source meanings and separate representation receipts, not a truth engine."""
from copy import deepcopy
from typing import Literal

from pydantic import Field

from .discovery_models import Record
from . import discovery_profile as profile, discovery_scope as scope, discovery_review as reviews

CONTRACT = 'grounded-meanings-v1'


class SourceMeaning(Record):
    local_ref: str
    meaning: str
    applies_to: str
    relation_kind: Literal['definition','obligation','authority','reference','comparison','identity','inheritance','other']
    conditions: str
    exceptions: str
    time: str
    negation: Literal['affirmed','negated']
    applicability: Literal['required','not_applicable','unknown']
    source_status: Literal['supported','refuted','unknown']
    source_refs: list[str]
    missing_source: str
    availability: Literal['provided','internal_unselected','external_missing','capacity','ambiguous']
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


OUTPUTS = dict(grounding=Grounding, representation=Representation, join=Join)
PROMPTS = dict(
    grounding='''원문 근거 판단만 수행한다. 현재 생성 후보와 그 표현 유무는 제공되지 않는다. 업무 요구는 사실 근거가 아니다.
원문이 직접 뒷받침하는 의미, 필요한 문서 간 연결, 참조 사실과 외부 상세를 별개 의미로 분해하라.
공통 단어/행위만으로 동일성이나 법적 상속을 확정하지 않는다. 특정 관계의 성립에 반드시 필요한 AND 전제만 premise_refs로 연결한다.
OR/예외/부정은 한 복합 의미 본문에 보존하며 양쪽을 AND 전제로 만들지 않는다. 전제 목록이 충분한 이유를 reason에 쓰고 불명확하면 premises_complete=false.
원문에 있는 의무/권한/참조 사실은 외부 상세 미제공과 별개로 지지할 수 있다. unknown을 refuted로 바꾸지 않는다.
가설을 반박한 것과 모든 경우의 부정 증명을 구분한다. 참조 상세 미제공은 external_missing, 읽어도 판정 불가는 ambiguous.
local_ref는 이번 응답에서 유일하며 premise_refs는 이번 local_ref 또는 제공된 meaning_key만 사용한다.
검토할 가설은 근거가 아니다. 모든 원문 구간을 검토해 examined_source_refs에 기록한다.
source_challenge 재판정 시 해당 의미와 직접 의존 전제만 수정하며 기존 의미를 교체하면 supersedes에 그 meaning_key를 적는다.''',
    representation='''고정된 원문 판정과 현재 후보 표현을 같은 의미키로 대조한다. 원문 판정을 조용히 뒤집지 않는다.
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
    value={k:deepcopy(row[k]) for k in ('meaning','applies_to','relation_kind','conditions','exceptions','time','negation')}
    value['requirement']=deepcopy(requirement)
    value['source_addresses']=sorted((dict(source_version_id=e['source_version_id'],parse_run_id=e['parse_run_id'],block_id=e['block_id'],span=e['span']) for e in row.get('evidence_refs',[])),key=profile.digest)
    return value


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
        if not row['meaning'].strip() or not row['applies_to'].strip(): raise ValueError('의미와 적용 범위 필요')
        if row['source_status']!='unknown' and not row.get('evidence_refs'): raise ValueError('원문 지지/반증에는 실제 근거 필요')
        if row['availability']=='external_missing' and not row['missing_source'].strip(): raise ValueError('외부 자료 부재에는 구체 자료명 필요')
        if row['availability']!='external_missing' and row['missing_source']: raise ValueError('제공/모호/용량 상태를 외부 자료 부재로 표시할 수 없음')
        if not row['reason'].strip(): raise ValueError('원문 판정 이유 필요')
        if row['supersedes'] and row['supersedes'] not in previous: raise ValueError('범위 밖 이전 의미 교체')
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


def representation(output,context,supplied):
    known={m['meaning_key']:m for m in context['source_assessment']['meanings']}
    keys=[c['meaning_key'] for c in output['checks']]
    if len(keys)!=len(set(keys)) or set(keys)!=set(known): raise ValueError('표현 대조 의미키 누락/중복/범위 밖')
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


def join(output,context):
    known={m['meaning_key']:m for m in context['meanings']}
    keys=[c['meaning_key'] for c in output['connections']]
    if len(keys)!=len(set(keys)) or set(keys)!=set(known): raise ValueError('결합 검수 의미키 누락/중복/범위 밖')
    challenges(output,known)
    return output
