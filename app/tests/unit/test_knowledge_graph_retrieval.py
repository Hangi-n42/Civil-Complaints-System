import json
from copy import deepcopy

import numpy as np
import pytest

from app.knowledge import autoschema, business_run, business_use, graph_retrieval as gr
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService


def snapshot():
    claims = []
    for i, (role, raw) in enumerate([
        ('entity_relation', dict(Head='기관', Relation='허용', Tail='신청')),
        ('entity_relation', dict(Head='기관', Relation='금지', Tail='신청')),
        ('event_entity', dict(Event='신청 접수', Entity=['기관'])),
        ('entity_relation', dict(Head='기관', Relation='안내', Tail='통지')),
    ]):
        text = '원문 ' + str(i)
        claims.append(dict(id=f'c{i}', chunk_id='ch' if i < 3 else 'another-source', role=role,
            raw=raw, statement=text, source_version_ids=['v'], review_status='accepted',
            evidence=[dict(block_id=f'b{i}', source_version_id='v', parse_run_id='p',
                start_char=0, end_char=len(text), quote=text)]))
    graph = autoschema.graph(claims)
    concepts = [dict(target=t, concepts=['행정 기관'], status='unreviewed')
                for t in graph['nodes'] if t['label'] == '기관']
    concepts.append(dict(target=dict(kind='relation', id='rel', label='허용', claim_ids=['c0']),
                         concepts=['권한 부여'], status='unreviewed'))
    return dict(id='s', kind='source_graph', run_id='origin', claims=claims, concepts=concepts,
        source_versions={'v': {}}, requirements=[], assessments={},
        blocks=[dict(id=f'b{i}', source_version_id='v', text='원문 ' + str(i)) for i in range(4)])


def test_graph_preserves_parallel_relations_source_identities_and_concept_status():
    s = snapshot(); before = deepcopy(s)
    graph, edges, passages, ignored = gr.build(s, 'full')
    assert len([n for _, n in graph.nodes(data=True) if n['label'] == '기관']) == 2
    pair = next(e for e in edges if e['relation'] == '허용')
    assert len(graph.get_edge_data(pair['head'], pair['tail'])) == 2
    assert graph.edges[pair['head'], pair['tail'], pair['id']]['concepts'] == ['권한 부여']
    hubs = [n for n, d in graph.nodes(data=True) if d['kind'] == 'concept']
    assert len(hubs) == 1 and graph.in_degree(hubs[0]) == 2
    assert all(not e['approved_is_a'] for e in edges if e['relation'] == 'has_concept')
    assert len(passages) == 4 and not ignored and s == before
    without, _, p2, _ = gr.build(s, 'entity_event')
    assert not any(n['kind'] == 'concept' for _, n in without.nodes(data=True))
    assert p2 == passages  # Graph ablation must not remove source information.
    entities, _, p3, _ = gr.build(s, 'entity')
    assert not any(n['kind'] == 'event' for _, n in entities.nodes(data=True))
    assert p3 == passages
    s['concepts'][0]['status'] = 'needs_review'
    changed, _, _, _ = gr.build(s, 'full')
    assert changed.in_degree(hubs[0]) == 1


def test_ppr_uses_relationships_not_only_dense_scores():
    import networkx as nx
    g = nx.MultiDiGraph()
    g.add_edges_from([('a', 'b'), ('b', 'p1')]); g.add_node('p2')
    edges = [dict(id='e', head='a', tail='b')]
    ranked, seeds = gr.rank(g, edges, {'p1': {}, 'p2': {}}, [1.], [.2, .8], {'e'}, 2)
    assert ranked[0][0] == 'p1' and seeds == {'a': 1., 'b': 1.}
    dense, seeds = gr.rank(g, edges, {'p1': {}, 'p2': {}}, [1.], [.2, .8], set(), 2)
    assert dense[0][0] == 'p2' and not seeds


def test_unlinked_source_passage_remains_retrievable_without_invented_claims():
    s = snapshot()
    s.update(claims=[], concepts=[], include_unlinked_blocks=True)
    g, edges, passages, _ = gr.build(s, 'full')
    assert len(passages) == 4 and not edges and g.number_of_edges() == 0
    assert all(not row['claim_ids'] for row in passages.values())
    ranked, seeds = gr.rank(g, edges, passages, [], [1., .8, .4, .1], set(), 2)
    assert len(ranked) == 2 and not seeds


def test_product_query_runs_filter_then_qa_and_does_not_pass_concepts_as_facts(tmp_path, monkeypatch):
    s = snapshot()
    service = KnowledgeService(tmp_path/'knowledge.db')
    original = dict(id='origin', status='succeeded', units=[], model_identity={}, recipe={})
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(s)))
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
    monkeypatch.setattr(gr, 'embed', lambda texts: np.asarray([[1., .5] for _ in texts]))
    stages = []
    def call(service, run, stage, instruction, context, schema, **kwargs):
        stages.append(stage)
        if stage == 'graph_retrieval_filter':
            return dict(selected_ids=[context['candidate_facts'][0]['id']])
        assert stage == 'business_qa'
        assert 'has_concept' not in json.dumps(context['context'])
        assert context['source_evidence']
        return dict(answer='원문 답변', choice=None, citations=[context['context'][0]['id']], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', call)
    try:
        request = BusinessQuery(snapshot_id='s', question='신청', limit=2)
        result = business_use.query(service, request)
        assert result['status'] == 'answered' and stages == ['graph_retrieval_filter', 'business_qa']
        run = service.run(result['run_id'])
        assert run['graph_retrieval']['seed_node_scores']
        assert run['graph_retrieval']['variant'] == 'full' and run['graph_retrieval']['concept_nodes'] > 0
        assert run['retrieval_contract'] == gr.CONTRACT
        assert run['retrieval_concept_hints'] == {}
        assert all(h['block_id'] in {'c0', 'c1', 'c2', 'c3'} for h in result['retrieval'])
        stages.clear()
        monkeypatch.setattr(gr, 'embed', lambda _: (_ for _ in ()).throw(ValueError('embedding failed')))
        result = business_use.query(service, request)
        assert result['status'] == 'retrieval_failed' and not stages
        assert service.run(result['run_id'])['status'] == 'failed'
    finally:
        service.shutdown()


def test_embedding_never_silently_truncates(monkeypatch):
    class Encoder:
        max_seq_length = 2
        tokenizer = type('Tokenizer', (), {'encode': lambda *a, **k: [1, 2, 3]})()
        def encode(self, *a, **k):
            pytest.fail('Oversized text must not be embedded after truncation')
    monkeypatch.setattr(gr, 'encoder', lambda: Encoder())
    with pytest.raises(ValueError, match='한도'):
        gr.embed(['long source'])


def test_qa_source_aliases_restore_citations_and_preserve_source_spans(tmp_path, monkeypatch):
    s = snapshot()
    service = KnowledgeService(tmp_path/'knowledge.db')
    recipe = dict(generation={'provider': 'ollama'}, models={'review': 'mock'},
                  options=dict(context_tokens=49152, review_tokens=4096, think=False, timeout=2))
    with service.repository.connect() as db:
        db.execute('INSERT INTO snapshots VALUES(?,?)', ('s', json.dumps(s)))
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(dict(
            id='origin', status='succeeded', units=[], model_identity={}, recipe=recipe))))
    class Client:
        def __init__(self, *_): pass
        async def generate(self, request, cancelled=None):
            context = json.loads(request.messages[1]['content'])
            evidence = context['source_evidence'][0]
            assert evidence['id'].startswith('b') and evidence['source_version_id'] == 'v1'
            assert evidence['parse_run_id'] == 'p1'
            assert evidence['span'] == [0, len(evidence['text'])]
            assert evidence['claim_references'][0]['claim_ids'][0].startswith('q')
            return dict(parsed=dict(answer='원문', choice=None, citations=['q1'], limitations=[]),
                        failure_kind=None, elapsed_s=.01)
    monkeypatch.setattr(business_run, 'ModelClient', Client)
    try:
        result = business_use.query(service, BusinessQuery(snapshot_id='s', question='원문', retrieval='bm25', limit=2))
        assert result['status'] == 'answered'
        assert result['answer']['citations'][0].startswith('c')
        with service.repository.connect() as db:
            assert service.repository.get(db, 'snapshots', 's') == s
    finally:
        service.shutdown()


def test_source_run_qa_uses_ranked_passages_without_creating_approval(tmp_path, monkeypatch):
    s = snapshot()
    original = dict(id='origin', kind='business', status='partial', units=[], model_identity={},
                    recipe=dict(options=dict(context_tokens=49152, review_tokens=4096)),
                    sources=s['source_versions'], blocks=s['blocks'], claims=s['claims'], concepts=s['concepts'])
    for claim in original['claims']:
        claim['review_status'] = 'unreviewed'
    service = KnowledgeService(tmp_path/'knowledge.db')
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('origin', json.dumps(original)))
    monkeypatch.setattr(gr, 'embed', lambda texts: np.asarray([[1., .5] for _ in texts]))
    def call(service, run, stage, instruction, context, schema, **kwargs):
        if stage == 'graph_retrieval_filter':
            return dict(selected_ids=[context['candidate_facts'][0]['id']])
        assert len(context['context']) == 2
        assert all(c['text'].startswith('원문') and c['id'].startswith('passage_') for c in context['context'])
        assert not context['source_evidence']  # No all-document claim expansion.
        assert '온톨로지 승인' in instruction
        return dict(answer='원문', choice=None, citations=[context['context'][0]['id']], limitations=[])
    monkeypatch.setattr(business_run, 'json_call', call)
    try:
        result = business_use.query(service, BusinessQuery(source_run_id='origin', question='원문', limit=2))
        assert result['status'] == 'answered' and result['snapshot_id'] is None
        assert result['answer_basis'] == 'source_passages_not_ontology_approval'
        with service.repository.connect() as db:
            assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM decisions').fetchone()[0] == 0
            assert service.repository.get(db, 'runs', 'origin') == original
    finally:
        service.shutdown()


def test_reader_context_keeps_table_rowspan_and_does_not_attach_other_source():
    blocks = [dict(id='name', text='센터명', source_version_id='v',
                   locator=dict(element_path='table', row=1, column=0, merged_span=dict(rows=2))),
              dict(id='body', text='번호 변경 제외', source_version_id='v',
                   locator=dict(element_path='table', row=2, column=1)),
              dict(id='other', text='다른 센터', source_version_id='v',
                   locator=dict(element_path='table', row=3, column=0)),
              dict(id='unrelated', text='별도 출처', source_version_id='v2',
                   locator=dict(element_path='table', row=2, column=0))]
    context = [dict(id='passage', text=blocks[1]['text'], source_reference=dict(
        block_id='body', source_version_id='v', start_char=0, end_char=len(blocks[1]['text'])))]
    rows = gr.source_context(blocks, context, dict(context_tokens=4096, review_tokens=256))
    assert [b['id'] for b in rows] == ['name']
    assert rows[0]['supports_context_ids'] == ['passage']
    assert rows[0]['locator']['merged_span']['rows'] == 2 and context[0]['locator']['row'] == 2


def test_source_citation_dedup_keeps_unknown_ids_invalid_and_legacy_strict():
    from typing import Literal
    from pydantic import Field, ValidationError, create_model
    old = create_model('ContextAnswer', __base__=business_use.Answer,
        citations=(list[Literal['q1', 'q2']], Field(max_length=2, json_schema_extra={'uniqueItems': True})))
    new = create_model('ContextAnswer', __base__=business_use.SourceAnswer,
        citations=(list[Literal['q1', 'q2']], Field(max_length=2, json_schema_extra={'uniqueItems': True})))
    assert old.model_json_schema() == new.model_json_schema()  # Model input contract unchanged.
    raw = dict(answer='근거 있는 답변', choice=None, citations=['q1', 'q1', 'q1'], limitations=[])
    assert new.model_validate(raw).citations == ['q1']
    assert raw['citations'] == ['q1', 'q1', 'q1']
    with pytest.raises(ValidationError):
        old.model_validate(raw)
    with pytest.raises(ValidationError):
        new.model_validate(dict(raw, citations=['unknown', 'unknown']))


def test_reader_preserves_mandatory_context_across_linked_continuations():
    header = '필수 조건 ' * 1200
    blocks = [dict(id='header', text=header, source_version_id='v',
                   locator=dict(element_path='table', row=0, column=0)),
              dict(id='body', text='허용되는 신청', source_version_id='v',
                   locator=dict(element_path='table', row=1, column=0))]
    context = [dict(id='passage', text=blocks[1]['text'], source_reference=dict(
        block_id='body', source_version_id='v', start_char=0, end_char=len(blocks[1]['text'])))]
    rows = gr.source_context(blocks, context, dict(context_tokens=4096, review_tokens=256))
    parts = sorted([r for r in rows if r.get('id') == 'header'], key=lambda r:r['span'])
    assert ''.join(r['text'] for r in parts) == header
    assert all(r['supports_context_ids'] == ['passage'] for r in parts)
