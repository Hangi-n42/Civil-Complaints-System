"""Automatic repair uses the same bounded source challenge path as explicit edits."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.knowledge import business_review, business_run, business_use
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments


@pytest.mark.parametrize('unresolved', [False, True])
def test_execute_rechecks_repair_and_shared_dependencies_once(monkeypatch, unresolved):
    run = local_run()
    before = deepcopy(run['claims'])
    changed, control = [c['id'] for c in before]
    run.update(id='repair-recheck', stored_pool=True, concepts=[], metrics={})
    run['recipe']['options']['conceptualize'] = False
    run['requirements'] = [dict(id=rid, revision=1, source_ids=[])
                           for rid in ('shared', 'independent', 'repair')]
    service = SimpleNamespace(lock=nullcontext(), repository=SimpleNamespace(
        connect=lambda: nullcontext(None), get=lambda *args: run, save=lambda *args: None))
    monkeypatch.setattr(business_run, 'save', lambda *args: None)
    monkeypatch.setattr(business_run, 'cancelled', lambda *args: False)
    monkeypatch.setattr(business_run, 'refresh_repaired_graph', lambda *args: None)
    monkeypatch.setattr(business_use, 'publish', lambda *args: dict(id='change'))
    monkeypatch.setattr(business_review, 'source', lambda *args, **kwargs: pytest.fail('No broad source reread'))
    monkeypatch.setattr(business_run, 'json_call', lambda *args, **kwargs: pytest.fail('No new judge'))
    initial, calls = {}, []

    def assess(_service, _run, requirement, *, source=None, phase='initial'):
        rid = requirement['id']
        source = deepcopy(source) if source else dict(meanings=[meaning(rid)],
            examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
        cid = control if rid == 'independent' else changed
        representation = judgments([rid], ids=[cid])
        if phase in {'after_repair', 'shared_claim_recheck'} or (phase == 'source_reassessment' and unresolved):
            representation['meaning_challenges'] = [dict(meaning_key=rid, fields=['conditions'],
                reason='Changed candidate exposes an unresolved condition', evidence=source['meanings'][0]['evidence'])]
        result = dict(id=str(len(run['assessments'])), requirement_id=rid, phase=phase, source=source,
            representation=representation, status='partial' if representation['meaning_challenges'] else 'satisfied',
            errors=[], actions=[], review_scope=dict(claim_ids=[cid]))
        result['input_fingerprint'] = business_run.assessment_fingerprint(run, requirement, source, result['review_scope'])
        run['assessments'].append(result)
        if phase == 'initial':
            initial[rid] = deepcopy(result)
        return result

    def repair(_service, _run, requirement, assessment):
        if requirement['id'] != 'repair':
            return False
        run['claims'][0]['conditions'] = ['Corrected condition']
        run['repairs'].append(dict(status='applied_awaiting_recheck'))
        return True

    def reassess(_service, _run, requirement, assessment, challenges):
        calls.append((requirement['id'], assessment['phase'], deepcopy(challenges)))
        assert {c['meaning_key'] for c in challenges} == {requirement['id']}
        return deepcopy(assessment['source'])

    monkeypatch.setattr(business_run, 'assess', assess)
    monkeypatch.setattr(business_run, 'repair', repair)
    monkeypatch.setattr(business_review, 'reassess_source', reassess)
    business_run.execute(service, run['id'])

    assert not run.get('error')
    assert [(rid, phase) for rid, phase, _ in calls] == [
        ('repair', 'after_repair'), ('shared', 'shared_claim_recheck')]
    latest = {a['requirement_id']: a for a in run['assessments']}
    assert latest['independent'] == initial['independent']
    assert run['claims'][1] == before[1]
    assert run['repairs'][0]['recheck_assessment_id'] == latest['repair']['id']
    assert run['repairs'][0]['status'] == ('recheck_incomplete' if unresolved else 'rechecked')
    assert run['status'] == ('partial' if unresolved else 'review_ready')
    assert len(run['assessments']) == 7  # Persistent challenges do not start an unbounded retry loop.
