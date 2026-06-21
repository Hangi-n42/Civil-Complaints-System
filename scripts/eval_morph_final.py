"""확장 pool 재judge 후 최종 비교: 형태소 BM25/hybrid vs dense.
qrels = 기존 Codex + morph(198) 병합. ideal(IDCG)은 형태소 신규 top-10을 더한 확장 pool 기준(공정)."""
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
    # 확장 pool(ideal용): 기존 pool + 형태소 BM25/hybrid top-10 신규
    pool[qid]['pool_ext'] = sorted(set(pool[qid]['pool']) | set(bm_ids[:10]) | set(morph_hyb[qid][:10]))

def dcg(gs):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gs))
def ndcg(qid, ranking, k=10):
    gs = [qrels.get((qid, c), 0) for c in ranking[:k]]
    ideal = sorted((qrels.get((qid, c), 0) for c in pool[qid]['pool_ext']), reverse=True)[:k]
    idc = dcg(ideal)
    return dcg(gs) / idc if idc > 0 else 0.0
def mean_ndcg(rk):
    return statistics.mean(ndcg(qid, rk[qid]) for qid in queries)

# 커버리지: 형태소 top-10 채점률(이제 거의 100%여야)
cov_in = cov_tot = 0
for qid in queries:
    for c in morph_bm[qid][:10]:
        cov_tot += 1
        if (qid, c) in qrels:
            cov_in += 1

dense = {qid: pool[qid]['dense'] for qid in queries}
eojeol_hyb = {qid: pool[qid]['hybrid'] for qid in queries}
print('=== 확장 pool 재judge 후 nDCG@10 (linear, ideal=확장 pool) ===')
print(f'  dense         : {mean_ndcg(dense):.4f}')
print(f'  형태소 BM25   : {mean_ndcg(morph_bm):.4f}')
print(f'  형태소 hybrid : {mean_ndcg(morph_hyb):.4f}')
print(f'  (참고)어절 hybrid: {mean_ndcg(eojeol_hyb):.4f}')
print(f'\n형태소 BM25 top-10 채점 커버리지: {cov_in}/{cov_tot} ({100 * cov_in // cov_tot}%)')

def boot_ci(diffs, n=2000):
    random.seed(42); N = len(diffs); ms = []
    for _ in range(n):
        ms.append(sum(diffs[random.randrange(N)] for _ in range(N)) / N)
    ms.sort(); return ms[int(0.025 * n)], ms[int(0.975 * n)]
qids = list(queries)
print('\n=== paired ΔnDCG@10 + 95% bootstrap CI ===')
for name, a, b in [('형태소hybrid − dense', morph_hyb, dense),
                   ('형태소BM25 − dense', morph_bm, dense),
                   ('형태소hybrid − 어절hybrid', morph_hyb, eojeol_hyb)]:
    diffs = [ndcg(q, a[q]) - ndcg(q, b[q]) for q in qids]
    md = statistics.mean(diffs); lo, hi = boot_ci(diffs)
    sig = '유의' if (lo > 0 or hi < 0) else '무의(0 포함)'
    wins = sum(1 for d in diffs if d > 1e-9)
    print(f'  Δ({name}) = {md:+.4f}  [{lo:+.4f}, {hi:+.4f}]  {sig}  (a 우세 {wins}/{len(diffs)})')
