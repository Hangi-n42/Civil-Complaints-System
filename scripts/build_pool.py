"""STEP2: pooling — dense/bm25/hybrid 각 top-50 → 합집합(judge 대상 풀). exclude_case_id 적용."""
import json, os, sys, chromadb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sentence_transformers import SentenceTransformer
from app.retrieval.search.hybrid import InvertedBM25
from app.core.config import settings

TOP = 50
RRF_K = settings.RRF_K

col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
case_ids, texts, seen = [], [], set()
for sid, doc, meta in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    if cid in seen or cid.startswith('CASE-POLICY'):  # 정책 Q&A 제외 — 민원 코퍼스만
        continue
    seen.add(cid); case_ids.append(cid); texts.append(doc or '')
print(f'BM25 빌드: {len(texts)} case')
bm25 = InvertedBM25(texts)
m = SentenceTransformer('BAAI/bge-m3')

queries = [q for q in (json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl'))) if q.get('source') == 'civil']  # 민원 쿼리만
pool = {}
for n, q in enumerate(queries):
    qid, excl, qtext = q['query_id'], q.get('exclude_case_id'), q['query']
    qe = m.encode(qtext, normalize_embeddings=True).tolist()
    dr = col.query(query_embeddings=[qe], n_results=TOP + 200)  # 정책 제외 후 민원 top 확보
    dense_ids, sd = [], set()
    for c in dr['ids'][0]:
        cid = c.split('::')[0]
        if cid == excl or cid in sd or cid.startswith('CASE-POLICY'):  # 정책 Q&A 제외
            continue
        sd.add(cid); dense_ids.append(cid)
        if len(dense_ids) >= TOP:
            break
    bm_ids = []
    for i in bm25.top_k(qtext, TOP + 15):
        cid = case_ids[i]
        if cid == excl:
            continue
        bm_ids.append(cid)
        if len(bm_ids) >= TOP:
            break
    dr_rank = {c: r for r, c in enumerate(dense_ids, 1)}
    br_rank = {c: r for r, c in enumerate(bm_ids, 1)}
    fused = {}
    for c in set(dr_rank) | set(br_rank):
        fused[c] = (1 / (RRF_K + dr_rank[c]) if c in dr_rank else 0) + (1 / (RRF_K + br_rank[c]) if c in br_rank else 0)
    hyb_ids = sorted(fused, key=lambda c: -fused[c])[:TOP]
    pool[qid] = {'dense': dense_ids, 'bm25': bm_ids, 'hybrid': hyb_ids,
                 'pool': sorted(set(dense_ids) | set(bm_ids) | set(hyb_ids))}
    if (n + 1) % 30 == 0:
        print(f'  {n + 1}/{len(queries)}')

out = os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')
json.dump(pool, open(out, 'w'), ensure_ascii=False, indent=1)
tot = sum(len(p['pool']) for p in pool.values())
print(f'완료: {len(queries)} 쿼리, pool pair {tot}, 평균 {tot / len(queries):.1f}/쿼리 -> {out}')
