"""grounding 개선 3단계: 분해(base+flag) 실패(27%) → '위험을 단일 0/1/2 판정에 녹인' 프롬프트로 재측정.
현재 단순 relevance 유지 + 0점 기준에 '결론 반대/법령·관할 다름' 명시. cap 코드 없음(분해 안 함).
현재 13% 대비 opposite를 더 거르나. 모델 env로 교체 가능."""
import asyncio, json, os, sys, chromadb
import httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.core.config import settings
from app.retrieval.grounding_filter import extract_score

MODEL = os.getenv('FILTER_MODEL', 'exaone3.5:7.8b')
EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
PROMPT = '''당신은 민원 검색 안전성 평가자입니다. 기준 민원(Query)과 과거 사례(Chunk)를 읽고 0~2점으로 평가하세요.
- 2점: 핵심 쟁점 동일 + 법령/제도/해결책 같음. 거의 그대로 인용 가능.
- 1점: 주제·쟁점 일부 일치하나 세부 달라 방향 참고만.
- 0점: 아래 중 하나라도 해당하면 0점.
  (a) 쟁점/절차가 달라 무관
  (b) 쟁점이 같아도 결론·방향이 반대(가능↔불가, 책임 인정↔부정, 설치↔이전 등)
  (c) 적용 법령·제도·관할·기준시점이 달라 그대로 쓰면 오답
핵심: 닮았어도 결론이 반대거나 법령/관할/시점이 다르면 0점. 경계가 모호하면 낮은 점수.
반드시 JSON: {"score": <0|1|2>}'''

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

sem = asyncio.Semaphore(5)
async def one(h):
    q = queries.get(h['query_id'])
    if not q:
        return None
    prompt = f"{PROMPT}\n\n기준 민원(Query):\n{q['query'][:600]}\n\n과거 민원(Chunk):\n{gtext(h['case_id'])[:600]}"
    payload = {'model': MODEL, 'prompt': prompt, 'stream': False, 'format': 'json',
               'options': {'temperature': 0.0, 'num_predict': 24, 'num_ctx': 2048}}
    s = None
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate", json=payload)
                s = extract_score(str(r.json().get('response', '')))
        except Exception:
            s = None
    return {**h, 'score': s}

async def run():
    res = [r for r in await asyncio.gather(*(one(h) for h in hard)) if r]
    removed = [r for r in res if r['score'] == 0]
    passed = [r for r in res if r['score'] is None or (r['score'] or 0) >= 1]
    print(f"opposite-녹인 단일 판정: {len(res)}건, 모델 {MODEL}")
    print(f"  ✅ 제거(위험 거름): {len(removed)}/{len(res)} ({100*len(removed)//len(res)}%)")
    print(f"  ❌ 통과(위험 못 거름): {len(passed)}/{len(res)} ({100*len(passed)//len(res)}%)  ← 현재 13% / 분해 27% 대비")
    for flag in ['opposite_outcome', 'wrong_legal_framework', 'outdated_or_wrong_jurisdiction']:
        sub = [r for r in res if flag in r['flags']]
        sp = [r for r in sub if r['score'] is None or (r['score'] or 0) >= 1]
        if sub:
            print(f"  {flag}: 통과 {len(sp)}/{len(sub)}")
    with open(os.path.join(EVAL, 'false_friend_opposite_aware.jsonl'), 'w', encoding='utf-8') as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

asyncio.run(run())
