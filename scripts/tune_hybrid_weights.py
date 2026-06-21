"""형태소 토큰화 후 하이브리드 가중치·RRF 튜닝. BM25 k1/b·RRF-k·dense-bm25 weight grid → nDCG@10.
baseline(형태소 hybrid, k1=1.5/b=0.75/rrf=60/w 1:1) 대비 더 끌어올릴 조합 탐색.
dense는 기존 pool 재사용(임베딩 0), 토큰 캐시로 로컬 수분."""
import json, os, sys, math, statistics, chromadb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import app.retrieval.search.hybrid as H
from kiwipiepy import Kiwi
kiwi = Kiwi()
_cache = {}
def morph_tok(text):
    if text not in _cache:
        _cache[text] = [t.form.lower() for t in kiwi.tokenize(text or '')
                        if t.tag[0] in 'NV' or t.tag in ('SL', 'SH', 'SN', 'XR')]
    return _cache[text]
H._tokenize = morph_tok

EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
case_ids, texts, seen = [], [], set()
for sid, doc, m in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((m or {}).get('case_id') or sid).split('::')[0]
    if cid in seen or cid.startswith('CASE-POLICY'):
        continue
    seen.add(cid); case_ids.append(cid); texts.append(doc or '')
pool = json.load(open(os.path.join(EVAL, 'pool.json')))
qrels = {}
for fn in ['qrels_raw_codex.jsonl', 'qrels_raw_codex_morph.jsonl']:
    for l in open(os.path.join(EVAL, fn), encoding='utf-8'):
        r = json.loads(l)
        if r.get('score') is not None:
            qrels[(r['query_id'], r['case_id'])] = r['score']
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(EVAL, 'queries.jsonl'))) if q.get('source') == 'civil'}
qids = list(queries)
TOP = 50

def dcg(gs):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gs))

for t in texts:  # 토큰화 캐시 워밍 1회
    morph_tok(t)
print(f'토큰 캐시 워밍: {len(texts)} doc')

GRID_K1 = [1.2, 1.5, 2.0]
GRID_B = [0.5, 0.75, 0.9]
GRID_RRF = [40, 60, 80]
GRID_W = [(1.0, 1.0), (1.4, 1.0), (1.0, 1.4)]  # (dense, bm25)
results = []
for k1 in GRID_K1:
    for b in GRID_B:
        bm25 = H.InvertedBM25(texts, k1=k1, b=b)
        bm_top = {}
        for qid in qids:
            q = queries[qid]; excl = q.get('exclude_case_id')
            ids = []
            for i in bm25.top_k(q['query'], TOP + 15):
                c = case_ids[i]
                if c == excl:
                    continue
                ids.append(c)
                if len(ids) >= TOP:
                    break
            bm_top[qid] = ids
        for rrf_k in GRID_RRF:
            for wd, wb in GRID_W:
                per_q = []
                for qid in qids:
                    dr = {c: r for r, c in enumerate(pool[qid]['dense'], 1)}
                    br = {c: r for r, c in enumerate(bm_top[qid], 1)}
                    fused = {}
                    for c in set(dr) | set(br):
                        fused[c] = (wd / (rrf_k + dr[c]) if c in dr else 0) + (wb / (rrf_k + br[c]) if c in br else 0)
                    rank = sorted(fused, key=lambda c: -fused[c])[:TOP]
                    ext = set(pool[qid]['pool']) | set(bm_top[qid][:10]) | set(rank[:10])
                    gs = [qrels.get((qid, c), 0) for c in rank[:10]]
                    ideal = sorted((qrels.get((qid, c), 0) for c in ext), reverse=True)[:10]
                    idc = dcg(ideal)
                    per_q.append(dcg(gs) / idc if idc > 0 else 0.0)
                results.append((statistics.mean(per_q), k1, b, rrf_k, wd, wb))
results.sort(reverse=True)
base = next(r for r in results if r[1:] == (1.5, 0.75, 60, 1.0, 1.0))
print(f'\nbaseline (k1=1.5,b=0.75,rrf=60,w 1:1): nDCG@10 = {base[0]:.4f}  (dense=0.789)')
print('=== top 8 조합 ===')
print(f'{"nDCG@10":9s} k1   b     rrf  w(d:b)')
for r in results[:8]:
    print(f'{r[0]:.4f}   {r[1]}  {r[2]}  {r[3]}   {r[4]}:{r[5]}')
print(f'\n최적 − baseline = {results[0][0]-base[0]:+.4f}')
