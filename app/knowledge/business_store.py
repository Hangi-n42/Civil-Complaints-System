"""Requirements persist across runs; assessment history lives in immutable run records."""
import json
from copy import deepcopy
from .service import KnowledgeConflict, encode, utcnow


def put_requirement(service, request):
    value = request.model_dump()
    expected = value.pop('expected_revision')
    with service.lock, service.repository.connect() as db:
        row = db.execute('SELECT payload FROM requirements WHERE id=?', (value['id'],)).fetchone()
        previous = json.loads(row['payload']) if row else None
        if expected != (previous['revision'] if previous else 0):
            raise KnowledgeConflict('Requirement revision changed')
        for source_id in value['source_ids']:
            service.repository.get(db, 'sources', source_id)
        value.update(revision=expected + 1, updated_at=utcnow(), current_assessment=None,
                     status='unassessed', history=deepcopy(previous.get('history', [])) if previous else [],
                     change_history=deepcopy(previous.get('change_history', [])) if previous else [])
        db.execute('INSERT INTO requirement_versions VALUES(?,?,?)', (value['id'], value['revision'], encode(value)))
        db.execute('INSERT INTO requirements VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (value['id'], encode(value)))
    return value


def requirements(service, identifier=None):
    with service.repository.connect() as db:
        values = [json.loads(row['payload']) for row in db.execute(
            'SELECT payload FROM requirements' + (' WHERE id=?' if identifier else ''),
            (identifier,) if identifier else ())]
        return dict(items=values)


def save_assessment(service, run, requirement, assessment):
    """Retain previous judgments/repair receipts; never rewrite a requirement to fit output."""
    with service.lock, service.repository.connect() as db:
        current = service.repository.get(db, 'requirements', requirement['id'])
        if current['revision'] != requirement['revision']:
            raise KnowledgeConflict('Requirement changed during assessment')
        ref = dict(run_id=run['id'], assessment_id=assessment['id'], revision=requirement['revision'],
                   source_version_ids=run['input_version_ids'], claim_ids=assessment.get('claim_ids', []),
                   status=assessment['status'], recorded_at=utcnow())
        current['history'].append(ref)
        current.update(current_assessment=ref, status=assessment['status'])
        service.repository.save(db, 'requirements', current)
