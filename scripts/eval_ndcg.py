"""STEP6: 시스템별 nDCG@10 (dense/bm25/hybrid) — Codex silver qrels 기준.
linear+exp gain, paired Δ + block bootstrap 95% CI."""
import json, math, os, statistics, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
qf = os.path.join(ROOT, 'data/evaluation/v3_rebuild/qrels_raw_codex.jsonl')
qrels = {}
for l in open(qf, encoding='utf-8'):
    r = json.loads(l)
    if r.get('score') is not None:
        qrels[(r['query_id'], r['case_id'])] = r['score']
pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))
SYS = ['dense', 'bm25', 'hybrid']

def dcg(gs):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gs))

def ndcg(qid, ranking, gf, k=10):
    gs = [gf(qrels.get((qid, cid), 0)) for cid in ranking[:k]]
    ideal = sorted((gf(qrels.get((qid, c), 0)) for c in pool[qid]['pool']), reverse=True)[:k]
    idc = dcg(ideal)
    return dcg(gs) / idc if idc > 0 else 0.0

def boot_ci(diffs, n_boot=2000):
    random.seed(42)
    n = len(diffs)
    means = []
    for _ in range(n_boot):
        s = sum(diffs[random.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]

for gname, gf in [('linear(0,1,2)', lambda s: s), ('exp(0,1,3)', lambda s: 2 ** s - 1)]:
    print(f'=== gain {gname} ===')
    per_q = {s: [ndcg(qid, pool[qid][s], gf) for qid in pool] for s in SYS}
    for s in SYS:
        print(f'  {s:7s} nDCG@10 = {statistics.mean(per_q[s]):.4f}')
    print(f'  최고: {max(SYS, key=lambda s: statistics.mean(per_q[s]))}')
    for s in ['dense', 'bm25']:
        diffs = [per_q['hybrid'][i] - per_q[s][i] for i in range(len(pool))]
        md = statistics.mean(diffs)
        lo, hi = boot_ci(diffs)
        sig = '유의' if (lo > 0 or hi < 0) else '무의(0 포함)'
        wins = sum(1 for d in diffs if d > 1e-9)
        print(f'  Δ(hybrid-{s}) = {md:+.4f}  95%CI [{lo:+.4f}, {hi:+.4f}]  {sig}  (hybrid 우세 {wins}/{len(diffs)})')
    print()
