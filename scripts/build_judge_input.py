"""STEP3 준비: judge 입력 생성 — pool의 각 (쿼리,후보)쌍에 후보 본문 첨부. exaone 전수 채점용."""
import json, os, chromadb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
data = col.get(include=['documents', 'metadatas'])
text_by_case = {}
for sid, doc, meta in zip(data['ids'], data['documents'], data['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    if cid not in text_by_case:
        text_by_case[cid] = doc or ''

queries = {}
for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl')):
    q = json.loads(l)
    queries[q['query_id']] = q
pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))

out = []
for qid, p in pool.items():
    q = queries[qid]
    top10 = set(p['dense'][:10]) | set(p['bm25'][:10]) | set(p['hybrid'][:10])
    for cid in p['pool']:
        if cid.startswith('CASE-POLICY'):  # 안전: 정책 Q&A 제외(민원만)
            continue
        out.append({
            'query_id': qid,
            'query': q['query'],
            'case_id': cid,
            'doc_text': text_by_case.get(cid, '')[:2000],
            'high_impact': cid in top10,  # top10이면 고영향(강검증 우선)
        })

outp = os.path.join(ROOT, 'data/evaluation/v3_rebuild/judge_input.jsonl')
with open(outp, 'w') as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
hi = sum(1 for r in out if r['high_impact'])
print(f'judge 입력 {len(out)} pair (high_impact={hi}) -> {outp}')
