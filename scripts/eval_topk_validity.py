"""지표 타당성(갭1): BE3 실제 답변 생성 범위(grounding top-5, 프롬프트 2~3)와 정렬된 지표로 재계산.
형태소 hybrid=dense 동률이 top-5/3·Success·MRR에서도 유지되는지 확인. (eval_morph_final과 동일 데이터)"""
import json, os, sys, math, statistics, random, chromadb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app.retrieval.search.hybrid as H
from kiwipiepy import Kiwi
from app.core.config import settings

kiwi = Kiwi()
def morph_tok(text):
    return [t.form.lower() for t in kiwi.tokenize(text or '')
            if t.tag[0] in 'NV' or t.tag in ('SL', 'SH', 'SN', 'XR')]
H._tokenize = morph_tok

RRF_K = settings.RRF_K
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
case_ids, texts, seen = [], [], set()
for sid, doc, meta in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    if cid in seen or cid.startswith('CASE-POLICY'):
        continue
    seen.add(cid); case_ids.append(cid); texts.append(doc or '')
bm25 = H.InvertedBM25(texts)

pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))
qrels = {}
for fn in ['qrels_raw_codex.jsonl', 'qrels_raw_codex_morph.jsonl']:
    for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild', fn), encoding='utf-8'):
        r = json.loads(l)
        if r.get('score') is not None:
            qrels[(r['query_id'], r['case_id'])] = r['score']
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl'))) if q.get('source') == 'civil'}

TOP = 50
morph_bm, morph_hyb = {}, {}
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
    dr = {c: r for r, c in enumerate(pool[qid]['dense'], 1)}
    br = {c: r for r, c in enumerate(bm_ids, 1)}
    fused = {}
    for c in set(dr) | set(br):
        fused[c] = (1 / (RRF_K + dr[c]) if c in dr else 0) + (1 / (RRF_K + br[c]) if c in br else 0)
    morph_hyb[qid] = sorted(fused, key=lambda c: -fused[c])[:TOP]
    pool[qid]['pool_ext'] = sorted(set(pool[qid]['pool']) | set(bm_ids[:10]) | set(morph_hyb[qid][:10]))
dense = {qid: pool[qid]['dense'] for qid in queries}

def dcg(gs):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gs))
def ndcg(qid, ranking, k):
    gs = [qrels.get((qid, c), 0) for c in ranking[:k]]
    ideal = sorted((qrels.get((qid, c), 0) for c in pool[qid]['pool_ext']), reverse=True)[:k]
    idc = dcg(ideal)
    return dcg(gs) / idc if idc > 0 else 0.0
def succ(rk, k):
    return statistics.mean(1.0 if any(qrels.get((q, c), 0) >= 1 for c in rk[q][:k]) else 0.0 for q in queries)
def hit(rk, k):
    return statistics.mean(sum(1 for c in rk[q][:k] if qrels.get((q, c), 0) >= 1) for q in queries)
def mrr(rk, k):
    def rr(q):
        for i, c in enumerate(rk[q][:k], 1):
            if qrels.get((q, c), 0) >= 1:
                return 1.0 / i
        return 0.0
    return statistics.mean(rr(q) for q in queries)
def boot_ci(diffs, n=2000):
    random.seed(42); N = len(diffs); ms = []
    for _ in range(n):
        ms.append(sum(diffs[random.randrange(N)] for _ in range(N)) / N)
    ms.sort(); return ms[int(0.025 * n)], ms[int(0.975 * n)]

qids = list(queries)
print('=== BE3 답변 생성 범위 정렬 지표 (grounding top-5, 프롬프트 2~3) ===')
print(f'{"시스템":14s} nDCG@5  nDCG@3  Succ@5  Succ@3  hit@5  MRR@5')
for name, rk in [('dense', dense), ('형태소 hybrid', morph_hyb), ('형태소 BM25', morph_bm)]:
    n5 = statistics.mean(ndcg(q, rk[q], 5) for q in qids)
    n3 = statistics.mean(ndcg(q, rk[q], 3) for q in qids)
    print(f'{name:14s} {n5:.4f}  {n3:.4f}  {succ(rk,5):.4f}  {succ(rk,3):.4f}  {hit(rk,5):.2f}   {mrr(rk,5):.4f}')
print('\n=== 형태소 hybrid − dense, top-5/3에서도 동률 유지되나 (paired 95% CI) ===')
for k in [5, 3]:
    diffs = [ndcg(q, morph_hyb[q], k) - ndcg(q, dense[q], k) for q in qids]
    md = statistics.mean(diffs); lo, hi = boot_ci(diffs)
    sig = '유의' if (lo > 0 or hi < 0) else '무의(0 포함)'
    print(f'  Δ@{k} = {md:+.4f}  [{lo:+.4f}, {hi:+.4f}]  {sig}')
