"""
V3 평가셋 검색 성능 비교
- BM25 (인메모리)
- BGE-m3 Dense (ChromaDB 직접, 어댑티브 없음)
- BGE-m3 Adaptive (RetrievalService + 어댑티브 라우터)

qrels: data/evaluation/v3/qrels.tsv (CASE-XXXXXX 레벨)
코퍼스: data/evaluation/v3/corpus_meta.json (9,132건)
쿼리: data/evaluation/v3/queries.jsonl (50건)
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.evaluation.metrics import RunRecord, evaluate_run
from app.evaluation.datasets import QrelRecord

DATA_DIR = PROJECT_ROOT / "data" / "evaluation" / "v3"
REPORT_DIR = PROJECT_ROOT / "reports" / "retrieval" / "v3"
TOP_K = 10


# ──────────────────────────────────────────────
# BM25 (인메모리)
# ──────────────────────────────────────────────

class BM25:
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(corpus)
        self.doc_freqs: list[Counter] = []
        self.doc_len: list[int] = []
        self.idf: dict[str, float] = {}
        self._build(corpus)

    def _tok(self, text: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9가-힣]+", text.lower())

    def _build(self, corpus: list[str]) -> None:
        nd: dict[str, int] = {}
        for doc in corpus:
            freq = Counter(self._tok(doc))
            self.doc_freqs.append(freq)
            self.doc_len.append(sum(freq.values()))
            for w in freq:
                nd[w] = nd.get(w, 0) + 1
        self.avgdl = sum(self.doc_len) / self.n if self.n else 0
        for w, df in nd.items():
            self.idf[w] = math.log(((self.n - df + 0.5) / (df + 0.5)) + 1)

    def top_k(self, query: str, k: int) -> list[tuple[int, float]]:
        scores = [0.0] * self.n
        for q in self._tok(query):
            idf = self.idf.get(q, 0.0)
            if idf == 0.0:
                continue
            for i in range(self.n):
                f = self.doc_freqs[i].get(q, 0)
                if f == 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += idf * f * (self.k1 + 1) / denom
        ranked = sorted(range(self.n), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in ranked[:k]]


# ──────────────────────────────────────────────
# 데이터 로딩
# ──────────────────────────────────────────────

def load_queries() -> list[dict[str, Any]]:
    queries = []
    with (DATA_DIR / "queries.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))
    return queries


def load_qrels() -> list[QrelRecord]:
    qrels = []
    with (DATA_DIR / "qrels.tsv").open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            parts = line.split("\t")
            if lineno == 1 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) == 4:
                qid, _, docid, rel = parts
            elif len(parts) == 3:
                qid, docid, rel = parts
            else:
                continue
            qrels.append(QrelRecord(qid=qid, docid=docid, relevance=int(rel)))
    return qrels


def load_corpus() -> list[dict[str, Any]]:
    with (DATA_DIR / "corpus_meta.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def chunk_to_case(chroma_id: str) -> str:
    """ChromaDB ID를 case_id 레벨로 변환.

    형식: CASE-XXXXXX::CASE-XXXXXX__chunk-N 또는 CASE-XXXXXX__chunk-N 또는 CASE-XXXXXX
    """
    if "::" in chroma_id:
        return chroma_id.split("::")[0]
    if "__chunk-" in chroma_id:
        return chroma_id.split("__chunk-")[0]
    return chroma_id


def dedup_to_case(hits: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """chunk 레벨 결과를 case 레벨로 병합 (case당 최고 점수 유지)."""
    best: dict[str, float] = {}
    for chunk_id, score in hits:
        cid = chunk_to_case(chunk_id)
        if cid not in best or score > best[cid]:
            best[cid] = score
    return sorted(best.items(), key=lambda x: x[1], reverse=True)


def build_run(qid: str, hits: list[tuple[str, float]]) -> list[RunRecord]:
    return [
        RunRecord(qid=qid, docid=cid, score=score, rank=rank)
        for rank, (cid, score) in enumerate(hits, 1)
    ]


# ──────────────────────────────────────────────
# 평가 실행
# ──────────────────────────────────────────────

def run_bm25(queries: list[dict], corpus: list[dict]) -> dict[str, list[RunRecord]]:
    print("[BM25] 인덱스 구축 중...")
    texts = [doc["chunk_text"] for doc in corpus]
    bm25 = BM25(texts)
    chunk_ids = [doc["chunk_id"] for doc in corpus]

    runs: dict[str, list[RunRecord]] = {}
    for q in queries:
        qid = q["query_id"]
        hits_idx = bm25.top_k(q["query"], TOP_K * 3)  # 중복 제거 감안해 여유 추출
        hits = [(chunk_ids[i], score) for i, score in hits_idx]
        deduped = dedup_to_case(hits)[:TOP_K]
        runs[qid] = build_run(qid, deduped)
    print(f"[BM25] 완료 ({len(queries)}건)")
    return runs


def run_dense(queries: list[dict], collection_name: str = "civil_cases_v1") -> dict[str, list[RunRecord]]:
    import chromadb
    from sentence_transformers import SentenceTransformer
    import torch

    print("[Dense] ChromaDB 연결 중...")
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    col = client.get_collection(collection_name)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[Dense] BGE-m3 임베딩 모델 로딩 ({device})...")
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    runs: dict[str, list[RunRecord]] = {}
    for idx, q in enumerate(queries, 1):
        qid = q["query_id"]
        q_emb = model.encode([q["query"]], normalize_embeddings=True)[0].tolist()
        result = col.query(
            query_embeddings=[q_emb],
            n_results=TOP_K * 3,
            include=["distances", "metadatas"],
        )
        ids = result["ids"][0]
        dists = result["distances"][0]
        metas = result["metadatas"][0]
        # metadata에 case_id가 있으면 사용, 없으면 ChromaDB ID에서 추출
        hits = [
            (meta.get("case_id") or chunk_to_case(cid), 1.0 - float(d))
            for cid, d, meta in zip(ids, dists, metas)
        ]
        deduped = dedup_to_case(hits)[:TOP_K]
        runs[qid] = build_run(qid, deduped)
        if idx % 10 == 0:
            print(f"  {idx}/{len(queries)}")
    print(f"[Dense] 완료 ({len(queries)}건)")
    return runs


def run_adaptive(queries: list[dict]) -> dict[str, list[RunRecord]]:
    from app.retrieval.service import RetrievalService

    TOPIC_MAP = {
        "복지": "welfare",
        "교통": "traffic",
        "환경": "environment",
        "건설": "construction",
        "도로": "traffic",
        "주택": "welfare",
        "소음": "environment",
    }

    def map_topic(category: str) -> str:
        for ko, en in TOPIC_MAP.items():
            if ko in (category or ""):
                return en
        return "general"

    print("[Adaptive] RetrievalService 초기화 중...")
    svc = RetrievalService()

    async def _search_all():
        runs: dict[str, list[RunRecord]] = {}
        for idx, q in enumerate(queries, 1):
            qid = q["query_id"]
            topic = map_topic(q.get("category", ""))
            results = await svc.search(
                query=q["query"],
                top_k=TOP_K * 3,
                topic_type=topic,
                retrieval_policy=None,
            )
            hits = [(r.get("case_id") or chunk_to_case(r.get("chunk_id") or ""), float(r.get("score", 0))) for r in results]
            deduped = dedup_to_case(hits)[:TOP_K]
            runs[qid] = build_run(qid, deduped)
            if idx % 10 == 0:
                print(f"  {idx}/{len(queries)}")
        return runs

    result = asyncio.run(_search_all())
    print(f"[Adaptive] 완료 ({len(queries)}건)")
    return result


def compute_metrics(runs: dict[str, list[RunRecord]], qrels: list[QrelRecord]) -> dict[str, float]:
    all_records = [r for records in runs.values() for r in records]
    return evaluate_run(qrels, all_records)


def print_table(results: dict[str, dict[str, float]]) -> None:
    metrics_to_show = ["nDCG@5", "nDCG@10", "Recall@5", "Recall@10", "MRR@5", "MRR@10", "AP@10"]
    # ir_measures 메트릭명 정규화
    key_map = {
        "nDCG@5": "nDCG@5", "nDCG@10": "nDCG@10",
        "Recall@5": "R@5", "Recall@10": "R@10",
        "MRR@5": "RR@5", "MRR@10": "RR@10",
        "AP@10": "AP@10",
    }

    header = f"{'지표':<14}" + "".join(f"{name:>16}" for name in results)
    print("\n" + "=" * (14 + 16 * len(results)))
    print("V3 평가셋 검색 성능 비교 결과")
    print("=" * (14 + 16 * len(results)))
    print(header)
    print("-" * (14 + 16 * len(results)))
    for display_name, ir_key in key_map.items():
        row = f"{display_name:<14}"
        for method_metrics in results.values():
            # ir_measures 키 형식 찾기
            val = None
            for k, v in method_metrics.items():
                if ir_key.lower() in k.lower():
                    val = v
                    break
            row += f"{val:>15.4f}" if val is not None else f"{'N/A':>15}"
        print(row)
    print("=" * (14 + 16 * len(results)))


def main() -> None:
    print("=" * 60)
    print("V3 평가셋 검색 성능 비교 시작")
    print(f"시각: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1] 데이터 로딩...")
    queries = load_queries()
    qrels = load_qrels()
    corpus = load_corpus()
    print(f"  쿼리 {len(queries)}건, qrels {len(qrels)}건, 코퍼스 {len(corpus)}건")

    all_results: dict[str, dict[str, float]] = {}
    all_runs: dict[str, dict[str, list[RunRecord]]] = {}

    # ── BM25 ──
    print("\n[2] BM25 평가...")
    t0 = time.perf_counter()
    bm25_runs = run_bm25(queries, corpus)
    bm25_metrics = compute_metrics(bm25_runs, qrels)
    bm25_time = time.perf_counter() - t0
    all_results["BM25"] = bm25_metrics
    all_runs["BM25"] = bm25_runs
    print(f"  소요: {bm25_time:.1f}초")

    # ── BGE-m3 Dense ──
    print("\n[3] BGE-m3 Dense 평가...")
    t0 = time.perf_counter()
    dense_runs = run_dense(queries)
    dense_metrics = compute_metrics(dense_runs, qrels)
    dense_time = time.perf_counter() - t0
    all_results["BGE-m3 Dense"] = dense_metrics
    all_runs["BGE-m3 Dense"] = dense_runs
    print(f"  소요: {dense_time:.1f}초")

    # ── Adaptive ──
    print("\n[4] BGE-m3 Adaptive 평가...")
    t0 = time.perf_counter()
    adaptive_runs = run_adaptive(queries)
    adaptive_metrics = compute_metrics(adaptive_runs, qrels)
    adaptive_time = time.perf_counter() - t0
    all_results["Adaptive"] = adaptive_metrics
    all_runs["Adaptive"] = adaptive_runs
    print(f"  소요: {adaptive_time:.1f}초")

    # ── 결과 출력 ──
    print_table(all_results)

    # ── JSON 리포트 저장 ──
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "run_id": run_id,
        "eval_set": "V3 (qrels_final, 749쌍, 49쿼리, Q-0036 도메인 외 제외)",
        "top_k": TOP_K,
        "results": {
            name: {k: round(v, 4) for k, v in metrics.items()}
            for name, metrics in all_results.items()
        },
        "latency_seconds": {
            "BM25": round(bm25_time, 2),
            "BGE-m3 Dense": round(dense_time, 2),
            "Adaptive": round(adaptive_time, 2),
        },
    }
    report_path = REPORT_DIR / f"comparison_{run_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 최신 결과를 latest.json으로도 저장
    (REPORT_DIR / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[OK] 리포트 저장: {report_path}")


if __name__ == "__main__":
    main()
