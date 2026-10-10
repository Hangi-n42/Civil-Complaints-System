"""Source-impact state must survive a same-revision reassessment."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_changes, business_run, business_store, business_use, discovery_profile, graph_retrieval
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, encode, utcnow


@pytest.mark.parametrize('context_mode,retrieval', [('graph', 'bm25'), ('document', 'bm25'), ('graph', 'hipporag2')])
@pytest.mark.parametrize('impact_status', ['affected', 'unknown'])
@pytest.mark.parametrize('diff_address', ['row', 'text'])
def test_reassessment_does_not_reactivate_old_changed_source(tmp_path, monkeypatch, context_mode, retrieval, impact_status, diff_address):
    # Synthetic source rows exercise state transitions, not semantic accuracy.
    service = KnowledgeService(tmp_path / 'knowledge.db')
    blocks = [dict(id=bid, source_version_id=version, parse_run_id='parse', text=bid)
              for bid, version in [('old-changed', 'v1'), ('old-stable', 'v1'), ('new-changed', 'v2')]]
    claims = [dict(id='c-' + b['id'], role='event_entity', raw=dict(Event=b['text']),
                   source_version_ids=[b['source_version_id']],
                   evidence=[dict(block_id=b['id'], source_version_id=b['source_version_id'], parse_run_id='parse',
                                  start_char=0, end_char=len(b['text']), quote=b['text'])]) for b in blocks]
    requirements = [dict(id=rid, revision=1, status='satisfied', history=[], change_history=[],
                         question=rid, criterion=rid, current_assessment=None) for rid in ['changed', 'stable']]
    original = dict(id='origin', kind='business', status='succeeded', units=[],
        started_at='2026-01-01T00:00:00+00:00', recipe=dict(options={}), model_identity={})
    snapshot = dict(id='old', kind='source_graph', run_id='origin', source_versions={'v1':{}}, concepts=[],
                    blocks=blocks[:2], claims=claims[:2], requirements=deepcopy(requirements),
                    assessments={r['id']:dict(id='a-' + r['id'], status='satisfied', claim_ids=[claims[i]['id']])
                                 for i, r in enumerate(requirements)})
    snapshot['assessments']['changed'].update(source=dict(meanings=[dict(key='expired', statement='expired meaning')]),
        representation=dict(checks=[dict(meaning_key='expired', status='represented', claim_ids=['c-old-stable'])]))
    snapshot['explicit_meaning_reviews'] = [dict(requirement_id='changed', meaning=dict(key='expired'), claim_ids=['c-old-stable'])]
    change = dict(id='change', kind='business_change', status='succeeded', units=[],
        request=dict(before_version_id='v1', after_version_id='v2'),
        diff=dict(changes=[dict(id='delta', before_block_id='old-changed', after_block_id='new-changed')]))
    if diff_address == 'text':
        change['diff']['changes'] = [dict(id='delta', before_block_ids=['old-changed'], after_block_ids=['new-changed'])]
    observed = []

    class BoundaryReached(Exception): pass

    class Index:
        def __init__(self, candidates, **_): self.candidates = candidates
        def search(self, *_):
            observed.append({c['id'] for c in self.candidates})
            raise BoundaryReached()

    def retrieve(_service, _run, view, _request):
        observed.append({c['id'] for c in view['claims']})
        raise BoundaryReached()

    monkeypatch.setattr(discovery_profile, 'FrozenIndex', Index)
    monkeypatch.setattr(graph_retrieval, 'retrieve', retrieve)
    try:
        with service.repository.connect() as db:
            for table, values in [('runs', [original, change]), ('requirements', requirements), ('snapshots', [snapshot])]:
                for value in values: db.execute(f'INSERT INTO {table} VALUES(?,?)', (value['id'], encode(value)))
        impacts = [dict(requirement_id='changed', status=impact_status, reason='changed row', change_ids=['delta']),
                   dict(requirement_id='stable', status='unaffected', reason='same row', change_ids=[])]
        business_changes.apply_impacts(service, change, requirements, impacts)
        for requirement in requirements:
            business_store.save_assessment(service, dict(id='new-run', input_version_ids=['v2']), requirement,
                dict(id='new-' + requirement['id'], status='partial', claim_ids=['c-new-changed']))
        request = BusinessQuery(snapshot_id='old', question='changed', requirement_ids=['changed'], retrieval=retrieval)
        result = business_use.query(service, request, context_mode=context_mode)
        assert result['status'] == 'needs_review' and result['answer'] is None
        assert not observed
        stable_request = request.model_copy(update=dict(question='stable', requirement_ids=['stable']))
        if retrieval == 'bm25':
            with pytest.raises(BoundaryReached): business_use.query(service, stable_request, context_mode=context_mode)
        else:
            assert business_use.query(service, stable_request)['status'] == 'retrieval_failed'
        assert observed[-1] == ({'old-stable'} if context_mode == 'document' else {'c-old-stable'})
        with service.repository.connect() as db:
            queries = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM runs')]
            assert next(r for r in queries if r.get('kind') == 'business_query')['snapshot_invalidations'][0]['claim_ids'] == ['c-old-changed']
            assert service.repository.get(db, 'snapshots', 'old') == snapshot
            db.execute("DELETE FROM runs WHERE json_extract(payload,'$.kind')='business_query'")
            new = dict(snapshot, id='new', source_versions={'v2':{}}, claims=claims[2:], blocks=blocks[2:])
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('new', encode(new)))
        new_request = request.model_copy(update=dict(snapshot_id='new'))
        if retrieval == 'bm25':
            with pytest.raises(BoundaryReached): business_use.query(service, new_request, context_mode=context_mode)
        else:
            assert business_use.query(service, new_request)['status'] == 'retrieval_failed'
        assert observed[-1] == ({'new-changed'} if context_mode == 'document' else {'c-new-changed'})
        # Before-version metadata alone is not an old source dependency.
        with service.repository.connect() as db:
            db.execute("DELETE FROM runs WHERE json_extract(payload,'$.kind')='business_query'")
            after_assessment = dict(id='new-changed', status='partial', claim_ids=['c-new-changed'],
                source=dict(meanings=[dict(key='after', evidence=claims[2]['evidence'])]))
            mixed = dict(new, id='mixed', source_versions={'v1':{}, 'v2':{}},
                         assessments=dict(new['assessments'], changed=after_assessment))
            origin_after = dict(original, id='after-origin', claims=claims[2:], blocks=blocks[2:])
            mixed['run_id'] = origin_after['id']
            db.execute('INSERT INTO runs VALUES(?,?)', (origin_after['id'], encode(origin_after)))
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('mixed', encode(mixed)))
        mixed_request = request.model_copy(update=dict(snapshot_id='mixed'))
        if retrieval == 'bm25':
            with pytest.raises(BoundaryReached): business_use.query(service, mixed_request, context_mode=context_mode)
        else:
            assert business_use.query(service, mixed_request)['status'] == 'retrieval_failed'
        assert observed[-1] == ({'new-changed'} if context_mode == 'document' else {'c-new-changed'})
        with service.repository.connect() as db:
            db.execute("DELETE FROM runs WHERE json_extract(payload,'$.kind')='business_query'")
            old_ref = dict(mixed, id='mixed-old-ref', assessments=dict(mixed['assessments'], changed=dict(after_assessment,
                source=dict(meanings=[dict(key='after', evidence=claims[2]['evidence'],
                    field_judgments=dict(conditions=dict(evidence=claims[0]['evidence'])))]))))
            db.execute('INSERT INTO snapshots VALUES(?,?)', (old_ref['id'], encode(old_ref)))
        assert business_use.query(service, request.model_copy(update=dict(snapshot_id='mixed-old-ref')))['status'] == 'needs_review'
        # A later start time alone cannot make changed old evidence current.
        with service.repository.connect() as db:
            db.execute("DELETE FROM runs WHERE json_extract(payload,'$.kind')='business_query'")
            original.update(id='later-review', started_at=utcnow())
            db.execute('INSERT INTO runs VALUES(?,?)', (original['id'], encode(original)))
            later = dict(snapshot, id='later', run_id=original['id'])
            db.execute('INSERT INTO snapshots VALUES(?,?)', ('later', encode(later)))
        later_request = request.model_copy(update=dict(snapshot_id='later'))
        assert business_use.query(service, later_request, context_mode=context_mode)['status'] == 'needs_review'
        with service.repository.connect() as db:
            db.execute("DELETE FROM runs WHERE json_extract(payload,'$.kind')='business_query'")
        # Unscoped QA cannot restore the expired assessment through explicit reviews.
        boundary_search = Index.search
        monkeypatch.setattr(Index, 'search', lambda *_: [dict(block_id='c-old-stable', score=1)])
        def answer(_service, _run, _stage, _instruction, context, _schema, **_):
            assert 'public_requirements' not in context and context['reviewed_meanings'] == []
            assert not any(v['requirement_id'] == 'changed' for v in context['requirement_limitations'])
            return dict(answer='old-stable', citations=['c-old-stable'], choice=None, limitations=[])
        monkeypatch.setattr(business_run, 'json_call', answer)
        assert business_use.query(service, BusinessQuery(snapshot_id='old', question='stable', retrieval='bm25'))['status'] == 'answered'
        # A later explicit no-impact determination replaces the earlier scope judgment.
        with service.repository.connect() as db:
            current = [service.repository.get(db, 'requirements', r['id']) for r in requirements]
            repeated = dict(change, id='rechecked-change')
            db.execute('INSERT INTO runs VALUES(?,?)', (repeated['id'], encode(repeated)))
        business_changes.apply_impacts(service, repeated, current, [dict(i, status='unaffected') for i in impacts])
        monkeypatch.setattr(Index, 'search', boundary_search)
        with pytest.raises(BoundaryReached):
            business_use.query(service, request.model_copy(update=dict(retrieval='bm25')))
        assert observed[-1] == {'c-old-stable'}
    finally:
        service.shutdown()
