"""천장 정체 진단: query(코퍼스 민원 원문)가 검색 결과와 얼마나 유사한지(self-retrieval/near-dup bias).
유사도가 매우 높으면(>0.9) 평가셋이 쉬움 → 천장이 '진짜 잘함'이 아니라 '평가가 쉬움'."""
import json, os, statistics, chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
doc = {}
for sid, d, meta in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    doc.setdefault(cid, d or '')

pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))
qrels = {}
for fn in ['qrels_raw_codex.jsonl', 'qrels_raw_codex_morph.jsonl']:
    for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild', fn), encoding='utf-8'):
        r = json.loads(l)
        if r.get('score') is not None:
            qrels[(r['query_id'], r['case_id'])] = r['score']
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl'))) if q.get('source') == 'civil'}
qids = list(queries)

m = SentenceTransformer('BAAI/bge-m3', device='cpu')
qvec = dict(zip(qids, m.encode([queries[q]['query'] for q in qids], normalize_embeddings=True, show_progress_bar=False)))
need = set()
for qid in qids:
    need.update(pool[qid]['dense'][:5])
    need.update(c for c in pool[qid]['pool'] if qrels.get((qid, c), 0) >= 2)
need = [c for c in need if c in doc]
cvec = dict(zip(need, m.encode([doc[c][:2000] for c in need], normalize_embeddings=True, show_progress_bar=False)))

def cos(a, b): return float(np.dot(a, b))
def pct(xs, t): return 100 * sum(1 for x in xs if x >= t) // max(len(xs), 1)

top1, top1_rel, rel2max = [], [], []
for qid in qids:
    d5 = pool[qid]['dense'][:5]
    if d5 and d5[0] in cvec:
        top1.append(cos(qvec[qid], cvec[d5[0]]))
        top1_rel.append(qrels.get((qid, d5[0]), 0))
    r2 = [c for c in pool[qid]['pool'] if qrels.get((qid, c), 0) >= 2 and c in cvec]
    if r2:
        rel2max.append(max(cos(qvec[qid], cvec[c]) for c in r2))

print('=== self-retrieval / near-dup 진단 (query ↔ 검색 사례 본문 유사도) ===')
print(f'query ↔ dense top-1 유사도: 평균 {statistics.mean(top1):.3f}, 중앙 {statistics.median(top1):.3f}')
print(f'  >0.95: {pct(top1,0.95)}%   >0.90: {pct(top1,0.90)}%   >0.85: {pct(top1,0.85)}%   (높을수록 near-dup/self = 평가 쉬움)')
print(f'dense top-1이 관련(rel>=1)인 비율: {100*sum(1 for r in top1_rel if r>=1)//len(top1_rel)}%')
print(f'query ↔ 최유사 rel2 사례 유사도: 평균 {statistics.mean(rel2max):.3f} (n={len(rel2max)})  >0.90: {pct(rel2max,0.90)}%')
print('\n해석: top-1 유사도 >0.9가 다수면 query가 코퍼스 사례와 거의 동일(self/near-dup) → 천장은 평가가 쉬운 탓.')
