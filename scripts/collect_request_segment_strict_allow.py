"""request_segments strict allow 후보 수집/검수 산출물 생성 스크립트.

운영 로직은 변경하지 않고, 현재 조건 B + pre-gate + v2_strict gate를 그대로 호출해
strict allow 후보를 목표 수까지 모은다. LLM 응답은 JSONL로 즉시 저장해 중단 후 재개할 수 있다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output
from app.retrieval.analyzers.request_segment_hybrid import (
    LLMValidationResult,
    assess_fallback_need,
    assess_llm_pre_gate,
    build_block_prompt,
    build_source_blocks,
    evaluate_assist_limited_v2_strict_gate,
    parse_llm_json_response,
    validate_block_llm_segments,
)
from app.structuring.preprocessing import civil_text, process_raw_record


JUDGMENTS = {"pass", "partial", "fail", "unsure"}
ERROR_TYPES = {
    "none",
    "over_split",
    "under_split",
    "unsupported_segment",
    "too_abstract",
    "weak_actionability",
    "dialogue_confusion",
    "legal_context_ambiguous",
    "evidence_insufficient",
    "title_summary_confusion",
    "condition_or_method_split",
    "other",
}
RECOMMENDATIONS = {"allow", "shadow_only", "review_required", "reject"}


def main() -> None:
    args = _parse_args()
    candidates = _build_candidates(args.input_dir, seed=args.seed)
    processed = _load_processed_calls(args.raw_responses_jsonl)
    allow_rows = [row for row in processed.values() if row.get("llm_assist_gate") == "allow_assist"]
    called_count = len(processed)

    for candidate in candidates:
        if len(allow_rows) >= args.target_allow:
            break
        if args.max_llm_calls and called_count >= args.max_llm_calls:
            break
        if candidate["candidate_key"] in processed:
            continue

        row = _evaluate_candidate(candidate, args)
        _append_jsonl(args.raw_responses_jsonl, row)
        processed[row["candidate_key"]] = row
        called_count += 1
        if row.get("llm_assist_gate") == "allow_assist":
            allow_rows.append(row)

        if called_count % args.checkpoint_every == 0 or len(allow_rows) % 25 == 0:
            _write_outputs(args, candidates, list(processed.values()), allow_rows)

    _write_outputs(args, candidates, list(processed.values()), allow_rows)
    summary = _summarize(candidates, list(processed.values()), allow_rows, args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw_data"))
    parser.add_argument("--seed", type=int, default=20260621)
    parser.add_argument("--target-allow", type=int, default=500)
    parser.add_argument("--max-llm-calls", type=int, default=0)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--num-predict", type=int, default=256)
    parser.add_argument("--candidates-json", type=Path, default=Path("reports/request_segment_strict_allow_500_candidates.json"))
    parser.add_argument("--raw-responses-jsonl", type=Path, default=Path("reports/request_segment_strict_allow_500_raw_responses.jsonl"))
    parser.add_argument("--review-jsonl", type=Path, default=Path("reports/request_segment_strict_allow_500_review.jsonl"))
    parser.add_argument("--collection-report-md", type=Path, default=Path("reports/request_segment_strict_allow_500_collection_report.md"))
    return parser.parse_args()


def _iter_raw_records(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal = 0
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            ordinal += 1
            rows.append({"__file": path.name, "__ordinal": ordinal, **item})
    return rows


def _build_candidates(input_dir: Path, *, seed: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for raw in _iter_raw_records(input_dir):
        processed = process_raw_record(raw)
        source_text = civil_text(processed)
        if not source_text:
            continue
        rule_output = build_analyzer_output(
            text=source_text,
            topic_type=processed.get("consulting_category") or "general",
            title=processed.get("title"),
            question=processed.get("client_question"),
        )
        decision = assess_fallback_need(source_text, rule_output)
        if not decision.should_call:
            continue
        pre_gate = assess_llm_pre_gate(
            policy="v2_strict",
            fallback_reasons=decision.reasons,
            source_text=source_text,
            rule_output=rule_output,
            prompt_style="block",
        )
        if pre_gate.decision != "allow_call":
            continue
        source_id = str(processed.get("source_id") or raw.get("__ordinal") or "")
        candidate_key = _candidate_key(raw.get("__file"), source_id, source_text)
        candidates.append(
            {
                "candidate_key": candidate_key,
                "source_id": source_id,
                "source_file": raw.get("__file"),
                "title": processed.get("title") or "",
                "question": processed.get("client_question") or "",
                "source_text": source_text,
                "source_excerpt": source_text[:900],
                "fallback_reasons": decision.reasons,
                "pre_gate": pre_gate.decision,
                "pre_gate_reason": pre_gate.reason,
                "pre_gate_risk_tags": pre_gate.risk_tags,
                "rule_segments": rule_output.get("request_segments") or [],
                "rule_trace": rule_output.get("complexity_trace") or {},
                "topic_type": processed.get("consulting_category") or "general",
            }
        )
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates


def _candidate_key(source_file: str | None, source_id: str, source_text: str) -> str:
    digest = hashlib.sha1(str(source_text or "").encode("utf-8")).hexdigest()[:12]
    return f"{source_file or 'raw'}::{source_id}::{digest}"


def _load_processed_calls(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        key = row.get("candidate_key")
        if key:
            rows[str(key)] = row
    return rows


def _evaluate_candidate(candidate: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    rule_output = {"request_segments": candidate["rule_segments"], "complexity_trace": candidate["rule_trace"]}
    source_blocks = build_source_blocks(candidate["source_text"], max_blocks=30)
    prompt = build_block_prompt(source_blocks, rule_output)
    started = time.perf_counter()
    raw_response = _call_ollama(prompt, args)
    latency = round(time.perf_counter() - started, 3)
    row = {
        **candidate,
        "source_block_count": len(source_blocks),
        "latency_sec": latency,
        "raw_response": raw_response,
        "accepted": False,
        "reject_reason": None,
        "hallucination_suspected": False,
        "llm_decision": None,
        "llm_segments": [],
        "evidence_ids": [],
        "restored_evidence_texts": [],
        "llm_assist_gate": "not_evaluated",
        "llm_assist_gate_reason": None,
        "llm_assist_gate_risk_tags": [],
        "llm_assist_gate_evidence_count": 0,
    }
    if raw_response is None:
        row["reject_reason"] = "llm_call_failed"
        return row

    validation = validate_block_llm_segments(
        raw_response,
        source_blocks=source_blocks,
        rule_output=rule_output,
        fallback_reasons=candidate["fallback_reasons"],
    )
    _apply_validation_and_gate(row, validation, candidate, raw_response, source_blocks)
    return row


def _apply_validation_and_gate(
    row: dict[str, Any],
    validation: LLMValidationResult,
    candidate: dict[str, Any],
    raw_response: str,
    source_blocks: list[Any],
) -> None:
    rule_output = {"request_segments": candidate["rule_segments"], "complexity_trace": candidate["rule_trace"]}
    gate = evaluate_assist_limited_v2_strict_gate(
        validation=validation,
        rule_output=rule_output,
        fallback_reasons=candidate["fallback_reasons"],
        source_text=candidate["source_text"],
        prompt_style="block",
        raw_response=raw_response,
    )
    evidence_ids = _extract_evidence_ids(raw_response)
    block_map = {block.id: block.text for block in source_blocks}
    row.update(
        {
            "accepted": validation.accepted,
            "reject_reason": validation.reject_reason,
            "hallucination_suspected": validation.hallucination_suspected,
            "llm_decision": validation.decision,
            "llm_segments": validation.segments,
            "evidence_ids": evidence_ids,
            "restored_evidence_texts": [[block_map.get(eid, "") for eid in ids] for ids in evidence_ids],
            "llm_assist_gate": gate.decision,
            "llm_assist_gate_reason": gate.reason,
            "llm_assist_gate_risk_tags": gate.risk_tags,
            "llm_assist_gate_evidence_count": gate.evidence_reference_count,
        }
    )


def _extract_evidence_ids(raw_response: str) -> list[list[str]]:
    parsed = parse_llm_json_response(raw_response)
    if not isinstance(parsed, dict):
        return []
    result: list[list[str]] = []
    for item in parsed.get("segments") or []:
        if not isinstance(item, dict):
            continue
        ids = item.get("evidence_ids")
        if isinstance(ids, list):
            result.append([str(value) for value in ids if str(value or "").strip()])
    return result


def _call_ollama(prompt: str, args: argparse.Namespace) -> str | None:
    payload = {
        "model": args.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": args.num_predict, "num_ctx": 4096},
    }
    try:
        with httpx.Client(timeout=args.timeout) as client:
            response = client.post(f"{args.base_url.rstrip('/')}/api/generate", json=payload)
            if response.status_code != 200:
                return None
            return str(response.json().get("response") or "")
    except (httpx.HTTPError, ValueError):
        return None


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_outputs(
    args: argparse.Namespace,
    candidates: list[dict[str, Any]],
    processed_rows: list[dict[str, Any]],
    allow_rows: list[dict[str, Any]],
) -> None:
    summary = _summarize(candidates, processed_rows, allow_rows, args)
    payload = {"settings": vars(args) | {"input_dir": str(args.input_dir)}, "summary": summary, "strict_allow_candidates": allow_rows}
    args.candidates_json.parent.mkdir(parents=True, exist_ok=True)
    args.candidates_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    args.review_jsonl.write_text(
        "\n".join(json.dumps(_review_row(row), ensure_ascii=False) for row in allow_rows) + ("\n" if allow_rows else ""),
        encoding="utf-8",
    )
    args.collection_report_md.write_text(_render_collection_report(summary), encoding="utf-8")


def _review_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_key": row.get("candidate_key"),
        "source_id": row.get("source_id"),
        "source_file": row.get("source_file"),
        "title": row.get("title"),
        "source_excerpt": row.get("source_excerpt"),
        "fallback_reasons": row.get("fallback_reasons") or [],
        "pre_gate": row.get("pre_gate"),
        "pre_gate_reason": row.get("pre_gate_reason"),
        "rule_segments": row.get("rule_segments") or [],
        "llm_segments": row.get("llm_segments") or [],
        "evidence_ids": row.get("evidence_ids") or [],
        "restored_evidence_texts": row.get("restored_evidence_texts") or [],
        "strict_gate": row.get("llm_assist_gate"),
        "strict_gate_reason": row.get("llm_assist_gate_reason"),
        "risk_tags": row.get("llm_assist_gate_risk_tags") or [],
        "latency_sec": row.get("latency_sec"),
        "human_judgment": "",
        "human_note": "",
        "human_error_type": "",
        "assist_recommendation": "",
    }


def _summarize(
    candidates: list[dict[str, Any]],
    processed_rows: list[dict[str, Any]],
    allow_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    called = len(processed_rows)
    latencies = [float(row["latency_sec"]) for row in processed_rows if row.get("latency_sec") is not None]
    return {
        "seed": args.seed,
        "target_allow": args.target_allow,
        "pre_gate_allow_candidates": len(candidates),
        "llm_called": called,
        "strict_allow_collected": len(allow_rows),
        "strict_allow_rate_called": len(allow_rows) / called if called else 0.0,
        "collection_complete": len(allow_rows) >= args.target_allow,
        "accepted": sum(1 for row in processed_rows if row.get("accepted")),
        "hallucination_suspected": sum(1 for row in processed_rows if row.get("hallucination_suspected")),
        "gate_counts": dict(Counter(row.get("llm_assist_gate") for row in processed_rows)),
        "reject_reason_counts": dict(
            Counter(row.get("reject_reason") or row.get("llm_assist_gate_reason") or "none" for row in processed_rows)
        ),
        "fallback_reason_counts": dict(Counter(reason for row in allow_rows for reason in row.get("fallback_reasons", []))),
        "risk_tag_counts": dict(Counter(tag for row in allow_rows for tag in row.get("llm_assist_gate_risk_tags", []))),
        "latency": _latency_summary(latencies),
    }


def _latency_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
    return {
        "avg": round(statistics.mean(ordered), 3),
        "p50": round(statistics.median(ordered), 3),
        "p95": round(ordered[p95_index], 3),
        "max": round(max(ordered), 3),
    }


def _render_collection_report(summary: dict[str, Any]) -> str:
    lines = [
        "# request_segments strict allow 후보 수집 리포트",
        "",
        "## 요약",
        "",
        "| 지표 | 값 |",
        "| --- | ---: |",
        f"| pre-gate allow candidates | {summary['pre_gate_allow_candidates']} |",
        f"| LLM called | {summary['llm_called']} |",
        f"| strict allow collected | {summary['strict_allow_collected']} |",
        f"| strict allow / called | {summary['strict_allow_rate_called']:.1%} |",
        f"| collection complete | {summary['collection_complete']} |",
        f"| hallucination suspected | {summary['hallucination_suspected']} |",
        "",
        "## latency",
        "",
        f"- avg: {summary['latency']['avg']}",
        f"- p50: {summary['latency']['p50']}",
        f"- p95: {summary['latency']['p95']}",
        f"- max: {summary['latency']['max']}",
        "",
        "## gate counts",
        "",
        "```json",
        json.dumps(summary["gate_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## reject/review reason",
        "",
        "```json",
        json.dumps(summary["reject_reason_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 주의",
        "",
        "이 파일의 strict allow는 validator/gate 통과 후보이며 사람 검수 정답이 아니다.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
