"""실제 DepartmentAssigner 예측을 query 신호로 주입해 부서 soft rerank A/B를 측정한다.

배경(#369): 기존 soft rerank 평가 하네스는 query 쪽 responsible_unit 을 항상 빈 값으로
넣어(`build_deterministic_structuring` -> responsible_unit=[]) BE1 부서 추정기의 개선이
검색 평가에 반영되지 않았다. 이 스크립트는 개선된 DepartmentAssigner 예측을 query 신호에
주입해 다음 3개를 비교한다.

- base        : soft rerank 미적용 (운영 기본)
- soft_nodept : 결정적 검색 신호만 (responsible_units=[] = 기존 하네스 동작)
- soft_dept   : 결정적 검색 신호 + 실제 DepartmentAssigner responsible_units

추가로, query 추정 부서가 정답 문서(rel>0)의 responsible_units 와 실제로 겹치는지
(=부서 신호가 순위에 기여할 여지가 있는지) 진단 수치를 함께 남긴다.

개인정보 보호: 쿼리 원문/스니펫은 산출물에 포함하지 않는다(집계·case_id 만).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from app.evaluation.datasets import sha256_file
from app.evaluation.metrics import evaluate_run
from app.retrieval.service import RetrievalService
from app.structuring.department_assigner import get_department_assigner
from scripts.eval_be1_metadata_overlay_soft_rerank import (
    METRIC_ORDER,
    build_query_signals,
    flatten_runs,
    load_qrels,
    load_queries,
    ordered_metric_keys,
    run_service_variant,
)

DEFAULT_QUERIES = PROJECT_ROOT / "data" / "evaluation" / "v3" / "queries.jsonl"
DEFAULT_QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
DEFAULT_OUT_JSON = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_query_signal_ab.json"
DEFAULT_OUT_MD = PROJECT_ROOT / "reports" / "retrieval" / "v3" / "responsible_unit_query_signal_ab.md"


def assign_query_departments(
    queries: list[dict[str, Any]], *, top_n_units: int
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """각 쿼리에 대해 DepartmentAssigner 예측 부서명 리스트를 만든다."""
    assigner = get_department_assigner()
    assigner.build_index(rebuild=False)
    preds: dict[str, list[str]] = {}
    confidences: dict[str, float] = {}
    started = time.perf_counter()
    for index, query in enumerate(queries, start=1):
        qid = query["query_id"]
        candidates = assigner.assign(query["query"], top_n_units=top_n_units)
        names = [c["name"] for c in candidates if c.get("name")]
        preds[qid] = names
        confidences[qid] = float(candidates[0]["confidence"]) if candidates else 0.0
        if index % 20 == 0:
            print(f"[assign] {index}/{len(queries)}")
    elapsed = time.perf_counter() - started
    covered = sum(1 for names in preds.values() if names)
    stat = {
        "elapsed_sec": round(elapsed, 1),
        "queries": len(queries),
        "queries_with_prediction": covered,
        "coverage_rate": round(covered / len(queries), 4) if queries else 0.0,
        "top_n_units": top_n_units,
    }
    return preds, stat


def augment_signals_with_departments(
    base_signals: dict[str, dict[str, Any]], dept_preds: dict[str, list[str]]
) -> dict[str, dict[str, Any]]:
    """결정적 신호 dict 복사본에 responsible_units 를 주입한다."""
    augmented: dict[str, dict[str, Any]] = {}
    for qid, signals in base_signals.items():
        new_signals = dict(signals)
        new_signals["responsible_units"] = list(dept_preds.get(qid, []))
        augmented[qid] = new_signals
    return augmented


def load_doc_departments(collection_name: str) -> dict[str, list[str]]:
    """case_id -> 문서쪽 responsible_units(리스트). 정답 문서 부서 매칭 진단용."""
    col = chromadb.PersistentClient(path=str(PROJECT_ROOT / "data" / "chroma_db")).get_collection(
        collection_name
    )
    metas = col.get(include=["metadatas"])["metadatas"]
    out: dict[str, list[str]] = {}
    for meta in metas:
        case_id = str(meta.get("case_id") or "").strip()
        if not case_id:
            continue
        raw = meta.get("responsible_units") or ""
        units = [u.strip() for u in str(raw).split("|") if u.strip()]
        out.setdefault(case_id, units)
    return out


def diagnose_query_doc_match(
    queries: list[dict[str, Any]],
    qrels: list[Any],
    dept_preds: dict[str, list[str]],
    doc_depts: dict[str, list[str]],
) -> dict[str, Any]:
    """query 추정 부서가 정답 문서(rel>0)의 부서와 겹치는 비율."""
    rel_by_qid: dict[str, list[str]] = {}
    for row in qrels:
        if row.relevance > 0:
            rel_by_qid.setdefault(row.qid, []).append(row.docid)

    judged = 0
    top1_match = 0
    any_match = 0
    rel_doc_total = 0
    rel_doc_dept_present = 0
    for query in queries:
        qid = query["query_id"]
        rel_docs = rel_by_qid.get(qid, [])
        if not rel_docs:
            continue
        judged += 1
        pred = dept_preds.get(qid, [])
        pred_set = set(pred)
        pred_top1 = pred[0] if pred else None
        rel_dept_union: set[str] = set()
        for docid in rel_docs:
            units = doc_depts.get(docid, [])
            rel_doc_total += 1
            if units:
                rel_doc_dept_present += 1
            rel_dept_union |= set(units)
        if pred_top1 and pred_top1 in rel_dept_union:
            top1_match += 1
        if pred_set & rel_dept_union:
            any_match += 1
    return {
        "judged_queries": judged,
        "query_top1_dept_in_relevant_docs": top1_match,
        "query_top1_match_rate": round(top1_match / judged, 4) if judged else 0.0,
        "query_anytop_dept_in_relevant_docs": any_match,
        "query_anytop_match_rate": round(any_match / judged, 4) if judged else 0.0,
        "relevant_docs_total": rel_doc_total,
        "relevant_docs_with_dept_tag": rel_doc_dept_present,
    }


def _fmt(v: float) -> str:
    return f"{v:.4f}"


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    diag = payload["query_doc_dept_diagnosis"]
    a = payload["assign_stat"]
    lines = [
        "# 부서 신호(query-side) soft rerank A/B",
        "",
        "## 배경",
        "",
        "기존 soft rerank 평가는 query 쪽 `responsible_unit` 을 항상 빈 값으로 넣어 BE1 부서 추정기",
        "개선이 검색 평가에 반영되지 않았다(#369). 이 평가는 실제 DepartmentAssigner 예측을",
        "query 신호로 주입해 부서 soft rerank 의 실제 효과를 측정한다.",
        "",
        "## 설정",
        "",
        f"- 컬렉션: `{payload['collection']}`",
        f"- 쿼리: {payload['query_count']}건 / qrels 보유: {payload['judged_query_count']}건",
        f"- qrels: `{payload['qrels_path']}` ({payload['evaluated_qrel_count']}개 라벨, {payload['qrels_sha256']})",
        f"- Top-K: {payload['top_k']}",
        f"- 부서 추정 커버리지: {a['queries_with_prediction']}/{a['queries']}건 "
        f"({a['coverage_rate']*100:.1f}%), top_n_units={a['top_n_units']}, {a['elapsed_sec']}s",
        f"- 문서쪽 부서 태그 출처: `{payload['doc_responsible_units_source']}`",
        "",
        "## 부서 신호가 도움될 여지 진단 (query 추정 부서 ∩ 정답문서 부서)",
        "",
        f"- 평가 쿼리: {diag['judged_queries']}건",
        f"- query top-1 부서가 정답 문서 부서에 존재: {diag['query_top1_dept_in_relevant_docs']}건 "
        f"({diag['query_top1_match_rate']*100:.1f}%)",
        f"- query top-N(≤3) 부서 중 하나라도 정답 문서 부서에 존재: "
        f"{diag['query_anytop_dept_in_relevant_docs']}건 ({diag['query_anytop_match_rate']*100:.1f}%)",
        f"- 정답 문서 부서 태그 보유: {diag['relevant_docs_with_dept_tag']}/{diag['relevant_docs_total']}",
        "",
    ]
    for strategy, result in payload["strategies"].items():
        m = result["metrics"]
        keys = result["metric_keys"]
        lines.extend(
            [
                f"## {strategy.upper()} 검색",
                "",
                "| 지표 | base | soft_nodept | soft_dept | Δ(dept−nodept) | Δ(dept−base) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for key in keys:
            base_v = m["base"].get(key, 0.0)
            nod_v = m["soft_nodept"].get(key, 0.0)
            dep_v = m["soft_dept"].get(key, 0.0)
            lines.append(
                f"| {key} | {_fmt(base_v)} | {_fmt(nod_v)} | {_fmt(dep_v)} | "
                f"{dep_v - nod_v:+.4f} | {dep_v - base_v:+.4f} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 판단",
            "",
            "- 부서 신호는 hard filter 가 아니라 약한 점수 boost(soft rerank)로만 사용한다.",
            "- 쿼리 원문/스니펫은 산출물에 포함하지 않았다(집계·case_id 만).",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--top-n-units", type=int, default=3)
    parser.add_argument("--strategies", nargs="+", default=["dense", "hybrid"], choices=["dense", "hybrid"])
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    queries = load_queries(args.queries, limit=max(0, args.limit))
    qrels = load_qrels(args.qrels)
    query_ids = {q["query_id"] for q in queries}
    eval_qrels = [row for row in qrels if row.qid in query_ids]
    judged_query_count = len({row.qid for row in eval_qrels})

    det_signals = build_query_signals(queries)
    dept_preds, assign_stat = assign_query_departments(queries, top_n_units=args.top_n_units)
    dept_signals = augment_signals_with_departments(det_signals, dept_preds)

    doc_depts = load_doc_departments(args.collection)
    diagnosis = diagnose_query_doc_match(queries, qrels, dept_preds, doc_depts)

    service = RetrievalService()
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": args.collection,
        "queries_path": args.queries.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "qrels_path": args.qrels.resolve().relative_to(PROJECT_ROOT).as_posix(),
        "queries_sha256": sha256_file(args.queries),
        "qrels_sha256": sha256_file(args.qrels),
        "query_count": len(queries),
        "judged_query_count": judged_query_count,
        "evaluated_qrel_count": len(eval_qrels),
        "top_k": args.top_k,
        "doc_responsible_units_source": "be1_structured",
        "assign_stat": assign_stat,
        "query_doc_dept_diagnosis": diagnosis,
        "strategies": {},
    }

    for strategy in args.strategies:
        variants: dict[str, Any] = {}
        runs: dict[str, Any] = {}
        # base: soft rerank off
        runs["base"], _ = await run_service_variant(
            service=service, queries=queries, query_signals=dept_signals,
            collection=args.collection, strategy=strategy, top_k=args.top_k,
            use_soft_rerank=False,
        )
        # soft_nodept: 결정적 신호만 (responsible_units=[])
        runs["soft_nodept"], _ = await run_service_variant(
            service=service, queries=queries, query_signals=det_signals,
            collection=args.collection, strategy=strategy, top_k=args.top_k,
            use_soft_rerank=True,
        )
        # soft_dept: 결정적 신호 + 부서 예측
        runs["soft_dept"], _ = await run_service_variant(
            service=service, queries=queries, query_signals=dept_signals,
            collection=args.collection, strategy=strategy, top_k=args.top_k,
            use_soft_rerank=True,
        )
        metrics = {name: evaluate_run(eval_qrels, flatten_runs(run)) for name, run in runs.items()}
        metric_keys = ordered_metric_keys(*metrics.values())
        variants["metric_keys"] = metric_keys
        variants["metrics"] = metrics
        payload["strategies"][strategy] = variants

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(payload, args.out_md)
    print(f"[WRITE] {args.out_json}")
    print(f"[WRITE] {args.out_md}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
