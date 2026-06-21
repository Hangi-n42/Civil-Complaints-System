"""grounding 개선 2단계: risk-aware verifier로 false-friend hard set 재채점 → 현재 필터(통과 13%)와 비교.
구조화 출력(base_relevance + risk_flags) + cap은 코드로(opposite→0, wrong_legal/outdated→max1). 로컬 exaone3.5:7.8b."""
import asyncio, json, os, sys, chromadb
import httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.core.config import settings

MODEL = os.getenv('FILTER_MODEL', 'exaone3.5:7.8b')
EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
RISK_PROMPT = '''당신은 민원 검색 안전성 평가자입니다. 기준 민원(Query)과 과거 사례(Chunk)를 읽고 JSON으로만 답하세요.
1. base_relevance: 0/1/2 (쟁점·법령·절차 유사도. 2=거의 동일, 1=부분, 0=무관)
2. risk_flags: 아래 위험이 관측되면 배열에 넣으세요(없으면 []):
   - "opposite_outcome": 쟁점은 같으나 결론·방향이 반대(가능↔불가, 책임 인정↔부정, 설치↔이전 등)
   - "wrong_legal_framework": 적용 법령·제도·업종 규제가 명백히 다름
   - "outdated_or_wrong_jurisdiction": 기준 시점·관할·적용 범위가 달라 결론이 바뀜
형식: {"base_relevance": <0|1|2>, "risk_flags": [...]}'''

hard = [json.loads(l) for l in open(os.path.join(EVAL, 'false_friend_hardset.jsonl'), encoding='utf-8')]
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(EVAL, 'queries.jsonl'))) if q.get('source') == 'civil'}
col = chromadb.PersistentClient(path=os.path.join(ROOT, 'data/chroma_db')).get_collection('civil_cases_v3')
got = col.get(include=['documents', 'metadatas'])
doc, meta = {}, {}
for sid, d, m in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((m or {}).get('case_id') or sid).split('::')[0]
    doc.setdefault(cid, d or ''); meta.setdefault(cid, m or {})
def gtext(cid):
    m = meta.get(cid) or {}
    dom = ' '.join(x for x in [m.get('category'), m.get('region')] if x)
    return (f'[{dom}] ' if dom else '') + doc.get(cid, '')[:400]

def cap(base, flags):  # cap은 코드로 결정적 적용
    if 'opposite_outcome' in flags:
        return 0
    if 'wrong_legal_framework' in flags or 'outdated_or_wrong_jurisdiction' in flags:
        return min(base, 1)
    return base

sem = asyncio.Semaphore(5)
async def one(h):
    q = queries.get(h['query_id'])
    if not q:
        return None
    prompt = f"{RISK_PROMPT}\n\n기준 민원(Query):\n{q['query'][:600]}\n\n과거 민원(Chunk):\n{gtext(h['case_id'])[:600]}"
    payload = {'model': MODEL, 'prompt': prompt, 'stream': False, 'format': 'json',
               'options': {'temperature': 0.0, 'num_predict': 80, 'num_ctx': 2048}}
    base, flags = None, []
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate", json=payload)
                resp = json.loads(r.json().get('response', '{}'))
                base = resp.get('base_relevance')
                flags = resp.get('risk_flags') or []
        except Exception:
            base = None
    final = cap(base if isinstance(base, int) else 1, flags) if base is not None else None
    return {**h, 'base': base, 'detected_flags': flags, 'final': final}

async def run():
    res = [r for r in await asyncio.gather(*(one(h) for h in hard)) if r]
    passed = [r for r in res if r['final'] is None or (r['final'] or 0) >= 1]
    print(f"risk-aware verifier (cap 코드 적용): {len(res)}건, 모델 {MODEL}")
    print(f"  ❌ 통과(위험 못 거름): {len(passed)}/{len(res)} ({100*len(passed)//len(res)}%)  ← 현재 필터 13% 대비")
    for flag in ['opposite_outcome', 'wrong_legal_framework', 'outdated_or_wrong_jurisdiction']:
        sub = [r for r in res if flag in r['flags']]
        sp = [r for r in sub if r['final'] is None or (r['final'] or 0) >= 1]
        det = [r for r in sub if flag in r['detected_flags']]
        if sub:
            print(f"  {flag}: 통과 {len(sp)}/{len(sub)} | risk-aware가 위험 탐지 {len(det)}/{len(sub)}")
    with open(os.path.join(EVAL, 'false_friend_risk_aware.jsonl'), 'w', encoding='utf-8') as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'-> {EVAL}/false_friend_risk_aware.jsonl')

asyncio.run(run())
