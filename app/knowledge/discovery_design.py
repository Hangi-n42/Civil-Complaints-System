"""Builder's bounded type designs and bindings over supplied source statements."""
from copy import deepcopy
from collections import Counter
from uuid import uuid4

from pydantic import ValidationError
from . import discovery_segments as segments, discovery_models as models, discovery_profile as profile


def inline_types(output):
    """Adapt declared wire endpoints to the existing stored type/binding contract."""
    observations = output.setdefault('observations', [])
    for binding in output.get('relation_bindings', []):
        if not isinstance(binding, dict): continue
        for field in ('subject_ref','object_ref'):
            if isinstance(binding.get(field), dict):
                candidate = dict(binding[field], local_ref='t'+str(len(observations)+1))
                observations.append(candidate)
                binding[field] = candidate['local_ref']


def scope_local_refs(output, supplied_ids=()):
    # Reserve local wire tokens, including undeclared ones; preserve only supplied wire IDs.
    tokens=[c['local_ref'] for c in output.get('observations', [])]
    supplied_ids=set(supplied_ids)
    if len(tokens)!=len(set(tokens)) or set(tokens) & supplied_ids:
        raise ValueError('새 유형 local_ref 중복 또는 제공 ID와 충돌')
    local = {f't{n}':'local_'+uuid4().hex for n in range(1,6) if f't{n}' not in supplied_ids}
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


def source_projection(candidate):
    """Only natural proposition/evidence semantics, never selected type IDs or reviews."""
    source = candidate.get('source_relation') or candidate.get('modeling_origin', {}).get('source_relation') or candidate
    fields = ('subject','predicate','object','direction','statement_type','negation','conditions','time','evidence_ids','evidence_refs')
    return {k:deepcopy(source.get(k)) for k in fields}


def declaration_schema(schema, relation_ids, source_refs):
    """Narrow the two existing observation wire records to explicit exclusive branches."""
    if 'RoleBasis' in schema['$defs']:
        schema['$defs']['RoleBasis']['properties']['relation_ref']['enum'] = relation_ids or ['']
    def variants(node):
        if 'anyOf' in node:
            for child in node['anyOf']: variants(child)
            return
        if 'role_basis' not in node.get('properties', {}): return
        role, direct = deepcopy(node), deepcopy(node)
        for name in ('label','definition','direct_definition_source_refs','source_relation_ids','conditions','exceptions','time'):
            role['properties'].pop(name,None)
        role['properties']['role_basis']={'$ref':'#/$defs/RoleBasis'}
        role['properties']['classification']={'type':'string','const':'type'}
        role['properties']['support_type']={'type':'string','const':'design_proposal'}
        role['properties']['design_reason']['minLength']=1
        direct['properties'].pop('role_basis')
        direct['properties']['label']['minLength']=1
        direct['properties']['definition']['minLength']=1
        if 'source_relation_ids' in direct['properties']: direct['properties']['source_relation_ids']['minItems']=1
        direct['properties']['direct_definition_source_refs'].update(minItems=1,items=dict(type='string',enum=source_refs or ['']))
        for branch in (role,direct):
            branch['required']=list(branch['properties'])
        node.clear();node['anyOf']=([role] if relation_ids else [])+[direct]
    for name in ('DeclaredType','DeclaredObservationRevision'):
        if name in schema['$defs']: variants(schema['$defs'][name])


def declarations(output, supplied, by_id, context):
    """Shared by initial/correction Builder and observation Revision; never repair free prose."""
    for candidate in output.get('observations', []):
        role = candidate.get('role_basis')
        direct = candidate.get('direct_definition_source_refs', [])
        candidate['definition_declaration'] = {k:deepcopy(candidate.get(k)) for k in
            ('role_basis','label','definition','conditions','exceptions','time','direct_definition_source_refs','design_reason')}
        if role:
            if candidate.get('label') or candidate.get('definition') or direct or candidate.get('source_relation_ids') or any(candidate.get(k) for k in ('conditions','exceptions','time')):
                raise ValueError('역할 선언과 자유 명칭·정의·조건·예외·시점을 함께 제출할 수 없음')
            if candidate['classification']!='type' or candidate['support_type']!='design_proposal' or not candidate.get('design_reason'):
                raise ValueError('역할 선언은 설계 유형과 설계 사유 필요')
            if role['relation_ref'] not in context.get('design_relation_ids',supplied):
                raise ValueError('역할 출처가 이번 설계 관계 범위 밖')
            source = supplied.get(role['relation_ref'], {})
            source = source.get('source_relation') or source
            if source.get('statement_type') not in {'rule','definition'} or source.get('validation') or source.get('evidence_validation') or source.get('outside_scope_reason'):
                raise ValueError('역할 출처는 제공된 유효 자연어 규범/정의 관계여야 함')
            if role['endpoint'] not in {'subject','object'} or not isinstance(source.get(role['endpoint']),str):
                raise ValueError('역할 출처의 끝점 오류')
            if any(source.get(k) in supplied and supplied[source[k]].get('classification') for k in ('subject','object')) and source.get('endpoint_mode')!='source_text':
                raise ValueError('유형 ID 연결은 자연어 역할 출처가 아님')
            refs, errors = segments.references(candidate,by_id,segments.originals(context))
            if errors or not source.get('evidence_refs') or not all(any(r['block_id']==e['block_id'] and r['span'][0]<=e['span'][0]<e['span'][1]<=r['span'][1] for r in refs) for e in source['evidence_refs']):
                raise ValueError('역할 출처 명제의 제공 원문 구간 연결 필요')
            candidate.update(label=source[role['endpoint']],definition_mode='source_role',role_source=deepcopy(source),source_relation_ids=[role['relation_ref']],
                definition='이 출처 명제에서 「'+source[role['endpoint']]+'」으로 지칭되는 '+('주체' if role['endpoint']=='subject' else '대상')+
                    ' 역할. 이 명제 안의 역할이며 유형 전체의 필요충분 정의나 실제 발생 사실을 선언하지 않음.',
                conditions='',exceptions='',time='')
        else:
            if not candidate.get('label') or not candidate.get('definition') or not direct:
                raise ValueError('직접 정의는 정의문과 명시적 직접 정의 원문 선택 필요')
            if 'candidate_ref' not in candidate and not candidate.get('source_relation_ids'):
                raise ValueError('직접 정의 설계의 출처 관계 선택 필요')
            refs,errors=segments.references(dict(source_refs=direct),by_id,segments.originals(context))
            if errors or not refs or (not set(direct)<=set(candidate['source_refs']) if candidate.get('source_refs') else not {e['block_id'] for e in refs}<=set(candidate.get('evidence_ids', []))):
                raise ValueError('직접 정의 근거는 이번 후보가 선택한 제공 원문이어야 함')
            candidate.update(definition_mode='direct',direct_definition_evidence_refs=refs)
            candidate.pop('role_basis',None)
            # An explicit transition must not inherit the former role's provenance.
            if 'candidate_ref' in candidate: candidate['source_relation_ids']=[]


def role_fingerprints(candidate, candidates):
    selected=[candidate]
    if candidate.get('source_relation'):
        selected += [candidates.get(candidate.get(k), {}) for k in ('subject','object')]
    hashes={}
    for target in selected:
        role=target.get('role_basis')
        if not role: continue
        source=candidates.get(role['relation_ref'])
        if source is None:
            # Canonical IDs and new extraction IDs differ; resolve only an actually supplied
            # identical natural proposition AND version/parse/block/span evidence, never the saved snapshot alone.
            source=next((c for c in candidates.values() if
                (c.get('source_relation') or c.get('modeling_origin', {}).get('source_relation') or c).get('statement_type') in {'rule','definition'}
                and source_projection(c)==source_projection(target.get('role_source', {}))),None)
        valid=source is not None and source_projection(source)==source_projection(target.get('role_source', {}))
        valid=valid and not any(target.get(k) for k in ('validation','evidence_validation','outside_scope_reason','deprecated'))
        natural=(source or {}).get('source_relation') or (source or {}).get('modeling_origin', {}).get('source_relation') or source or {}
        valid=valid and not natural.get('validation') and not natural.get('evidence_validation') and not natural.get('outside_scope_reason')
        hashes[target['id']]=profile.digest(source_projection(source)) if valid else None
    return hashes
