"""BE1 query_signals -> BE2 search -> optional QA E2E 검증 스크립트.

사용 예:
  python scripts/e2e_be1_query_signals_search_qa.py --limit 5 --structuring-mode deterministic
  python scripts/e2e_be1_query_signals_search_qa.py --limit 5 --structuring-mode actual --grounding-filter

기본 실행은 답변 생성을 건너뛴다. QA는 Ollama 생성 모델이 필요하므로
로컬 또는 Tailscale 데스크톱 런타임이 준비된 경우에만 --run-generation을 사용한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.generation.context_mapper import map_retrieval_to_qa_context
from app.retrieval.service import RetrievalService
from app.structuring.enrichment import build_key_terms, normalize_entity_texts
from app.structuring.legal_dictionary import get_legal_ref_matcher
from app.structuring.preprocessing import load_processed, to_structuring_record

SIGNAL_FIELDS = [
    "entity_texts",
    "legal_ref_names",
    "legal_ref_ids",
    "key_terms",
    "responsible_units",
]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _safe_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _clean_values(values: Any) -> list[str]:
    if values is None:
        raw_values: list[Any] = []
    elif isinstance(values, str):
        raw_values = [item for item in values.split("|") if item]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = [values]

    out: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = _clean_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _extract_field_values(items: Any, field: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return _clean_values([item.get(field) for item in items if isinstance(item, dict)])


def normalize_generation_metadata(value: Any) -> dict[str, Any]:
    """BE3 generation_metadata를 E2E 리포트용 기본 형태로 정규화한다."""

    metadata = value if isinstance(value, dict) else {}
    return {
        "fallback_used": bool(metadata.get("fallback_used", False)),
        "parse_retry_count": _safe_non_negative_int(metadata.get("parse_retry_count")),
        "generation_mode": _clean_text(metadata.get("generation_mode")) or "default",
        "legal_grounding_status": _clean_text(metadata.get("legal_grounding_status")) or "not_requested",
        "legal_grounding_error": _clean_text(metadata.get("legal_grounding_error")),
    }


def build_generation_warnings(
    *,
    answer_chars: int,
    generation_metadata: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if answer_chars <= 0:
        warnings.append("empty_answer")
    if generation_metadata.get("fallback_used"):
        warnings.append("fallback_used")
    return warnings


def extract_query_signals(structured: dict[str, Any]) -> dict[str, Any]:
    """BE1 구조화 출력에서 /search query_signals payload를 만든다."""

    urgency = structured.get("urgency")
    urgency_level = urgency.get("level") if isinstance(urgency, dict) else urgency
    responsible_unit_sources = _extract_field_values(structured.get("responsible_unit"), "source")
    return {
        "entity_texts": _extract_field_values(structured.get("entity_texts"), "text"),
        "legal_ref_names": _extract_field_values(structured.get("legal_refs"), "name"),
        "legal_ref_ids": _extract_field_values(structured.get("legal_refs"), "law_id"),
        "key_terms": _clean_values(structured.get("key_terms")),
        "responsible_units": _extract_field_values(structured.get("responsible_unit"), "name"),
        "responsible_units_source": responsible_unit_sources[0] if responsible_unit_sources else "",
        "urgency_level": _clean_text(urgency_level),
    }


def build_deterministic_structuring(record: dict[str, Any]) -> dict[str, Any]:
    """LLM 4요소 추출 없이 BE1 검색 신호만 만든다."""

    text = _clean_text(record.get("text"))
    entity_texts = normalize_entity_texts([], text)
    legal_refs = get_legal_ref_matcher().match(text)
    key_terms = build_key_terms(text, entity_texts, legal_refs)
    return {
        "case_id": record.get("case_id"),
        "raw_text": text,
        "category": record.get("category"),
        "region": record.get("region"),
        "entity_texts": entity_texts,
        "legal_refs": legal_refs,
        "key_terms": key_terms,
        "responsible_unit": [],
        "structured_by": "deterministic_search_signal_smoke",
    }


def signal_counts(signals: dict[str, list[str]]) -> dict[str, int]:
    return {field: len(signals.get(field) or []) for field in SIGNAL_FIELDS}


def values_from_metadata(metadata: dict[str, Any], field: str) -> list[str]:
    return _clean_values(metadata.get(field))


def overlap_by_field(
    query_signals: dict[str, list[str]],
    metadata: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    overlaps: dict[str, dict[str, Any]] = {}
    for field in SIGNAL_FIELDS:
        left = {item.casefold(): item for item in query_signals.get(field, [])}
        right = {item.casefold(): item for item in values_from_metadata(metadata, field)}
        matched = [left[key] for key in left.keys() & right.keys()]
        overlaps[field] = {"count": len(matched), "values": matched}
    return overlaps


def compact_result(
    item: dict[str, Any],
    *,
    query_signals: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    out = {
        "rank": int(item.get("rank") or 0),
        "case_id": _clean_text(item.get("case_id")),
        "chunk_id": _clean_text(item.get("chunk_id")),
        "score": float(item.get("score", 0.0) or 0.0),
        "title": _clean_text(item.get("title")),
        "snippet_preview": _clean_text(item.get("snippet"))[:180],
    }
    if query_signals is not None:
        out["metadata_overlap"] = overlap_by_field(query_signals, metadata)
        out["metadata_overlap_total"] = sum(
            field["count"] for field in out["metadata_overlap"].values()
        )
    return out


def result_key(item: dict[str, Any]) -> str:
    return _clean_text(item.get("chunk_id")) or _clean_text(item.get("case_id"))


def compare_rankings(
    baseline: list[dict[str, Any]],
    with_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    base_rank = {result_key(item): idx for idx, item in enumerate(baseline, start=1) if result_key(item)}
    signal_rank = {
        result_key(item): idx for idx, item in enumerate(with_signals, start=1) if result_key(item)
    }

    common_keys = sorted(base_rank.keys() & signal_rank.keys(), key=lambda key: signal_rank[key])
    rank_changes = [
        {
            "key": key,
            "baseline_rank": base_rank[key],
            "with_signals_rank": signal_rank[key],
            "rank_delta": base_rank[key] - signal_rank[key],
        }
        for key in common_keys
        if base_rank[key] != signal_rank[key]
    ]

    baseline_top1 = result_key(baseline[0]) if baseline else ""
    signal_top1 = result_key(with_signals[0]) if with_signals else ""
    return {
        "baseline_empty": not baseline,
        "with_signals_empty": not with_signals,
        "top1_changed": bool(baseline_top1 and signal_top1 and baseline_top1 != signal_top1),
        "baseline_top1": baseline_top1,
        "with_signals_top1": signal_top1,
        "new_in_with_signals_top_k": sorted(signal_rank.keys() - base_rank.keys()),
        "dropped_from_baseline_top_k": sorted(base_rank.keys() - signal_rank.keys()),
        "rank_changes": rank_changes,
        "moved_up_count": sum(1 for item in rank_changes if item["rank_delta"] > 0),
        "moved_down_count": sum(1 for item in rank_changes if item["rank_delta"] < 0),
    }


def select_records(
    processed_path: Path,
    *,
    limit: int,
    offset: int,
    case_ids: list[str],
) -> list[dict[str, Any]]:
    records = load_processed(str(processed_path))
    if case_ids:
        wanted = set(case_ids)
        return [rec for rec in records if str(rec.get("source_id") or "") in wanted][:limit]
    return records[offset : offset + limit]


async def build_structured_output(
    record: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    structuring_record = to_structuring_record(record)
    if mode == "deterministic":
        return build_deterministic_structuring(structuring_record)

    from app.structuring.service import get_structuring_service

    return await get_structuring_service().structure(structuring_record)


async def maybe_generate_answer(
    *,
    query: str,
    search_results: list[dict[str, Any]],
    top_k: int,
    query_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.generation.service import get_generation_service

    context, context_trace = map_retrieval_to_qa_context(
        retrieval_results=search_results,
        top_k=top_k,
        policy=None,
    )
    if not context:
        return {"status": "skipped", "reason": "QA 컨텍스트를 구성할 검색 결과가 없습니다."}

    result = await get_generation_service().generate_qa(
        query=query,
        context=context,
        routing_trace={
            "topic_type": "general",
            "complexity_level": "medium",
            "complexity_score": 0.5,
        },
        query_signals=query_signals,
    )
    answer = _clean_text(result.get("answer"))
    generation_metadata = normalize_generation_metadata(result.get("generation_metadata"))
    warnings = build_generation_warnings(
        answer_chars=len(answer),
        generation_metadata=generation_metadata,
    )
    return {
        "status": "warning" if warnings else "ok",
        "warnings": warnings,
        "answer_chars": len(answer),
        "answer_preview": answer[:240],
        "citation_count": len(result.get("citations") or []),
        "model": result.get("model"),
        "generation_metadata": generation_metadata,
        "context_trace": context_trace,
    }


async def run_one(
    service: RetrievalService,
    record: dict[str, Any],
    *,
    structuring_mode: str,
    top_k: int,
    collection: str,
    strategy: str,
    grounding_filter: bool,
    run_generation: bool,
) -> dict[str, Any]:
    case_id = _clean_text(record.get("source_id"))
    started = perf_counter()
    structured = await build_structured_output(record, mode=structuring_mode)
    query = _clean_text(structured.get("raw_text")) or _clean_text(to_structuring_record(record).get("text"))
    query_signals = extract_query_signals(structured)

    baseline = await service.search(
        query=query,
        top_k=top_k,
        collection_name=collection,
        strategy=strategy,
        grounding_filter=False,
        query_signals=None,
    )
    with_signals = await service.search(
        query=query,
        top_k=top_k,
        collection_name=collection,
        strategy=strategy,
        grounding_filter=False,
        query_signals=query_signals,
    )

    grounding_results: list[dict[str, Any]] = []
    grounding_error = ""
    if grounding_filter:
        try:
            grounding_results = await service.search(
                query=query,
                top_k=top_k,
                collection_name=collection,
                strategy=strategy,
                grounding_filter=True,
                query_signals=query_signals,
            )
        except Exception as exc:  # noqa: BLE001
            grounding_error = str(exc)

    generation: dict[str, Any] = {"status": "skipped", "reason": "--run-generation 미지정"}
    if run_generation:
        try:
            generation = await maybe_generate_answer(
                query=query,
                search_results=grounding_results or with_signals,
                top_k=top_k,
                query_signals=query_signals,
            )
        except Exception as exc:  # noqa: BLE001
            generation = {"status": "error", "reason": str(exc)}

    comparison = compare_rankings(baseline, with_signals)
    return {
        "case_id": case_id,
        "category": _clean_text(record.get("consulting_category")),
        "source": _clean_text(record.get("source")),
        "structuring_mode": structuring_mode,
        "structured_by": structured.get("structured_by"),
        "query_chars": len(query),
        "query_preview": query[:240],
        "query_signals": query_signals,
        "signal_counts": signal_counts(query_signals),
        "baseline_top": [compact_result(item) for item in baseline],
        "with_signals_top": [compact_result(item, query_signals=query_signals) for item in with_signals],
        "grounding_top": [
            compact_result(item, query_signals=query_signals) for item in grounding_results
        ],
        "grounding_error": grounding_error,
        "generation": generation,
        "comparison": comparison,
        "elapsed_ms": int((perf_counter() - started) * 1000),
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in rows if row.get("status") == "ok"]
    failures = [row for row in rows if row.get("status") != "ok"]
    coverage = {
        field: sum(1 for row in successful if row.get("signal_counts", {}).get(field, 0) > 0)
        for field in SIGNAL_FIELDS
    }
    top1_changed = sum(1 for row in successful if row.get("comparison", {}).get("top1_changed"))
    moved_up = sum(int(row.get("comparison", {}).get("moved_up_count") or 0) for row in successful)
    with_overlap_top1 = sum(
        1
        for row in successful
        if row.get("with_signals_top")
        and int(row["with_signals_top"][0].get("metadata_overlap_total") or 0) > 0
    )
    grounding_runs = [row for row in successful if row.get("grounding_top") or row.get("grounding_error")]
    generation_rows = [
        row.get("generation", {})
        for row in successful
        if row.get("generation", {}).get("status") != "skipped"
    ]
    generation_mode_counts: dict[str, int] = {}
    legal_grounding_status_counts: dict[str, int] = {}
    for generation in generation_rows:
        metadata = normalize_generation_metadata(generation.get("generation_metadata"))
        mode = str(metadata.get("generation_mode") or "default")
        generation_mode_counts[mode] = generation_mode_counts.get(mode, 0) + 1
        legal_status = str(metadata.get("legal_grounding_status") or "not_requested")
        legal_grounding_status_counts[legal_status] = (
            legal_grounding_status_counts.get(legal_status, 0) + 1
        )

    return {
        "records": len(rows),
        "successful_records": len(successful),
        "failed_records": len(failures),
        "signal_coverage": coverage,
        "top1_changed_count": top1_changed,
        "moved_up_candidate_count": moved_up,
        "with_signals_top1_has_metadata_overlap_count": with_overlap_top1,
        "baseline_empty_count": sum(
            1 for row in successful if row.get("comparison", {}).get("baseline_empty")
        ),
        "with_signals_empty_count": sum(
            1 for row in successful if row.get("comparison", {}).get("with_signals_empty")
        ),
        "grounding_run_count": len(grounding_runs),
        "grounding_error_count": sum(1 for row in successful if row.get("grounding_error")),
        "generation_run_count": len(generation_rows),
        "generation_ok_count": sum(1 for item in generation_rows if item.get("status") == "ok"),
        "generation_warning_count": sum(
            1 for item in generation_rows if item.get("status") == "warning"
        ),
        "generation_error_count": sum(1 for item in generation_rows if item.get("status") == "error"),
        "generation_empty_answer_count": sum(
            1
            for item in generation_rows
            if item.get("status") in {"ok", "warning"}
            and _safe_non_negative_int(item.get("answer_chars")) <= 0
        ),
        "generation_fallback_count": sum(
            1
            for item in generation_rows
            if normalize_generation_metadata(item.get("generation_metadata")).get("fallback_used")
        ),
        "generation_max_parse_retry_count": max(
            [
                _safe_non_negative_int(
                    normalize_generation_metadata(item.get("generation_metadata")).get(
                        "parse_retry_count"
                    )
                )
                for item in generation_rows
            ],
            default=0,
        ),
        "generation_mode_counts": generation_mode_counts,
        "generation_legal_grounding_status_counts": legal_grounding_status_counts,
    }


def render_markdown(report: dict[str, Any]) -> str:
    args = report["args"]
    summary = report["summary"]
    rows = [row for row in report["records"] if row.get("status") == "ok"]

    lines = [
        "# BE1 query_signals 검색 E2E 검증 요약",
        "",
        "## 실행 조건",
        "",
        f"- 생성 시각: {report['generated_at']}",
        f"- 구조화 모드: `{args['structuring_mode']}`",
        f"- 샘플 수: {summary['records']}건",
        f"- 검색 전략: `{args['strategy']}`",
        f"- grounding filter 실행: `{args['grounding_filter']}`",
        f"- 답변 생성 실행: `{args['run_generation']}`",
        "",
        "## 핵심 결과",
        "",
        f"- 정상 처리: {summary['successful_records']}건",
        f"- 실패: {summary['failed_records']}건",
        f"- top1 변경: {summary['top1_changed_count']}건",
        f"- 기존 top-k 안에서 위로 올라간 후보 수: {summary['moved_up_candidate_count']}개",
        f"- metadata overlap이 있는 후보가 top1인 건수: {summary['with_signals_top1_has_metadata_overlap_count']}건",
        f"- baseline 빈 결과: {summary['baseline_empty_count']}건",
        f"- query_signals 적용 후 빈 결과: {summary['with_signals_empty_count']}건",
        f"- grounding filter 오류: {summary['grounding_error_count']}건",
        "",
        "## 신호 생성 커버리지",
        "",
        "| 필드 | 값이 나온 샘플 수 |",
        "| --- | ---: |",
    ]
    for field in SIGNAL_FIELDS:
        lines.append(f"| `{field}` | {summary['signal_coverage'].get(field, 0)} |")

    if args["structuring_mode"] == "deterministic":
        lines.extend(
            [
                "",
                "## 해석 주의",
                "",
                "- 이 실행은 LLM 4요소 추출을 건너뛴 smoke test입니다.",
                "- 실제 BE1 구조화까지 검증하려면 `--structuring-mode actual`로 다시 실행해야 합니다.",
            ]
        )

    if args["run_generation"]:
        mode_counts = summary.get("generation_mode_counts", {})
        mode_text = ", ".join(
            f"{mode}: {count}" for mode, count in sorted(mode_counts.items())
        ) or "-"
        legal_status_counts = summary.get("generation_legal_grounding_status_counts", {})
        legal_status_text = ", ".join(
            f"{status}: {count}" for status, count in sorted(legal_status_counts.items())
        ) or "-"
        lines.extend(
            [
                "",
                "## 답변 생성 관측",
                "",
                f"- 답변 생성 실행 건수: {summary.get('generation_run_count', 0)}건",
                f"- 정상 생성: {summary.get('generation_ok_count', 0)}건",
                f"- 생성 경고: {summary.get('generation_warning_count', 0)}건",
                f"- 생성 오류: {summary.get('generation_error_count', 0)}건",
                f"- 빈 답변: {summary.get('generation_empty_answer_count', 0)}건",
                f"- fallback 사용: {summary.get('generation_fallback_count', 0)}건",
                f"- 최대 JSON 파싱 재시도: {summary.get('generation_max_parse_retry_count', 0)}회",
                f"- generation mode 분포: {mode_text}",
                f"- 법령 grounding 상태 분포: {legal_status_text}",
                "",
                "| case_id | 상태 | mode | 법령 grounding | fallback | retry | 답변 글자 수 | 경고 |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in rows[:30]:
            generation = row.get("generation", {})
            metadata = normalize_generation_metadata(generation.get("generation_metadata"))
            warnings = ", ".join(generation.get("warnings") or [])
            lines.append(
                "| {case_id} | {status} | {mode} | {legal_status} | {fallback} | {retry} | {answer_chars} | {warnings} |".format(
                    case_id=row.get("case_id", ""),
                    status=generation.get("status", ""),
                    mode=metadata.get("generation_mode", "default"),
                    legal_status=metadata.get("legal_grounding_status", "not_requested"),
                    fallback="예" if metadata.get("fallback_used") else "아니오",
                    retry=metadata.get("parse_retry_count", 0),
                    answer_chars=_safe_non_negative_int(generation.get("answer_chars")),
                    warnings=warnings or "-",
                )
            )

    lines.extend(
        [
            "",
            "## 샘플별 변화",
            "",
            "| case_id | 신호 수 | baseline top1 | query_signals top1 | top1 변경 |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for row in rows[:30]:
        signal_total = sum(int(v) for v in row.get("signal_counts", {}).values())
        comparison = row.get("comparison", {})
        lines.append(
            "| {case_id} | {signal_total} | {base} | {sig} | {changed} |".format(
                case_id=row.get("case_id", ""),
                signal_total=signal_total,
                base=comparison.get("baseline_top1", ""),
                sig=comparison.get("with_signals_top1", ""),
                changed="예" if comparison.get("top1_changed") else "아니오",
            )
        )

    failures = [row for row in report["records"] if row.get("status") != "ok"]
    if failures:
        lines.extend(["", "## 실패 항목", "", "| case_id | 오류 |", "| --- | --- |"])
        for row in failures[:30]:
            lines.append(f"| {row.get('case_id', '')} | {_clean_text(row.get('error'))[:240]} |")

    lines.append("")
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    service = RetrievalService()
    records = select_records(
        Path(args.processed),
        limit=args.limit,
        offset=args.offset,
        case_ids=args.case_id,
    )
    outputs: list[dict[str, Any]] = []
    for record in records:
        case_id = _clean_text(record.get("source_id"))
        try:
            row = await run_one(
                service,
                record,
                structuring_mode=args.structuring_mode,
                top_k=args.top_k,
                collection=args.collection,
                strategy=args.strategy,
                grounding_filter=args.grounding_filter,
                run_generation=args.run_generation,
            )
            row["status"] = "ok"
            outputs.append(row)
            print(
                f"ok case_id={case_id} top1_changed={row['comparison']['top1_changed']} "
                f"signals={row['signal_counts']}"
            )
        except Exception as exc:  # noqa: BLE001
            outputs.append({"status": "error", "case_id": case_id, "error": str(exc)})
            print(f"error case_id={case_id} reason={exc}")
            if args.fail_fast:
                raise

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "args": {
            "processed": args.processed,
            "limit": args.limit,
            "offset": args.offset,
            "case_id": args.case_id,
            "top_k": args.top_k,
            "collection": args.collection,
            "strategy": args.strategy,
            "structuring_mode": args.structuring_mode,
            "grounding_filter": args.grounding_filter,
            "run_generation": args.run_generation,
        },
        "summary": build_summary(outputs),
        "records": outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="BE1 query_signals가 BE2 검색/답변 초안 검색에 연결되는지 검증합니다."
    )
    parser.add_argument("--processed", default=str(ROOT / "data/processed/processed_consulting_data.json"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--strategy", default="hybrid")
    parser.add_argument(
        "--structuring-mode",
        choices=["actual", "deterministic"],
        default="actual",
        help="actual은 BE1 StructuringService 전체 실행, deterministic은 검색 신호 함수만 실행",
    )
    parser.add_argument("--grounding-filter", action="store_true")
    parser.add_argument("--run-generation", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--out-json",
        default=str(ROOT / "reports/retrieval/v3/be1_query_signals_e2e.json"),
    )
    parser.add_argument(
        "--out-md",
        default=str(ROOT / "reports/retrieval/v3/be1_query_signals_e2e_summary.md"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run(args))
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
