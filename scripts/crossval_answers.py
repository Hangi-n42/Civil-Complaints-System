"""교차검증: 쿼리답변↔후보답변 유사도 vs Codex score 상관. 담당자 답변(processed)으로 silver 검증."""
import json, re, os
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
proc = {}
for r in json.load(open(os.path.join(ROOT, 'data/processed/processed_consulting_data.json'))):
    a = r.get('consultant_answer')
    if a and a.strip():
        proc[str(r['source_id'])] = a.strip()

qans = {}
for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/queries.jsonl')):
    x = json.loads(l)
    if x['source'] == 'civil':
        qans[x['query_id']] = proc.get(str(x['source_id']))

qrels = {}
for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/qrels_raw_codex.jsonl'), encoding='utf-8'):
    r = json.loads(l)
    if r.get('score') is not None:
        qrels[(r['query_id'], r['case_id'])] = r['score']

def sid(c):
    m = re.search(r'(\d+)', c)
    return m.group(1) if m else None

pairs = []
for (qid, cid), score in qrels.items():
    qa = qans.get(qid)
    ca = proc.get(sid(cid) or '')
    if qa and ca:
        pairs.append((qa, ca, score))
print('교차검증 pair:', len(pairs))

texts = sorted(set([p[0] for p in pairs] + [p[1] for p in pairs]))
print('고유 답변 임베딩:', len(texts))
m = SentenceTransformer('BAAI/bge-m3', device='cpu')
vecs = m.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
emb = {t: v for t, v in zip(texts, vecs)}

sims = np.array([float(np.dot(emb[qa], emb[ca])) for qa, ca, _ in pairs])
scores = np.array([s for _, _, s in pairs])

# Spearman (numpy 구현 — scipy 의존 회피)
def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])

print(f'\nSpearman(답변유사도 vs Codex score) = {spearman(sims, scores):.3f}')
print(f'Pearson  = {float(np.corrcoef(sims, scores)[0,1]):.3f}')
print('score별 답변유사도 평균(단조 증가하면 일치):')
for s in [0, 1, 2]:
    mask = scores == s
    if mask.sum():
        print(f'  score={s}: 유사도 평균 {sims[mask].mean():.3f} ± {sims[mask].std():.3f} (n={mask.sum()})')
