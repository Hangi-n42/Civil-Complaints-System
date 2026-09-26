"""K3 canonical schema, grounded proposals and atomic human decisions."""
import json
from types import SimpleNamespace
from threading import RLock

import pytest

from app.knowledge.repository import KnowledgeRepository
from app.knowledge import ontology_schema as ontology


def proposal(identifier='Housing', kind='concept', **fields):
    return dict(id=identifier, kind=kind, name='임대주택', definition='자료를 종합한 임대주택 개념', inclusion='원문에 명시된 임대주택', exclusion='개별 세대',
                evidence=[dict(evidence_id='e1', quote='임대주택')], cq_ids=['CQ1'], **fields)


def test_linkml_review_versions_and_atomic_conflict(tmp_path):
    service = SimpleNamespace(repository=KnowledgeRepository(tmp_path / 'knowledge.db'), lock=RLock())
    run = dict(id='run1', frozen_blocks=[dict(evidence_id='e1', text='임대주택 단지')],
               cqs=[dict(id='CQ1', question='단지를 어떻게 구분하는가?')], review={'issues': []})
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], json.dumps(run)))
    proposed = [proposal(), proposal('name', 'attribute', domain_id='Housing')]
    published = ontology.publish(service, run, proposed)
    assert ontology.publish(service, run, proposed) == published
    change_id = published['changeset_id']
    before = ontology.get_ontology(service, published['ontology_version_id'])
    assert before['status'] == 'draft'
    assert before['run_id'] == run['id'] and len(before['schema_hash']) == 64
    assert len(before['generated_json_schema_hash']) == 64
    assert before['unsupported_constraints'] == []
    assert 'Housing' in before['json_schema']['$defs']
    assert before['candidates'][0]['definition'] == proposed[0]['definition']
    assert ontology.candidates(service, change_id)['unresolved_count'] == 2

    # A slot cannot be accepted without the class it references; no partial write.
    with pytest.raises(ValueError, match='함께 수락'):
        ontology.decide(service, change_id, dict(expected_changeset_revision=0, actor='tester',
                         decisions=[dict(candidate_id='name', action='accept')]))
    assert ontology.candidates(service, change_id)['changeset_revision'] == 0

    result = ontology.decide(service, change_id, dict(expected_changeset_revision=0, actor='tester', decisions=[
        dict(candidate_id='Housing', action='modify', patch={'name': '주택단지'}, reason='검토 후 명칭 수정'),
        dict(candidate_id='name', action='accept')]))
    reviewed = ontology.get_ontology(service, result['reviewed_ontology_version_id'])
    assert reviewed['status'] == 'reviewed'
    assert reviewed['candidates'][0]['id'] == 'Housing'
    assert reviewed['candidates'][0]['name'] == '주택단지'
    assert ontology.get_ontology(service, published['ontology_version_id']) == before
    listing = ontology.candidates(service, change_id)
    assert listing['unresolved_count'] == 0
    assert len(listing['changesets'][0]['decisions']) == 2
    assert listing['changesets'][0]['original_candidates'][0]['name'] == '임대주택'
    with pytest.raises(ontology.VersionConflict):
        ontology.decide(service, change_id, dict(expected_changeset_revision=0, actor='tester',
                         decisions=[dict(candidate_id='Housing', action='defer')]))


def test_grounding_references_and_cq_defaults():
    blocks = [dict(evidence_id='e1', text='임대주택 단지')]
    cqs = [dict(id='CQ1', question='단지는?')]
    good = proposal()
    ontology.validate_candidates([good], blocks, cqs)
    for changed in ({'evidence': [{'evidence_id': 'unknown', 'quote': '임대주택'}]},
                    {'evidence': [{'evidence_id': 'e1', 'quote': '없는 문장'}]},
                    {'cq_ids': ['missing']}, {'unsupported_rule': 'silently ignored'}):
        with pytest.raises(ValueError):
            ontology.validate_candidates([good | changed], blocks, cqs)
    with pytest.raises(ValueError):
        ontology.validate_candidates([good, proposal('belongs', 'relation', domain_id='Housing', range='Missing')], blocks, cqs)
    assert all(set(cq) == {'id', 'question'} for cq in ontology.default_cqs()['items'])
