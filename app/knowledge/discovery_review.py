"""Per-record Critic validity shared by completion, revision and A3 conversion."""
from collections import Counter
from copy import deepcopy
from uuid import uuid4

from pydantic import ValidationError

from . import discovery_models as models, discovery_profile as profile, discovery_segments as segments


def fingerprint(candidate):
    return profile.digest({k:v for k,v in candidate.items() if k not in {'origin_dependency_ids','analysis_group_id'}})


def valid_ids(review, candidates=None):
    coverage = review.get('review_coverage')
    if coverage is None: return None  # Stored legacy reviews retain their original contract.
    valid = set(coverage['valid_candidate_ids'])
    if candidates is not None:
        valid = {i for i in valid if i in candidates and coverage['candidate_hashes'].get(i)==fingerprint(candidates[i])}
    return valid


def normalize(output, run, deps, by_id, supplied, context, normalize_hierarchy):
    expected = {i:c for i,c in supplied.items() if c.get('review_status')!='reviewed'}
    relations = {c['id'] for c in context.get('unapproved_relations', [])}
    hierarchies = {(h['child_ref'],h['parent_ref'],h['relation']):h['id']
                   for h in context.get('taxonomy', {}).get('hierarchies', [])}
    provided = segments.originals(context)
    pending, errors, issue_ids = set(), [], {}
    local_refs = [i.get('local_ref') for i in output['issues'] if isinstance(i,dict) and i.get('local_ref')]
    if len(local_refs)!=len(set(local_refs)):
        raise ValueError('응답 내부 쟁점 local_ref 중복')

    def problem(section, index, raw, reason, targets):
        pending.update(set(targets) & expected.keys())
        errors.append(dict(section=section,index=index,record=deepcopy(raw),reason=reason,candidate_ids=sorted(targets)))

    for section, model in [('issues',models.Issue), ('relation_checks',models.RelationCheck),
                           ('hierarchy_checks',models.Hierarchy), ('missing_meanings',models.MissingMeaning)]:
        records = output[section]
        def key(record):
            fields = ('child_ref','parent_ref','relation') if section=='hierarchy_checks' else ('candidate_ref',)
            values = tuple(record.get(f) if isinstance(record.get(f),str) else None for f in fields)
            return values if section=='hierarchy_checks' else values[0]
        counts = Counter(key(r) for r in records if isinstance(r,dict))
        accepted = []
        for index, raw in enumerate(records):
            target = key(raw) if isinstance(raw,dict) else None
            identifier = hierarchies.get(target) if section=='hierarchy_checks' else target
            targets = {identifier} if identifier in expected else set(expected) if section=='issues' and not identifier else set()
            try:
                item = model.model_validate(raw).model_dump()
                segments.restore(item, by_id, provided)
                if section in {'relation_checks','hierarchy_checks'} and counts[target]!=1:
                    raise ValueError('중복 검토 대상; 어느 판정도 선택하지 않음')
                if section=='issues':
                    if item['candidate_ref'] and item['candidate_ref'] not in supplied:
                        raise ValueError('검토 대상 후보 참조 불일치')
                    if not item['evidence_ids'] and not item['counter_evidence_ids'] and not item['defer_reason'].strip():
                        raise ValueError('근거 없는 쟁점에는 명시적 보류 사유 필요')
                    item['id']='di_'+uuid4().hex
                    issue_ids[item['local_ref']]=item['id']
                elif section=='relation_checks':
                    if item['candidate_ref'] not in relations:
                        raise ValueError('이번 관계 검토 대상 밖 ID')
                    if item['judgment']!='unknown' and not (item['quote'] or item.get('evidence_refs')):
                        raise ValueError('관계 판단에는 원문 인용 필요')
                    if item['quote'] and not item.get('source_refs'):
                        refs, problems = segments.references(dict(evidence_ids=[item['evidence_id']],
                            source_quotes=[dict(evidence_id=item['evidence_id'],quote=item['quote'])]), by_id, provided)
                        if problems: raise ValueError('; '.join(problems))
                        item['evidence_refs']=refs
                elif section=='hierarchy_checks':
                    if target not in hierarchies: raise ValueError('제안하지 않은 계층 검토')
                    # The existing Builder validation checks kind/direction/evidence contracts.
                    checked=normalize_hierarchy({'hierarchies':[item]}, 'builder', run, deps, by_id, supplied)['hierarchies'][0]
                    if checked['validation']: raise ValueError('; '.join(checked['validation']))
                    item=checked
                    item['id']=identifier
                else:
                    refs, problems = segments.references(item, by_id, provided)
                    if not item['source_quotes'] and not item['source_refs']: problems.append('누락 복구의 정확한 원문 구절 필요')
                    if not item['cq_ids'] and not item['scope_item_ids'] or item['outside_scope_reason']: problems.append('복구의 허용 질문/범위 연결 필요')
                    if not set(item['cq_ids']) <= {q['id'] for q in run['cqs']} or not set(item['scope_item_ids']) <= {q['id'] for q in run['scope_items']}: problems.append('복구의 허용 질문/범위 밖 연결')
                    if problems: raise ValueError('; '.join(problems))
                    item.update(evidence_refs=refs,validation=[])
                accepted.append(item)
            except (ValidationError, ValueError, KeyError, TypeError) as exc:
                problem(section,index,raw,str(exc),targets)
        output[section]=accepted
        if section in {'relation_checks','hierarchy_checks'}:
            required = relations if section=='relation_checks' else set(hierarchies.values())
            covered = {c['candidate_ref'] if section=='relation_checks' else c['id'] for c in accepted}
            for identifier in sorted(required-covered-pending):
                problem(section,None,None,'필수 관계/계층 검토 누락',{identifier})
    actions=[]
    previous={i['id'] for u in run.get('analysis_units', []) if u['status']=='succeeded' for i in u.get('output', {}).get('issues', [])}
    for index, action in enumerate(output['actions']):
        if action['action']=='request_evidence':
            identifier=issue_ids.get(action['issue_id'],action['issue_id'])
            if identifier not in set(issue_ids.values()) | previous:
                problem('actions',index,action,'유효한 쟁점 없는 근거 요청',set())
                continue
            action['issue_id']=identifier
        actions.append(action)
    # Conflicting/invalid judgments never drive a revision or recovery through another record.
    output['issues']=[i for i in output['issues'] if i['candidate_ref'] not in pending and not (pending and not i['candidate_ref'])]
    output['relation_checks']=[i for i in output['relation_checks'] if i['candidate_ref'] not in pending]
    output['hierarchy_checks']=[i for i in output['hierarchy_checks'] if i['id'] not in pending]
    valid_issue_ids={i['id'] for i in output['issues']} | previous
    output['actions']=[a for a in actions if a['action']!='request_evidence' or a['issue_id'] in valid_issue_ids]
    output['record_errors']=errors
    output['review_coverage']=dict(expected_candidate_ids=sorted(expected),valid_candidate_ids=sorted(expected.keys()-pending),
        pending_candidate_ids=sorted(pending),candidate_hashes={i:fingerprint(c) for i,c in expected.items()})
    return output
