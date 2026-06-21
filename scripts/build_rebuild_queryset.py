"""STEP1: LLM-silver 평가셋 쿼리 구축 — 민원 100(version-neutral) + 정책 50(category stratify).
정책 쿼리는 원문 client_question(leakage는 exclude_case_id + near-dup으로 STEP2/5에서 관리)."""
import json, collections, random, os

random.seed(42)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1) 민원 쿼리 100 (기존 version-neutral)
civil = [json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/version_neutral/queries.jsonl'))]
for q in civil:
    q.setdefault('query_type', 'civil')
    q['source'] = 'civil'

# 2) 정책 50 category 비례 stratify
pol_raw = json.load(open(os.path.join(ROOT, 'data/processed/civil_policy_qna_processed.json')))
by_cat = collections.defaultdict(list)
for r in pol_raw:
    by_cat[r.get('consulting_category') or '미분류'].append(r)
total = len(pol_raw)
TARGET = 50
picked = []
for cat, recs in sorted(by_cat.items(), key=lambda x: -len(x[1])):
    n = max(1, round(TARGET * len(recs) / total))
    picked += [(cat, r) for r in random.sample(recs, min(n, len(recs)))]
picked = picked[:TARGET]

pol_q = []
for i, (cat, r) in enumerate(picked):
    pol_q.append({
        'query_id': f'POL-{i:03d}',
        'query': (r.get('client_question') or '').strip(),
        'source_id': r['source_id'],
        'source': 'policy_qna',
        'category': cat,
        'query_type': 'policy',
        'exclude_case_id': f"CASE-POLICY-{r['source_id']}",
    })
pol_q = [q for q in pol_q if q['query']]  # 빈 쿼리 제외

allq = civil + pol_q
out_dir = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, 'queries.jsonl')
with open(out, 'w') as f:
    for q in allq:
        f.write(json.dumps(q, ensure_ascii=False) + '\n')

print(f'민원 {len(civil)} + 정책 {len(pol_q)} = {len(allq)} 쿼리 → {out}')
print('정책 category 분포:')
for k, v in collections.Counter(q['category'] for q in pol_q).most_common():
    print(f'  {v:2d}  {k}')
