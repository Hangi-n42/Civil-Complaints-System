"""
공정 평가용 풀 확장 (pooling-bias 제거).

기존 qrels는 Dense/BM25의 top-10 위주로 풀링돼, reranker가 Dense top-50에서
끌어올린 문서(11~50위)가 미판정 → 오답 처리되는 편향이 있었다
(reports/retrieval/v3/reranker_condensed_eval.json 참고).

이 스크립트는 100개 쿼리 각각에 대해
  Dense top-50  ∪  BM25 top-50
합집합을 만들고, 그중 **아직 qrels에 없는** (query, doc) 쌍만 추출한다.
  - Dense top-50: reranker가 닿을 수 있는 범위 전체를 덮음
  - BM25 top-50: 어휘(키워드) 다양성 → Dense가 놓치는 사각지대 보강
LLM 판정은 judge_fair_pool.py가 수행 (이 스크립트는 LLM 호출 없음).

산출: data/evaluation/v3/pool_to_judge.tsv
       (qid, docid, in_dense, in_bm25, dense_rank, bm25_rank)
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_v3_evaluation import _pick_embedding_device, chunk_to_case
from app.core.config import settings

DATA_DIR = ROOT / "data" / "evaluation" / "v3"
QUERIES_PATH = DATA_DIR / "queries.jsonl"
CORPUS_PATH = DATA_DIR / "corpus_meta.json"
QRELS_PATH = DATA_DIR / "qrels.tsv"
OUT_PATH = DATA_DIR / "pool_to_judge.tsv"

DENSE_K = 50
BM25_K = 50
COLLECTION = "civil_cases_v1"


class BM25:
    """간단한 인메모리 BM25 (build_retrieval_eval_v3_pool.py와 동일 구현)."""

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.corpus_size = len(corpus)
        self.doc_freqs: list[Counter] = []
        self.idf: dict[str, float] = {}
        self.doc_len: list[int] = []
        nd: dict[str, int] = {}
        num_tok = 0
        for document in corpus:
            freqs = Counter(self._tokenize(document))
            self.doc_freqs.append(freqs)
            self.doc_len.append(sum(freqs.values()))
            num_tok += self.doc_len[-1]
            for word in freqs:
                nd[word] = nd.get(word, 0) + 1
        self.avgdl = num_tok / self.corpus_size if self.corpus_size else 0
        for word, freq in nd.items():
            self.idf[word] = math.log(((self.corpus_size - freq + 0.5) / (freq + 0.5)) + 1)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9가-힣]+", text.lower())

    def get_top_k(self, query: str, k: int) -> list[int]:
        scores = [0.0] * self.corpus_size
        for q in self._tokenize(query):
            idf = self.idf.get(q)
            if idf is None:
                continue
            for i in range(self.corpus_size):
                f = self.doc_freqs[i].get(q, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                    scores[i] += idf * f * (self.k1 + 1) / denom
        return sorted(range(self.corpus_size), key=lambda i: scores[i], reverse=True)[:k]


def load_queries() -> list[dict]:
    import json
    out = []
    with QUERIES_PATH.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def load_corpus() -> tuple[list[str], list[str]]:
    """corpus_meta.json → (case_ids, texts) 병렬 리스트. case 1:1 청크."""
    import json
    case_ids, texts = [], []
    with CORPUS_PATH.open(encoding="utf-8") as f:
        for doc in json.load(f):
            case_ids.append(doc.get("case_id", ""))
            texts.append(doc.get("chunk_text", ""))
    return case_ids, texts


def load_existing_pairs() -> set[tuple[str, str]]:
    pairs = set()
    with QRELS_PATH.open(encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            parts = line.strip().split("\t")
            if i == 0 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                pairs.add((parts[0], parts[2]))
            elif len(parts) == 3:
                pairs.add((parts[0], parts[1]))
    return pairs


def dense_topk(queries: list[dict], k: int) -> dict[str, list[str]]:
    import chromadb
    from sentence_transformers import SentenceTransformer

    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    col = client.get_collection(COLLECTION)
    device = _pick_embedding_device()
    print(f"[Dense] BGE-m3 로딩 ({device})...")
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    out: dict[str, list[str]] = {}
    for idx, q in enumerate(queries, 1):
        emb = model.encode([q["query"]], normalize_embeddings=True)[0].tolist()
        res = col.query(query_embeddings=[emb], n_results=k, include=["metadatas"])
        cases, seen = [], set()
        for cid, meta in zip(res["ids"][0], res["metadatas"][0]):
            case = meta.get("case_id") or chunk_to_case(cid)
            if case not in seen:
                seen.add(case)
                cases.append(case)
        out[q["query_id"]] = cases[:k]
        if idx % 20 == 0:
            print(f"  Dense {idx}/{len(queries)}")
    return out


def main() -> None:
    queries = load_queries()
    case_ids, texts = load_corpus()
    existing = load_existing_pairs()
    print(f"쿼리 {len(queries)} / 코퍼스 {len(case_ids)}건 / 기존 판정쌍 {len(existing)}")

    dense = dense_topk(queries, DENSE_K)

    print("[BM25] 인덱스 구축...")
    bm25 = BM25(texts)
    bm25_top: dict[str, list[str]] = {}
    for idx, q in enumerate(queries, 1):
        bm25_top[q["query_id"]] = [case_ids[i] for i in bm25.get_top_k(q["query"], BM25_K)]
        if idx % 20 == 0:
            print(f"  BM25 {idx}/{len(queries)}")

    rows = []
    per_q = []
    for q in queries:
        qid = q["query_id"]
        d_rank = {c: r for r, c in enumerate(dense.get(qid, []), 1)}
        b_rank = {c: r for r, c in enumerate(bm25_top.get(qid, []), 1)}
        union = set(d_rank) | set(b_rank)
        new = [c for c in union if (qid, c) not in existing]
        per_q.append(len(new))
        for c in sorted(new, key=lambda c: (d_rank.get(c, 999), b_rank.get(c, 999))):
            rows.append((qid, c, int(c in d_rank), int(c in b_rank),
                         d_rank.get(c, 0), b_rank.get(c, 0)))

    header = "qid\tdocid\tin_dense\tin_bm25\tdense_rank\tbm25_rank"
    OUT_PATH.write_text(
        header + "\n" + "\n".join("\t".join(map(str, r)) for r in rows) + "\n",
        encoding="utf-8",
    )

    n = len(rows)
    avg = sum(per_q) / len(per_q) if per_q else 0
    est_1 = n * 2 / 3600        # 1모델 × 2s/건
    print("\n" + "=" * 60)
    print(f"신규 판정 대상: {n}쌍 ({len(queries)}쿼리, 쿼리당 평균 {avg:.1f})")
    print(f"저장: {OUT_PATH}")
    print(f"예상 시간 — 1모델 ~{est_1:.1f}h, 2모델(exaone+gemma) ~{est_1*2:.1f}h  (warm 2s/건 기준)")
    print("=" * 60)


if __name__ == "__main__":
    main()
