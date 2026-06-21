"""grounding 개선 1단계: 현재 grounding filter가 false-friend를 얼마나 통과시키나 측정.
현재 필터 함수(grounding_filter.score_relevance, RELEVANCE_RUBRIC=단순 relevance)를 그대로 호출.
제거(위험 거름)=score 0 / 통과(위험 못 거름)=score>=1 또는 None(fail-open). 로컬 exaone3.5:7.8b."""
import asyncio, json, os, sys, chromadb
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.retrieval.grounding_filter import score_relevance

MODEL = os.getenv('FILTER_MODEL', 'exaone3.5:7.8b')
EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
hard = [json.loads(l) for l in open(os.path.join(EVAL, 'false_friend_hardset.jsonl'), encoding='utf-8')]
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(EVAL, 'queries.jsonl'))) if q.get('source') == 'civil'}

col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
doc, meta = {}, {}
for sid, d, m in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((m or {}).get('case_id') or sid).split('::')[0]
    doc.setdefault(cid, d or ''); meta.setdefault(cid, m or {})

def gtext(cid):  # 현재 필터의 grounding_text 근사: [도메인] + 본문 조각
    m = meta.get(cid) or {}
    dom = ' '.join(x for x in [m.get('category'), m.get('region')] if x)
    return (f'[{dom}] ' if dom else '') + doc.get(cid, '')[:400]

sem = asyncio.Semaphore(5)
async def one(h):
    q = queries.get(h['query_id'])
    if not q:
        return None
    async with sem:
        s = await score_relevance(q['query'], gtext(h['case_id']), model=MODEL)
    return {**h, 'filter_score': s}

async def run():
    res = [r for r in await asyncio.gather(*(one(h) for h in hard)) if r]
    removed = [r for r in res if r['filter_score'] == 0]
    none = [r for r in res if r['filter_score'] is None]
    passed = [r for r in res if r['filter_score'] is None or (r['filter_score'] or 0) >= 1]
    print(f'측정 false-friend: {len(res)}건 (모델 {MODEL})')
    print(f'  ✅ 제거(위험 거름, score=0): {len(removed)}/{len(res)} ({100*len(removed)//len(res)}%)')
    print(f'  ❌ 통과(위험 못 거름, score>=1 또는 None): {len(passed)}/{len(res)} ({100*len(passed)//len(res)}%)')
    print(f'     (그중 채점실패 None=permissive 통과: {len(none)}건)')
    for flag in ['opposite_outcome', 'wrong_legal_framework', 'outdated_or_wrong_jurisdiction']:
        sub = [r for r in res if flag in r['flags']]
        sp = [r for r in sub if r['filter_score'] is None or (r['filter_score'] or 0) >= 1]
        if sub:
            print(f'     {flag}: {len(sp)}/{len(sub)} 통과')
    with open(os.path.join(EVAL, 'false_friend_current_filter.jsonl'), 'w', encoding='utf-8') as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'-> {EVAL}/false_friend_current_filter.jsonl')

asyncio.run(run())
