"""grounding 개선 4단계: over-rejection 검증. 위험 녹인 프롬프트가 '정상 사례(rel2, 위험없음)'를
과하게 깎지 않는지. 정상 rel2 샘플 → 현재 RELEVANCE_RUBRIC vs 위험-녹인 프롬프트 채점 → rel>=1 유지율 비교.
유지율이 비슷하면 OK(위험만 거름), 위험-녹인 쪽이 많이 떨어지면 over-rejection."""
import asyncio, json, os, sys, chromadb, random
import httpx
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.core.config import settings
from app.retrieval.grounding_filter import extract_score, build_prompt

MODEL = os.getenv('FILTER_MODEL', 'exaone3.5:7.8b')
EVAL = os.path.join(ROOT, 'data/evaluation/v3_rebuild')
OPP_PROMPT = '''당신은 민원 검색 안전성 평가자입니다. 기준 민원(Query)과 과거 사례(Chunk)를 읽고 0~2점으로 평가하세요.
- 2점: 핵심 쟁점 동일 + 법령/제도/해결책 같음. 거의 그대로 인용 가능.
- 1점: 주제·쟁점 일부 일치하나 세부 달라 방향 참고만.
- 0점: 아래 중 하나라도 해당하면 0점.
  (a) 쟁점/절차가 달라 무관
  (b) 쟁점이 같아도 결론·방향이 반대(가능↔불가, 책임 인정↔부정, 설치↔이전 등)
  (c) 적용 법령·제도·관할·기준시점이 달라 그대로 쓰면 오답
핵심: 닮았어도 결론이 반대거나 법령/관할/시점이 다르면 0점. 경계가 모호하면 낮은 점수.
반드시 JSON: {"score": <0|1|2>}'''

# 정상 사례 = rel2 + risk_flag 없음 (관련 높고 위험 없는 좋은 근거)
risk_pairs = set()
rel2_clean = []
for fn in ['qrels_raw_codex.jsonl', 'qrels_raw_codex_morph.jsonl']:
    for l in open(os.path.join(EVAL, fn), encoding='utf-8'):
        r = json.loads(l)
        flags = [k for k, v in (r.get('risk_flags') or {}).items() if v]
        key = (r['query_id'], r['case_id'])
        if flags:
            risk_pairs.add(key)
        if r.get('score') == 2 and not flags:
            rel2_clean.append(key)
rel2_clean = [k for k in rel2_clean if k not in risk_pairs]
random.seed(42)
sample = random.sample(rel2_clean, min(150, len(rel2_clean)))

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
async def score(prompt, q, c):
    full = f"{prompt}\n\n기준 민원(Query):\n{queries[q]['query'][:600]}\n\n과거 민원(Chunk):\n{gtext(c)[:600]}"
    payload = {'model': MODEL, 'prompt': full, 'stream': False, 'format': 'json',
               'options': {'temperature': 0.0, 'num_predict': 24, 'num_ctx': 2048}}
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=120) as cl:
                r = await cl.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate", json=payload)
                return extract_score(str(r.json().get('response', '')))
        except Exception:
            return None

CUR_RUBRIC = build_prompt('', '').split('\n\n기준')[0]  # 현재 RELEVANCE_RUBRIC만
async def one(key):
    q, c = key
    if q not in queries:
        return None
    cur, opp = await asyncio.gather(score(CUR_RUBRIC, q, c), score(OPP_PROMPT, q, c))
    return {'cur': cur, 'opp': opp}

async def run():
    res = [r for r in await asyncio.gather(*(one(k) for k in sample)) if r]
    cur_keep = sum(1 for r in res if r['cur'] is None or (r['cur'] or 0) >= 1)
    opp_keep = sum(1 for r in res if r['opp'] is None or (r['opp'] or 0) >= 1)
    n = len(res)
    print(f"정상 사례(rel2·위험없음) {n}건 유지율 (rel>=1로 살아남음):")
    print(f"  현재 RELEVANCE_RUBRIC : {cur_keep}/{n} ({100*cur_keep//n}%)")
    print(f"  위험-녹인 프롬프트     : {opp_keep}/{n} ({100*opp_keep//n}%)")
    drop = cur_keep - opp_keep
    print(f"  → 위험-녹인 쪽 추가 탈락: {drop}건 ({100*drop//max(cur_keep,1)}% over-rejection)")
    print("  (작으면 OK: 위험만 거르고 좋은 근거는 유지. 크면 over-rejection 부작용)")

asyncio.run(run())
