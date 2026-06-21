"""grounding 개선 1단계: false-friend hard set 추출.
false-friend = Codex가 위험 플래그(결론반대·법령다름·시점불일치)를 달았는데 검색(dense/hybrid)이
상위(top-10)로 올린 사례 = '닮아서 상위인데 답변에 쓰면 위험'. 현재 필터가 이걸 거르는지 측정할 대상."""
import json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
RISK = {'opposite_outcome', 'wrong_legal_framework', 'outdated_or_wrong_jurisdiction'}  # generic 제외

risk = {}
for fn in ['qrels_raw_codex.jsonl', 'qrels_raw_codex_morph.jsonl']:
    for l in open(os.path.join(EVAL, fn), encoding='utf-8'):
        r = json.loads(l)
        flags = r.get('risk_flags') or {}
        tf = [k for k, v in flags.items() if v and k in RISK]
        if tf:
            risk[(r['query_id'], r['case_id'])] = {'flags': tf, 'score': r.get('score'), 'reason': r.get('reason', '')}

pool = json.load(open(os.path.join(EVAL, 'pool.json')))
hard = []
for (q, c), info in risk.items():
    if q not in pool:
        continue
    d10 = pool[q]['dense'][:10]
    h10 = pool[q]['hybrid'][:10]
    in_d, in_h = c in d10, c in h10
    if in_d or in_h:   # 검색이 상위로 올린 위험 사례 = false-friend
        hard.append({
            'query_id': q, 'case_id': c, 'flags': info['flags'], 'score': info['score'],
            'rank_dense': d10.index(c) + 1 if in_d else None,
            'rank_hybrid': h10.index(c) + 1 if in_h else None,
            'reason': info['reason'],
        })

out = os.path.join(EVAL, 'false_friend_hardset.jsonl')
with open(out, 'w', encoding='utf-8') as f:
    for h in sorted(hard, key=lambda x: (x['rank_hybrid'] or 99, x['rank_dense'] or 99)):
        f.write(json.dumps(h, ensure_ascii=False) + '\n')

fc = collections.Counter(f for h in hard for f in h['flags'])
print(f'false-friend hard set: {len(hard)}건  -> {out}')
print(f'  플래그별: {dict(fc)}')
print(f'  결론반대(opposite_outcome) 상위진입: {sum(1 for h in hard if "opposite_outcome" in h["flags"])}건')
print(f'  score 분포: {dict(collections.Counter(h["score"] for h in hard))}')
print(f'  top-3 진입(가장 위험): {sum(1 for h in hard if (h["rank_hybrid"] or 99)<=3 or (h["rank_dense"] or 99)<=3)}건')
print('\n  예시 3건:')
for h in sorted(hard, key=lambda x: (x['rank_hybrid'] or 99))[:3]:
    print(f"   {h['query_id']} {h['case_id']} flags={h['flags']} score={h['score']} hyb순위={h['rank_hybrid']} | {h['reason'][:60]}")
