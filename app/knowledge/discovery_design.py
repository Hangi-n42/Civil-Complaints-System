"""Builder's bounded type designs and bindings over supplied source statements."""
from copy import deepcopy
from uuid import uuid4

from . import discovery_segments as segments


def scope_local_refs(output):
    # Separate model t1..t5 from a supplied canonical ID that happens to have that name.
    local = {'t'+str(n):'local_'+uuid4().hex for n in range(1,6)}
    for candidate in output.get('observations', []):
        candidate['_binding_ref']=local[candidate['local_ref']]
    for field, keys in [('relation_bindings',('subject_ref','object_ref')), ('hierarchies',('child_ref','parent_ref')),
                        ('alias_proposals',('observation_ref','target_id'))]:
        for item in output.get(field, []):
            for key in keys: item[key]=local.get(item[key],item[key])


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
    seen = set()
    output['modeled_relations'] = []
    for binding in output.get('relation_bindings', []):
        identifier = binding['relation_ref']
        source = supplied.get(identifier, {})
        if identifier not in editable or identifier in seen or source.get('statement_type') not in {'rule','definition'}:
            raise ValueError('중복 연결 또는 실제 제공된 규범/정의 관계 밖 참조')
        seen.add(identifier)
        relation = deepcopy(source)
        relation.update(source_relation=deepcopy(source), design_reason=binding['reason'],
                        statement_type='design_proposal', support_type='design_proposal', unresolved_endpoints=[])
        for field in ('subject','object'):
            ref = local.get(binding[field+'_ref'],binding[field+'_ref'])
            binding[field+'_ref'] = ref
            target = available.get(ref, {})
            relation[field] = ref
            if target.get('classification')!='type' or target.get('validation') or target.get('outside_scope_reason') or target.get('deprecated'):
                relation['unresolved_endpoints'].append(field)
                relation['validation'].append('설계 관계의 끝점은 실제 제공된 유효 유형 ID여야 함: '+field)
        output['modeled_relations'].append(relation)
    for field, keys in [('hierarchies',('child_ref','parent_ref')), ('alias_proposals',('observation_ref','target_id'))]:
        for item in output.get(field, []):
            for key in keys: item[key]=local.get(item[key],item[key])
    return available
