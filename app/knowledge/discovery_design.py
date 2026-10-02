"""Builder's bounded type designs and bindings over supplied source statements."""
from copy import deepcopy
from collections import Counter
from uuid import uuid4

from pydantic import ValidationError
from . import discovery_segments as segments, discovery_models as models


def scope_local_refs(output):
    # Separate model t1..t5 from a supplied canonical ID that happens to have that name.
    local = {'t'+str(n):'local_'+uuid4().hex for n in range(1,6)}
    for candidate in output.get('observations', []):
        candidate['_binding_ref']=local[candidate['local_ref']]
    for field, keys in [('relation_bindings',('subject_ref','object_ref')), ('hierarchies',('child_ref','parent_ref')),
                        ('alias_proposals',('observation_ref','target_id'))]:
        for item in output.get(field, []):
            if not isinstance(item,dict): continue
            for key in keys:
                if isinstance(item.get(key),str): item[key]=local.get(item[key],item[key])


def bind(output, supplied, by_id, context):
    editable = set(context.get('design_relation_ids', supplied))
    proposals = output.get('observations', [])
    local = {c.pop('_binding_ref', c['local_ref']):c['id'] for c in proposals}
    available = dict(supplied, **{c['id']:c for c in proposals})
    for candidate in proposals:
        refs, errors = segments.references(candidate,by_id,segments.originals(context))
        candidate['evidence_refs'] = refs
        candidate['validation'].extend(errors)
        sources = [supplied.get(i,{}) for i in candidate['source_relation_ids']]
        if not set(candidate['source_relation_ids']) <= editable or any(s.get('statement_type') not in {'rule','definition'} for s in sources):
            candidate['validation'].append('설계 출처는 실제 제공된 규범/정의 관계여야 함')
        if not all(set(s.get('evidence_ids', [])) & set(candidate['evidence_ids']) for s in sources):
            candidate['validation'].append('설계 유형과 출처 관계의 근거 연결 필요')
    bindings = output.get('relation_bindings', [])
    counts = Counter(b.get('relation_ref') for b in bindings if isinstance(b,dict) and isinstance(b.get('relation_ref'),str))
    answered, bound, deferred, pending, errors, accepted = set(), set(), set(), set(), [], []
    output['modeled_relations'] = []
    output['source_errors'] = []
    for raw in bindings:
        identifier = raw.get('relation_ref') if isinstance(raw,dict) and isinstance(raw.get('relation_ref'),str) else None
        try:
            binding = models.RelationBinding.model_validate(raw).model_dump()
            source = supplied.get(identifier, {})
            if identifier not in editable or counts[identifier]!=1 or source.get('statement_type') not in {'rule','definition'}:
                raise ValueError('중복 연결 또는 실제 제공된 규범/정의 관계 밖 참조')
            if binding['decision'] in {'defer','source_error'}:
                if binding['subject_ref'] or binding['object_ref']: raise ValueError('보류에 확정 끝점 연결을 함께 제출할 수 없음')
                answered.add(identifier); deferred.add(identifier); accepted.append(binding)
                if binding['decision']=='source_error': output['source_errors'].append(binding)
                continue
            for field in ('subject_ref','object_ref'):
                binding[field] = local.get(binding[field],binding[field])
                target = available.get(binding[field], {})
                if target.get('classification')!='type' or target.get('validation') or target.get('outside_scope_reason') or target.get('deprecated'):
                    raise ValueError('설계 관계의 끝점은 실제 제공된 유효 유형 ID여야 함: '+field)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            if identifier in editable: pending.add(identifier)
            errors.append(dict(candidate_ids=[identifier] if identifier in editable else [],record=deepcopy(raw),reason=str(exc)))
            continue
        accepted.append(binding); answered.add(identifier); bound.add(identifier)
        relation = deepcopy(source)
        relation.update(source_relation=deepcopy(source), design_reason=binding['reason'],
                        statement_type='design_proposal', support_type='design_proposal', unresolved_endpoints=[])
        for field in ('subject','object'):
            relation[field] = binding[field+'_ref']
        output['modeled_relations'].append(relation)
    if 'design_relation_ids' in context:
        for identifier in sorted(editable-answered-pending):
            errors.append(dict(candidate_ids=[identifier],record=None,reason='필수 관계의 연결 또는 구체 보류 누락'))
        pending |= editable-answered
        output['binding_coverage']=dict(expected_relation_ids=sorted(editable),answered_relation_ids=sorted(answered),
            bound_relation_ids=sorted(bound),deferred_relation_ids=sorted(deferred),pending_relation_ids=sorted(pending))
        output['binding_errors']=errors
    output['relation_bindings']=accepted
    for field, keys in [('hierarchies',('child_ref','parent_ref')), ('alias_proposals',('observation_ref','target_id'))]:
        for item in output.get(field, []):
            for key in keys: item[key]=local.get(item[key],item[key])
    return available
