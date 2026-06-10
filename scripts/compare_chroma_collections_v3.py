"""Compare two Chroma collections on the v3 retrieval evaluation set."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.datasets import QrelRecord, sha256_file
from app.evaluation.metrics import RunRecord, evaluate_run, per_query_metric


DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_PERSIST_DIR = PROJECT_ROOT / "data" / "chroma_db"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "be1_restructured_v1_collection_ab.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "be1_restructured_v1_collection_ab.md"

METRIC_ORDER = ["nDCG@5", "nDCG@10", "R@5", "R@10", "RR@5", "RR@10", "AP@10", "P@5"]


def _pick_embedding_device() -> str:
    import torch

    env = os.getenv("EMBEDDING_DEVICE", "").strip().lower()
    if env in {"cuda", "mps", "cpu"}:
        if env == "cuda" and not torch.cuda.is_available():
            return "mps" if torch.backends.mps.is_available() else "cpu"
        if env == "mps" and not torch.backends.mps.is_available():
            return "cpu"
        return env
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_queries(path: Path) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            qid = str(row.get("query_id") or row.get("qid") or row.get("id") or "").strip()
            query = str(row.get("query") or row.get("text") or "").strip()
            if not qid or not query:
                raise ValueError(f"{path} {line_number}번째 줄에 query_id 또는 query가 없습니다")
            queries.append({"query_id": qid, "query": query})
    return queries


def load_qrels(path: Path) -> list[QrelRecord]:
    qrels: list[QrelRecord] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if line_number == 1 and parts[0].lower() in {"qid", "query_id"}:
                continue
            if len(parts) >= 4:
                qid, _, docid, relevance = parts[:4]
            elif len(parts) >= 3:
                qid, docid, relevance = parts[:3]
            else:
                raise ValueError(f"{path} {line_number}번째 줄 형식이 올바르지 않습니다: {raw!r}")
            qrels.append(QrelRecord(qid=qid, docid=docid, relevance=int(relevance)))
    return qrels


def chunk_to_case(chroma_id: str) -> str:
    if "::" in chroma_id:
        return chroma_id.split("::", 1)[0]
    if "__chunk-" in chroma_id:
        return chroma_id.split("__chunk-", 1)[0]
    return chroma_id


def dedup_to_case(hits: list[tuple[str, float]], top_k: int) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for raw_id, score in hits:
        case_id = chunk_to_case(raw_id)
        if case_id not in best or score > best[case_id]:
            best[case_id] = score
    return sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_k]


def build_run(qid: str, hits: list[tuple[str, float]]) -> list[RunRecord]:
    return [
        RunRecord(qid=qid, docid=case_id, score=score, rank=rank)
        for rank, (case_id, score) in enumerate(hits, start=1)
    ]


def run_collection(
    *,
    client: Any,
    collection_name: str,
    queries: list[dict[str, Any]],
    query_embeddings: list[list[float]],
    top_k: int,
) -> tuple[dict[str, list[RunRecord]], dict[str, Any]]:
    started = time.perf_counter()
    collection = client.get_collection(collection_name)
    count = collection.count()
    result = collection.query(
        query_embeddings=query_embeddings,
        n_results=top_k * 3,
        include=["distances", "metadatas"],
    )

    runs: dict[str, list[RunRecord]] = {}
    top1_by_query: dict[str, str] = {}
    for query, ids, distances, metadatas in zip(
        queries,
        result["ids"],
        result["distances"],
        result["metadatas"],
    ):
        hits = []
        for chroma_id, distance, metadata in zip(ids, distances, metadatas):
            case_id = ""
            if isinstance(metadata, dict):
                case_id = str(metadata.get("case_id") or "").strip()
            hits.append((case_id or chunk_to_case(str(chroma_id)), 1.0 - float(distance)))
        deduped = dedup_to_case(hits, top_k)
        qid = query["query_id"]
        runs[qid] = build_run(qid, deduped)
        top1_by_query[qid] = deduped[0][0] if deduped else ""

    elapsed = time.perf_counter() - started
    return runs, {
        "collection": collection_name,
        "count": count,
        "elapsed_sec": elapsed,
        "query_per_sec": len(queries) / elapsed if elapsed > 0 else 0.0,
        "top1_by_query": top1_by_query,
    }


def flatten_runs(runs: dict[str, list[RunRecord]]) -> list[RunRecord]:
    return [record for records in runs.values() for record in records]


def metric_value(metrics: dict[str, float], key: str) -> float:
    for metric_key, value in metrics.items():
        if metric_key == key:
            return value
    return 0.0


def ordered_metric_keys(*metric_sets: dict[str, float]) -> list[str]:
    all_keys = {key for metric_set in metric_sets for key in metric_set}
    ordered = [key for key in METRIC_ORDER if key in all_keys]
    return ordered + sorted(all_keys - set(ordered))


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def compare_per_query(
    qrels: list[QrelRecord],
    baseline_run: list[RunRecord],
    candidate_run: list[RunRecord],
) -> dict[str, Any]:
    baseline = per_query_metric(qrels, baseline_run)
    candidate = per_query_metric(qrels, candidate_run)
    rows = []
    for qid in sorted(set(baseline) | set(candidate)):
        before = baseline.get(qid, 0.0)
        after = candidate.get(qid, 0.0)
        rows.append(
            {
                "query_id": qid,
                "baseline_nDCG@10": before,
                "candidate_nDCG@10": after,
                "delta_nDCG@10": after - before,
            }
        )

    epsilon = 1e-9
    improved = sum(1 for row in rows if row["delta_nDCG@10"] > epsilon)
    regressed = sum(1 for row in rows if row["delta_nDCG@10"] < -epsilon)
    tied = len(rows) - improved - regressed
    return {
        "summary": {
            "total": len(rows),
            "improved": improved,
            "tied": tied,
            "regressed": regressed,
        },
        "top_improvements": [
            row
            for row in sorted(rows, key=lambda row: row["delta_nDCG@10"], reverse=True)
            if row["delta_nDCG@10"] > epsilon
        ][:10],
        "top_regressions": [
            row
            for row in sorted(rows, key=lambda row: row["delta_nDCG@10"])
            if row["delta_nDCG@10"] < -epsilon
        ][:10],
        "rows": rows,
    }


def format_float(value: float) -> str:
    return f"{value:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    baseline_name = payload["baseline_collection"]
    candidate_name = payload["candidate_collection"]
    metric_keys = payload["metric_keys"]
    baseline_metrics = payload["metrics"][baseline_name]
    candidate_metrics = payload["metrics"][candidate_name]
    deltas = payload["metric_deltas"]
    per_query = payload["per_query_nDCG@10"]
    collection_stats = payload["collection_stats"]
    top1 = payload["top1_comparison"]

    lines = [
        "# BE1 구조화 컬렉션 검색 성능 비교",
        "",
        "## 요약",
        "",
        f"- 기준 컬렉션: `{baseline_name}`",
        f"- 후보 컬렉션: `{candidate_name}`",
        f"- 검색 실행 쿼리: {payload['query_count']}건",
        f"- qrels 보유 쿼리: {payload['judged_query_count']}건",
        f"- qrels: `{payload['qrels_path']}` ({payload['qrel_count']}개 라벨, {payload['qrels_sha256']})",
        f"- 검색 방식: BGE-m3 dense 검색, case_id 단위 중복 제거 후 Top-{payload['top_k']} 평가",
        f"- 임베딩 디바이스: `{payload['embedding_device']}`",
        "",
        "## 전체 지표",
        "",
        "| 지표 | 기준 | 후보 | 변화 |",
        "|---|---:|---:|---:|",
    ]
    for key in metric_keys:
        before = baseline_metrics.get(key, 0.0)
        after = candidate_metrics.get(key, 0.0)
        delta = deltas.get(key, 0.0)
        lines.append(f"| {key} | {format_float(before)} | {format_float(after)} | {delta:+.4f} |")

    lines.extend(
        [
            "",
            "## 쿼리별 nDCG@10 변화",
            "",
            f"- 비교 대상: {per_query['summary']['total']}건",
            f"- 개선: {per_query['summary']['improved']}건",
            f"- 동일: {per_query['summary']['tied']}건",
            f"- 하락: {per_query['summary']['regressed']}건",
            f"- 전체 검색 쿼리 Top-1 결과 변경: {top1['changed']}건 / {top1['total']}건",
            "",
            "### 개선 상위",
            "",
            "| query_id | 기준 nDCG@10 | 후보 nDCG@10 | 변화 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in per_query["top_improvements"]:
        lines.append(
            "| {query_id} | {baseline_nDCG@10:.4f} | {candidate_nDCG@10:.4f} | {delta_nDCG@10:+.4f} |".format(
                **row
            )
        )
    if not per_query["top_improvements"]:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "### 하락 상위",
            "",
            "| query_id | 기준 nDCG@10 | 후보 nDCG@10 | 변화 |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in per_query["top_regressions"]:
        lines.append(
            "| {query_id} | {baseline_nDCG@10:.4f} | {candidate_nDCG@10:.4f} | {delta_nDCG@10:+.4f} |".format(
                **row
            )
        )
    if not per_query["top_regressions"]:
        lines.append("| - | - | - | - |")

    lines.extend(
        [
            "",
            "## 실행 정보",
            "",
            "| 컬렉션 | 적재 건수 | 검색 시간(초) | 초당 쿼리 수 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in (baseline_name, candidate_name):
        stat = collection_stats[name]
        lines.append(
            f"| `{name}` | {stat['count']} | {stat['elapsed_sec']:.2f} | {stat['query_per_sec']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 해석",
            "",
            "- 이 리포트는 컬렉션 자체의 검색 품질 차이를 보기 위한 1차 비교입니다.",
            "- 집계 지표는 qrels가 있는 쿼리만 평가에 반영합니다.",
            "- 쿼리 원문과 검색 본문은 산출물에 포함하지 않았고, 평가 ID와 집계 지표만 남겼습니다.",
            "- 기본 컬렉션 전환 여부는 이 결과와 별도 스모크 테스트를 함께 보고 결정하는 것이 안전합니다.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist-dir", type=Path, default=DEFAULT_PERSIST_DIR)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--baseline", default="civil_cases_v1")
    parser.add_argument("--candidate", default="civil_cases_be1_restructured_v1")
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    import chromadb
    from sentence_transformers import SentenceTransformer

    queries = load_queries(args.queries)
    qrels = load_qrels(args.qrels)
    judged_query_count = len({qrel.qid for qrel in qrels})
    device = _pick_embedding_device()

    print(f"[LOAD] queries={len(queries)} qrels={len(qrels)}")
    print(f"[MODEL] {args.embedding_model} ({device})")
    model_started = time.perf_counter()
    model = SentenceTransformer(args.embedding_model, device=device)
    embeddings = model.encode(
        [query["query"] for query in queries],
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).tolist()
    embedding_elapsed = time.perf_counter() - model_started
    print(f"[MODEL] query embeddings completed in {embedding_elapsed:.2f}s")

    client = chromadb.PersistentClient(path=str(args.persist_dir))
    baseline_runs, baseline_stat = run_collection(
        client=client,
        collection_name=args.baseline,
        queries=queries,
        query_embeddings=embeddings,
        top_k=args.top_k,
    )
    candidate_runs, candidate_stat = run_collection(
        client=client,
        collection_name=args.candidate,
        queries=queries,
        query_embeddings=embeddings,
        top_k=args.top_k,
    )

    baseline_flat = flatten_runs(baseline_runs)
    candidate_flat = flatten_runs(candidate_runs)
    baseline_metrics = evaluate_run(qrels, baseline_flat)
    candidate_metrics = evaluate_run(qrels, candidate_flat)
    metric_keys = ordered_metric_keys(baseline_metrics, candidate_metrics)
    deltas = {
        key: candidate_metrics.get(key, 0.0) - baseline_metrics.get(key, 0.0)
        for key in metric_keys
    }
    per_query = compare_per_query(qrels, baseline_flat, candidate_flat)

    top1_before = baseline_stat.pop("top1_by_query")
    top1_after = candidate_stat.pop("top1_by_query")
    top1_total = len(set(top1_before) | set(top1_after))
    top1_changed = sum(1 for qid in sorted(set(top1_before) | set(top1_after)) if top1_before.get(qid) != top1_after.get(qid))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "persist_dir": display_path(args.persist_dir),
        "queries_path": display_path(args.queries),
        "qrels_path": display_path(args.qrels),
        "queries_sha256": sha256_file(args.queries),
        "qrels_sha256": sha256_file(args.qrels),
        "query_count": len(queries),
        "qrel_count": len(qrels),
        "judged_query_count": judged_query_count,
        "top_k": args.top_k,
        "embedding_model": args.embedding_model,
        "embedding_device": device,
        "embedding_elapsed_sec": embedding_elapsed,
        "baseline_collection": args.baseline,
        "candidate_collection": args.candidate,
        "collection_stats": {
            args.baseline: baseline_stat,
            args.candidate: candidate_stat,
        },
        "metrics": {
            args.baseline: baseline_metrics,
            args.candidate: candidate_metrics,
        },
        "metric_keys": metric_keys,
        "metric_deltas": deltas,
        "per_query_nDCG@10": per_query,
        "top1_comparison": {
            "total": top1_total,
            "changed": top1_changed,
        },
        "sample_run_records": {
            args.baseline: [asdict(record) for record in baseline_flat[:20]],
            args.candidate: [asdict(record) for record in candidate_flat[:20]],
        },
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)

    print(f"[WRITE] {args.out_json}")
    print(f"[WRITE] {args.out_md}")
    print("[METRICS]")
    for key in metric_keys:
        print(
            f"  {key}: {baseline_metrics.get(key, 0.0):.4f} -> "
            f"{candidate_metrics.get(key, 0.0):.4f} ({deltas[key]:+.4f})"
        )


if __name__ == "__main__":
    main()
