"""AutoSchemaKG HippoRAG2 retrieval over a source graph.

Adapted from the MIT-licensed vendor/hipporag2_upstream.py: query2edge,
query2passage, endpoint score averaging and personalized PageRank. Local BGE
embeddings replace the paper's encoder; exact supplied edge IDs replace fuzzy
rematching of LLM-generated triples. See the retrieval methodology document.
"""
from functools import lru_cache
from time import monotonic
from typing import Literal

import networkx as nx
import numpy as np
from pydantic import Field, create_model

from . import autoschema, business_run
from .vendor.autoschemakg.rag_prompt import filter_triple_messages

CONTRACT = 'autoschemakg-hipporag2-source-passages-v2'


@lru_cache(maxsize=1)
def encoder():
    from sentence_transformers import SentenceTransformer
    from app.core.config import settings
    # Use the existing local embedding model. Never download implicitly.
    return SentenceTransformer(settings.EMBEDDING_MODEL, device=settings.EMBEDDING_DEVICE,
                               local_files_only=True)


def embed(texts):
    model = encoder()
    # No silent embedding truncation. Source conditions cannot disappear here.
    for text in texts:
        if len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False)) > model.max_seq_length:
            raise ValueError('검색 임베딩 입력이 모델 한도를 넘습니다. 원문 구간을 분할해야 합니다.')
    return np.asarray(model.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype=float)


def normalize(values):
    """Upstream min_max_normalize, including the equal-score case."""
    values = np.asarray(values, dtype=float)
    span = np.max(values) - np.min(values)
    return np.ones_like(values) if span == 0 else (values - np.min(values)) / span


def build(snapshot, variant):
    """Keep source-specific identities and parallel edges; concepts are search only."""
    extracted = autoschema.graph(snapshot['claims'])
    graph = nx.MultiDiGraph()
    for node in extracted['nodes']:
        if variant == 'entity' and node['kind'] != 'entity':
            continue
        graph.add_node(node['id'], **{k: v for k, v in node.items() if k != 'id'})
    claims = {c['id']: c for c in snapshot['claims']}
    edges = []
    for edge in extracted['edges']:
        if edge['head'] in graph and edge['tail'] in graph:
            graph.add_edge(edge['head'], edge['tail'], key=edge['id'], **edge)
            edges.append(dict(edge, text=' '.join((graph.nodes[edge['head']]['label'], edge['relation'],
                                                  graph.nodes[edge['tail']]['label']))))
    passages = {}
    for claim in claims.values():
        for ref in claim.get('evidence', []):
            # Preserve the complete provided quote and source version, not its concept label.
            pid = autoschema.identifier('passage', {k: ref.get(k) for k in
                ('source_version_id', 'parse_run_id', 'block_id', 'start_char', 'end_char', 'quote')})
            row = passages.setdefault(pid, dict(id=pid, text=ref['quote'], evidence=ref, claim_ids=[]))
            if claim['id'] not in row['claim_ids']:
                row['claim_ids'].append(claim['id'])
            graph.add_node(pid, kind='passage', label=ref['quote'])
    if snapshot.get('include_unlinked_blocks'):
        # Upstream indexes source passages even when no triple was extracted.
        # Such passages can still be found by the dense fallback; no invented edges.
        linked_blocks = {(p['evidence']['source_version_id'], p['evidence']['block_id']) for p in passages.values()}
        for block in snapshot['blocks']:
            if (block['source_version_id'], block['id']) in linked_blocks or not block['text'].strip():
                continue
            ref = dict(source_version_id=block['source_version_id'], parse_run_id=block.get('parse_run_id'),
                       block_id=block['id'], start_char=0, end_char=len(block['text']), quote=block['text'])
            pid = autoschema.identifier('passage', ref)
            passages[pid] = dict(id=pid, text=block['text'], evidence=ref, claim_ids=[])
            graph.add_node(pid, kind='passage', label=block['text'])
    for node in extracted['nodes']:
        if node['id'] not in graph:
            continue
        for pid, passage in passages.items():
            linked = set(node['claim_ids']).intersection(passage['claim_ids'])
            if linked:
                graph.add_edge(node['id'], pid, key='mention', relation='mention in', claim_ids=sorted(linked))
    ignored = []
    if variant == 'full':
        for record in snapshot.get('concepts', []):
            target = record['target']
            if record['status'] not in {'unreviewed', 'accepted'}:
                continue
            # Upstream relation concepts annotate edges; entity/event concepts are nodes.
            if target['kind'] == 'relation':
                for edge in edges:
                    if edge.get('claim_id') in target.get('claim_ids', []) and edge['relation'] == target['label']:
                        graph.edges[edge['head'], edge['tail'], edge['id']]['concepts'] = record['concepts']
                continue
            if target['id'] not in graph or not set(target.get('claim_ids', [])).intersection(claims):
                ignored.append(target['id'])
                continue
            for label in dict.fromkeys(record['concepts']):
                cid = autoschema.identifier('concept', label)
                graph.add_node(cid, kind='concept', label=label, status='unapproved_search_concept')
                eid = autoschema.identifier('has_concept', [target['id'], cid])
                if graph.has_edge(target['id'], cid, eid):
                    continue
                edge = dict(id=eid, head=target['id'], tail=cid, relation='has_concept',
                            status=record['status'], approved_is_a=False)
                graph.add_edge(target['id'], cid, key=eid, **edge)
                edges.append(dict(edge, text=target['label'] + ' has_concept ' + label))
    return graph, edges, passages, ignored


def passage_candidates(passages):
    return [dict(id=p['id'], text=p['text'], file_id=p['evidence']['source_version_id'],
                 source_group=p['evidence']['source_version_id'],
                 source_reference={k: v for k, v in p['evidence'].items() if k != 'quote'},
                 linked_claim_ids=p['claim_ids']) for p in passages.values()]


def source_context(blocks, context, options):
    """Reuse extraction's mandatory table/list/heading bundles at the reader boundary."""
    selected = {}
    originals = {(b['source_version_id'], b['id']): b for b in blocks}
    for item in context:
        ref = item['source_reference']
        key = (ref['source_version_id'], ref['block_id'])
        selected.setdefault(key, []).append(item['id'])
        if key in originals:
            item['locator'] = autoschema.source_packet([originals[key]])[0].get('locator', {})
    views = {}
    # One indivisible target unit per bundle; this reuses the existing required
    # context selection without packing unrelated targets up to the model limit.
    bundles = autoschema.chunks(blocks, options['context_tokens'], options['review_tokens'], target_chars=1)
    continuation_targets = {}
    for bundle in bundles:
        for b in bundle['blocks']:
            if b.get('continuation_bundle') and not b.get('context_only'):
                continuation_targets.setdefault(b['continuation_bundle'], set()).update(
                    selected.get((b['source_version_id'], b['id']), []))
    for bundle in bundles:
        targets = list(dict.fromkeys(cid for b in bundle['blocks'] for cid in (
            sorted(continuation_targets.get(b.get('continuation_bundle'), []))
            if b.get('continuation_bundle') else
            selected.get((b['source_version_id'], b['id']), []) if not b.get('context_only') else [])))
        if not targets:
            continue
        for b in bundle['blocks']:
            if not b.get('context_only'):
                continue
            span = b.get('span', [0, len(b['text'])])
            key = (b['source_version_id'], b['id'], tuple(span))
            existing = next((c['id'] for c in context if c['source_reference']['block_id'] == b['id']
                and c['source_reference']['source_version_id'] == b['source_version_id']
                and [c['source_reference']['start_char'], c['source_reference']['end_char']] == span), None)
            if existing:
                row = views.setdefault(key, dict(context_id=existing, supports_context_ids=[]))
            else:
                row = views.setdefault(key, dict(autoschema.source_packet([b])[0], span=span,
                    parse_run_id=b.get('parse_run_id'), supports_context_ids=[]))
            row['supports_context_ids'] = list(dict.fromkeys(row['supports_context_ids'] + targets))
    return list(views.values())


def rank(graph, edges, passages, edge_scores, passage_scores, selected_ids, limit):
    """Upstream endpoint averaging + passage personalization + directed PPR."""
    nodes = {}
    for edge, score in zip(edges, edge_scores):
        if edge['id'] in selected_ids:
            for node in (edge['head'], edge['tail']):
                nodes.setdefault(node, []).append(float(score))
    node_scores = {n: sum(v) / len(v) for n, v in nodes.items()}
    node_scores = dict(sorted(node_scores.items(), key=lambda x: x[1], reverse=True)[:10])
    text_scores = dict(zip(passages, (float(s) * .9 for s in passage_scores)))
    if node_scores:
        pr = nx.pagerank(graph, personalization={**node_scores, **text_scores}, alpha=.9,
                         max_iter=2000, tol=1e-7)
        scores = {pid: pr[pid] for pid in passages}
    else:
        scores = text_scores
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:limit], node_scores


def retrieve(service, run, snapshot, request):
    started = monotonic()
    graph, edges, passages, ignored = build(snapshot, request.graph_variant)
    if not passages:
        raise ValueError('출처가 있는 검색 구간이 없습니다.')
    from app.core.config import settings
    trace = dict(contract=CONTRACT, variant=request.graph_variant, directed=True,
        nodes=graph.number_of_nodes(), edges=graph.number_of_edges(), passages=len(passages),
        concept_nodes=sum(n['kind'] == 'concept' for _, n in graph.nodes(data=True)),
        ignored_concept_targets=ignored, embedding_model=settings.EMBEDDING_MODEL,
        embedding_device=settings.EMBEDDING_DEVICE, alpha=.9, passage_weight=.9,
        topk_edges=30, topk_nodes=10, selected_edge_ids=[], fallback=None)
    run['graph_retrieval'] = trace
    query = request.question + '\n' + '\n'.join(request.choices)
    # Cached only on this service and immutable snapshot content; model/settings are in key.
    cache = getattr(service, '_graph_embedding_cache', {})
    key = autoschema.identifier('index', [snapshot['id'], request.graph_variant,
        settings.EMBEDDING_MODEL, settings.EMBEDDING_DEVICE, edges, passages])
    if key not in cache:
        vectors = embed([e['text'] for e in edges] + [p['text'] for p in passages.values()])
        cache.clear()  # Keep only one snapshot/variant; no persistent stale index.
        cache[key] = (vectors[:len(edges)], vectors[len(edges):])
        service._graph_embedding_cache = cache
        trace['index_cache_hit'] = False
    else:
        trace['index_cache_hit'] = True
    edge_vectors, passage_vectors = cache[key]
    q = embed([query])[0]
    passage_scores = normalize(passage_vectors @ q)
    edge_scores = normalize(edge_vectors @ q) if edges else np.array([])
    selected = []
    if request.retrieval == 'hipporag2' and edges:
        indices = sorted(range(len(edges)), key=lambda i: (-edge_scores[i], edges[i]['id']))[:30]
        candidates = [dict(id=edges[i]['id'], triple=edges[i]['text'], status=edges[i]['status']) for i in indices]
        aliases = {c['id']: f'e{i+1}' for i, c in enumerate(candidates)}
        schema = create_model('RelevantEdges', selected_ids=(list[Literal[tuple(aliases)]],
            Field(max_length=len(candidates), json_schema_extra={'uniqueItems': True})))
        output = business_run.json_call(service, run, 'graph_retrieval_filter',
            filter_triple_messages[0]['content'] + '\n프로젝트 출력 계약: fact 대신 selected_ids에 제공 id만 반환한다. '
            '여러 단계의 연결에 필요한 관계도 선택한다. has_concept는 검색 연결이며 승인된 사실이나 is-a가 아니다.',
            dict(question=query, candidate_facts=candidates), schema, reference_map=aliases)
        trace['candidate_edge_ids'] = [c['id'] for c in candidates]
        if output is None:
            raise ValueError('관계 선택 모델 호출 실패: 검색 성공으로 처리하지 않습니다.')
        selected = list(dict.fromkeys(output['selected_ids']))
        trace['selected_edge_ids'] = selected
    ranked, seeds = rank(graph, edges, passages, edge_scores, passage_scores, set(selected), len(passages))
    trace['seed_node_scores'] = seeds
    if not seeds:
        trace['fallback'] = 'dense_passages' if request.retrieval == 'hipporag2' else 'dense_baseline'
    trace['ranked_passages'] = [dict(id=p, score=s, evidence=passages[p]['evidence'],
                                   claim_ids=passages[p]['claim_ids']) for p, s in ranked]
    if run.get('answer_basis') == 'source_passages_not_ontology_approval':
        hits = [dict(block_id=pid, file_id=passages[pid]['evidence']['source_version_id'],
                     score=score, selection_reason=request.retrieval) for pid, score in ranked[:request.limit]]
        trace['elapsed_s'] = monotonic() - started
        trace['ranking_is_semantic_validation'] = False
        business_run.save(service, run)
        return hits
    # Existing reviewed-snapshot consumer keeps approved claim bundles.
    hits, seen = [], set()
    for pid, score in ranked:
        for cid in passages[pid]['claim_ids']:
            if cid not in seen:
                hits.append(dict(block_id=cid, file_id=passages[pid]['evidence']['source_version_id'],
                                 score=score, passage_id=pid, selection_reason=request.retrieval))
                seen.add(cid)
                if len(hits) == request.limit:
                    break
        if len(hits) == request.limit:
            break
    trace['elapsed_s'] = monotonic() - started
    trace['ranking_is_semantic_validation'] = False
    business_run.save(service, run)
    return hits
