"""발표 전 얇은 재judge용: 형태소 BM25/hybrid top-10 중 '기존 pool 밖 미채점' 신규 후보만 추출.
→ data/evaluation/v3_rebuild/judge_input_morph.jsonl (기존 judge_input과 동일 형식). dense는 손대지 않음."""
import json, os, sys, chromadb
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
case_ids, texts, doc_by_cid, seen = [], [], {}, set()
for sid, doc, meta in zip(got['ids'], got['documents'], got['metadatas']):
    cid = str((meta or {}).get('case_id') or sid).split('::')[0]
    if cid in seen or cid.startswith('CASE-POLICY'):
        continue
    seen.add(cid); case_ids.append(cid); texts.append(doc or ''); doc_by_cid[cid] = doc or ''
bm25 = H.InvertedBM25(texts)

pool = json.load(open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/pool.json')))
queries = {q['query_id']: q for q in (json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl'))) if q.get('source') == 'civil'}
judged = set()
for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/qrels_raw_codex.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    if r.get('score') is not None:
        judged.add((r['query_id'], r['case_id']))

TOP = 50
out, seen_pair = [], set()
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
    dr = {c: r for r, c in enumerate(pool[qid]['dense'], 1)}
    br = {c: r for r, c in enumerate(bm_ids, 1)}
    fused = {}
    for c in set(dr) | set(br):
        fused[c] = (1 / (RRF_K + dr[c]) if c in dr else 0) + (1 / (RRF_K + br[c]) if c in br else 0)
    hyb = sorted(fused, key=lambda c: -fused[c])[:TOP]
    for cid in set(bm_ids[:10]) | set(hyb[:10]):   # 형태소 BM25·hybrid top-10
        if (qid, cid) in judged or (qid, cid) in seen_pair:
            continue
        seen_pair.add((qid, cid))
        out.append({'query_id': qid, 'query': qtext, 'case_id': cid,
                    'doc_text': doc_by_cid.get(cid, '')[:2000], 'high_impact': True})

outf = os.path.join(ROOT, 'data/evaluation/v3_rebuild/judge_input_morph.jsonl')
with open(outf, 'w', encoding='utf-8') as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
nq = len(set(r['query_id'] for r in out))
print(f'재judge 신규 후보(형태소 top-10, 기존 미채점): {len(out)} pair, {nq} 쿼리, 평균 {len(out)/max(nq,1):.1f}/쿼리')
print(f'-> {outf}')
print(f'(참고: 전체 채점본 8,732 대비 {100*len(out)//8732}% — 얇은 재judge)')
