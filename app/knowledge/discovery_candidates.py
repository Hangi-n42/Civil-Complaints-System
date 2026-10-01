"""Run-local exact observation reuse; raw units and canonical ontology stay unchanged."""
from copy import deepcopy

from . import discovery_profile as profile


VERSION = 'a2-candidates-v1'


def enabled(run):
    return run.get('recipe', {}).get('candidate_version') == VERSION


def originals(run):
    return {c['id']:(c,u) for u in run.get('analysis_units', []) if u['status']=='succeeded'
            and u['stage'] in {'concept','builder'} for c in u['output'].get('observations', [])}


def exact_key(candidate):
    refs = candidate.get('evidence_refs', [])
    if candidate.get('validation') or candidate.get('evidence_validation') or candidate.get('outside_scope_reason') or not refs:
        return None
    fields = ('label','classification','definition','conditions','exceptions','time','support_type',
              'classification_reason','abstraction_level','review_signals','design_reason')
    evidence = [(e.get('source_version_id'),e.get('parse_run_id'),e.get('block_id'),e.get('span'),e.get('quote')) for e in refs]
    if any(not all((v,p,b,s,q)) for v,p,b,s,q in evidence): return None
    return profile.digest(dict(values={k:candidate.get(k, '') for k in fields},
        scope={k:sorted(candidate.get(k, [])) for k in ('cq_ids','scope_item_ids','source_relation_ids')},
        evidence=sorted(evidence)))


def register(run):
    if not enabled(run): return
    state = run.setdefault('candidate_identity', dict(version=VERSION, raw_to_candidate={}, discoveries={}))
    mapping = state['raw_to_candidate']; raw = originals(run)
    revised = {h['candidate_id'] for u in run['analysis_units'] if u['status']=='succeeded'
               for h in u.get('output', {}).get('history', [])}
    # Do not attach a new old-definition observation to an already revised candidate.
    known = {key:i for i,(c,_) in raw.items() if mapping.get(i)==i and i not in revised
             and (key:=exact_key(c)) is not None}
    for identifier,(candidate,unit) in raw.items():
        if identifier in mapping: continue
        key = exact_key(candidate)
        representative = known.setdefault(key,identifier) if key is not None else identifier
        mapping[identifier] = representative
        state['discoveries'].setdefault(representative, []).append(dict(raw_observation_id=identifier,
            unit_id=unit['id'], group_id=unit['group_id']))


def identifier(run, value):
    return run.get('candidate_identity', {}).get('raw_to_candidate', {}).get(value,value) if enabled(run) else value


def dependencies(run, value):
    original = originals(run).get(identifier(run,value)) if enabled(run) else None
    return set(original[1].get('dependency_ids', [])) if original else set()


def view(run, row, revised=False):
    if not enabled(run): return deepcopy(row)
    value = deepcopy(row)
    if 'classification' in row and row.get('id'):
        target = identifier(run,row['id'])
        if target != row['id'] and not revised:
            value = deepcopy(originals(run)[target][0])
        value['id'] = target
    # Resolve only ID-bearing fields of each contract, never prose or source_relation.
    fields = ('subject','object') if 'negation' in row else ('child_ref','parent_ref') if 'child_ref' in row else ()
    for field in fields: value[field] = identifier(run,value[field])
    if fields == ('child_ref','parent_ref') and value['child_ref']==value['parent_ref']:
        reason = '대표 후보 연결 후 자기 참조'
        if reason not in value.setdefault('validation', []): value['validation'].append(reason)
    value['candidate_view_version'] = VERSION
    return value


def rows(run, values, available=None):
    result = {}
    for row in values:
        if available is not None and not dependencies(run,row['id']) <= available: continue
        value = view(run,row)
        result.setdefault(value['id'],value)
    return list(result.values())


def alignment(run, value):
    result = deepcopy(value)
    for field in ('observation_ref','target_id'): result[field] = identifier(run,result[field])
    return result


def output(run, value):
    result = deepcopy(value)
    if not enabled(run): return result
    for field in ('observations','relations','modeled_relations','hierarchies','effective_hierarchies'):
        if field in result: result[field] = rows(run,result[field])
    for field in ('alignments','alias_proposals'):
        if field in result: result[field] = [alignment(run,a) for a in result[field]]
    for binding in result.get('relation_bindings', []):
        for field in ('subject_ref','object_ref'): binding[field] = identifier(run,binding[field])
    return result
