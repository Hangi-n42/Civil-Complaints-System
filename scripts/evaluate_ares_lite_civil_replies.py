"""Run ARES-lite evaluation over civil complaint QA outputs.

Examples:
    python scripts/evaluate_ares_lite_civil_replies.py \
        --input logs/evaluation/week11/sample_qa_outputs.jsonl \
        --output logs/evaluation/week11/ares_lite_report.json \
        --scores-output logs/evaluation/week11/ares_lite_scores.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.ares_lite import AresLiteCase, AresLiteEvaluator, build_ares_lite_report
from app.evaluation.ares_lite.report_builder import merge_ares_lite_summary_into_rubric_report


def main() -> None:
    parser = argparse.ArgumentParser(description="ARES-lite 민원 RAG 평가")
    parser.add_argument("--input", required=True, help="평가할 JSON 또는 JSONL 파일")
    parser.add_argument("--output", required=True, help="요약 리포트 JSON 출력 경로")
    parser.add_argument("--scores-output", help="case별 결과 JSONL 출력 경로")
    parser.add_argument("--cases", help="query/context 보강용 원본 case JSON/JSONL 파일")
    parser.add_argument("--rubric-report", help="ARES-lite summary를 병합할 기존 LLM-Rubric report JSON")
    parser.add_argument("--merged-rubric-output", help="ARES-lite summary가 추가된 rubric report 출력 경로")
    parser.add_argument("--max-cases", type=int, default=0, help="앞에서부터 N건만 평가")
    parser.add_argument("--print-summary", action="store_true", help="평가 요약을 stdout에 출력")
    args = parser.parse_args()

    input_path = _resolve(args.input)
    output_path = _resolve(args.output)
    scores_output_path = _resolve(args.scores_output) if args.scores_output else None
    rubric_report_path = _resolve(args.rubric_report) if args.rubric_report else None
    merged_rubric_output_path = (
        _resolve(args.merged_rubric_output)
        if args.merged_rubric_output
        else None
    )
    case_map = _load_case_map(_resolve(args.cases)) if args.cases else {}

    rows = _load_rows(input_path)
    if args.max_cases > 0:
        rows = rows[: args.max_cases]

    evaluator = AresLiteEvaluator()
    results = []
    for index, row in enumerate(rows):
        merged = _merge_case_context(row, case_map)
        case = AresLiteCase.from_mapping(merged, index=index)
        results.append(evaluator.evaluate(case))

    report = build_ares_lite_report(results)
    _write_json(output_path, report)
    if scores_output_path:
        _write_jsonl(scores_output_path, results)
    if rubric_report_path:
        if not merged_rubric_output_path:
            raise ValueError("--merged-rubric-output is required when --rubric-report is provided")
        rubric_report = _load_json_object(rubric_report_path)
        merged_report = merge_ares_lite_summary_into_rubric_report(rubric_report, report)
        _write_json(merged_rubric_output_path, merged_report)

    if args.print_summary:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


def _resolve(path: str | None) -> Path:
    if not path:
        raise ValueError("path is required")
    raw = Path(path)
    return raw if raw.is_absolute() else PROJECT_ROOT / raw


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return _read_jsonl(path)
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be an object, list, or JSONL")
    for key in ("results", "runs", "cases", "items", "data", "predictions"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def _load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON report must be an object")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            if not isinstance(item, dict):
                raise ValueError(f"JSONL row {line_no} must be an object")
            rows.append(item)
    return rows


def _load_case_map(path: Path) -> dict[str, dict[str, Any]]:
    case_map: dict[str, dict[str, Any]] = {}
    for item in _load_rows(path):
        case_id = str(
            item.get("case_id")
            or item.get("complaint_id")
            or item.get("source_id")
            or item.get("id")
            or ""
        ).strip()
        if case_id:
            case_map[case_id] = item
    return case_map


def _merge_case_context(row: dict[str, Any], case_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case_id = str(
        row.get("case_id")
        or row.get("complaint_id")
        or row.get("source_id")
        or row.get("id")
        or ""
    ).strip()
    base = dict(case_map.get(case_id, {}))
    base.update(row)

    if not base.get("query"):
        for key in ("complaint_text", "complaint", "question", "민원내용"):
            if base.get(key):
                base["query"] = base[key]
                break
    if not base.get("generated_answer"):
        for key in ("answer", "parsed_answer_repaired", "parsed_answer", "parsed_answer_strict", "response"):
            if base.get(key):
                base["generated_answer"] = base[key]
                break
    if not _has_contexts(base) and isinstance(base.get("citations"), list):
        citation_contexts = [
            {
                "context_id": citation.get("doc_id") or citation.get("case_id"),
                "content": citation.get("quote") or citation.get("snippet") or citation.get("text"),
                "source": citation.get("source"),
            }
            for citation in base["citations"]
            if isinstance(citation, dict)
        ]
        if citation_contexts:
            base["retrieved_contexts"] = citation_contexts
    return base


def _has_contexts(item: dict[str, Any]) -> bool:
    for key in ("retrieved_contexts", "contexts", "references", "search_results", "retrieval_context"):
        if isinstance(item.get(key), list) and item[key]:
            return True
    return False


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
