"""형태소(kiwi) BM25 vs 어절 BM25 재평가. 토큰화만 교체, dense는 기존 pool 재사용.
기존 Codex qrels로 nDCG@10 비교 + 형태소 top-10 pool 커버리지(하한 해석용)."""
import json, os, sys, math, statistics, chromadb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app.retrieval.search.hybrid as H
from kiwipiepy import Kiwi
from app.core.config import settings

kiwi = Kiwi()
def morph_tok(text):
    # 내용어만: 명사(N*)/용언(V*)/외국어(SL)/한자(SH)/숫자(SN)/어근(XR). 조사·어미·기호 제거
    return [t.form.lower() for t in kiwi.tokenize(text or '')
            if t.tag[0] in 'NV' or t.tag in ('SL', 'SH', 'SN', 'XR')]
H._tokenize = morph_tok  # monkey-patch → InvertedBM25가 형태소 토큰화 사용

RRF_K = settings.RRF_K
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
case_ids, texts, seen = [], [], set()
for sid, doc, meta in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    if cid in seen or cid.startswith('CASE-POLICY'):
        continue
    seen.add(cid); case_ids.append(cid); texts.append(doc or '')
print(f'형태소 BM25 빌드: {len(texts)} case')
bm25 = H.InvertedBM25(texts)

pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))
qrels = {}
for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/qrels_raw_codex.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    if r.get('score') is not None:
        qrels[(r['query_id'], r['case_id'])] = r['score']
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl'))) if q.get('source') == 'civil'}

TOP = 50
morph_bm, morph_hyb, cov_in, cov_tot = {}, {}, 0, 0
for qid, q in queries.items():
    excl = q.get('exclude_case_id'); qtext = q['query']
    bm_ids = []
    for i in bm25.top_k(qtext, TOP + 15):
        cid = case_ids[i]
        if cid == excl:
            continue
        bm_ids.append(cid)
        if len(bm_ids) >= TOP:
            break
    morph_bm[qid] = bm_ids
    poolset = set(pool[qid]['pool'])
    for c in bm_ids[:10]:
        cov_tot += 1
        if c in poolset:
            cov_in += 1
    dr = {c: r for r, c in enumerate(pool[qid]['dense'], 1)}
    br = {c: r for r, c in enumerate(bm_ids, 1)}
    fused = {}
    for c in set(dr) | set(br):
        fused[c] = (1 / (RRF_K + dr[c]) if c in dr else 0) + (1 / (RRF_K + br[c]) if c in br else 0)
    morph_hyb[qid] = sorted(fused, key=lambda c: -fused[c])[:TOP]

def dcg(gs):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gs))
def ndcg(qid, ranking, k=10):
    gs = [qrels.get((qid, c), 0) for c in ranking[:k]]
    ideal = sorted((qrels.get((qid, c), 0) for c in pool[qid]['pool']), reverse=True)[:k]
    idc = dcg(ideal)
    return dcg(gs) / idc if idc > 0 else 0.0
def mean_ndcg(rk):
    return statistics.mean(ndcg(qid, rk[qid]) for qid in queries)
def hits10(rk):
    return statistics.mean(sum(1 for c in rk[qid][:10] if qrels.get((qid, c), 0) >= 1) for qid in queries)

eojeol_bm = {qid: pool[qid]['bm25'] for qid in queries}
eojeol_hyb = {qid: pool[qid]['hybrid'] for qid in queries}
dense = {qid: pool[qid]['dense'] for qid in queries}
print('\n=== nDCG@10 (linear, 기존 Codex qrels) ===')
print(f'  어절   BM25  : {mean_ndcg(eojeol_bm):.4f}   형태소 BM25  : {mean_ndcg(morph_bm):.4f}')
print(f'  어절   hybrid: {mean_ndcg(eojeol_hyb):.4f}   형태소 hybrid: {mean_ndcg(morph_hyb):.4f}')
print(f'  (참고) dense : {mean_ndcg(dense):.4f}')
print('\n=== top-10 관련문서(rel>=1) 평균 적중 (pool 내, 공정 비교) ===')
print(f'  어절 BM25 {hits10(eojeol_bm):.2f}  vs  형태소 BM25 {hits10(morph_bm):.2f}  (dense {hits10(dense):.2f})')
print(f'\n형태소 BM25 top-10 pool 커버리지: {cov_in}/{cov_tot} ({100 * cov_in // cov_tot}%)')
print('  (낮으면 형태소가 pool 밖 새 후보 다수 → 위 nDCG는 하한, 재judge 필요)')

import random
def boot_ci(diffs, n=2000):
    random.seed(42); N = len(diffs); ms = []
    for _ in range(n):
        ms.append(sum(diffs[random.randrange(N)] for _ in range(N)) / N)
    ms.sort(); return ms[int(0.025 * n)], ms[int(0.975 * n)]
qids = list(queries)
print('\n=== paired ΔnDCG@10 + 95% bootstrap CI ===')
for name, a, b in [('형태소hybrid − dense', morph_hyb, dense),
                   ('형태소hybrid − 어절hybrid', morph_hyb, eojeol_hyb),
                   ('형태소BM25 − 어절BM25', morph_bm, eojeol_bm)]:
    diffs = [ndcg(q, a[q]) - ndcg(q, b[q]) for q in qids]
    md = statistics.mean(diffs); lo, hi = boot_ci(diffs)
    sig = '유의' if (lo > 0 or hi < 0) else '무의(0 포함)'
    print(f'  Δ({name}) = {md:+.4f}  [{lo:+.4f}, {hi:+.4f}]  {sig}')
