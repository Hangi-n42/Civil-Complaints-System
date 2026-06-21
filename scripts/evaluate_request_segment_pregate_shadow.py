"""request_segments LLM pre-gate shadow 평가 스크립트."""

from __future__ import annotations

import argparse
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
    validate_block_llm_segments,
)
from app.structuring.preprocessing import civil_text, process_raw_record


def main() -> None:
    args = _parse_args()
    if args.reuse_json:
        results = _reuse_results(args.reuse_json)
        mode = "reuse"
    else:
        candidates = _sample_candidates(args.input_dir, sample_size=args.sample_size, seed=args.seed)
        results = _evaluate_candidates(candidates, args)
        mode = "live"

    summary = _summarize(results, seed=args.seed, mode=mode)
    payload = {
        "settings": {
            "mode": mode,
            "seed": args.seed,
            "sample_size": args.sample_size,
            "input_dir": str(args.input_dir),
            "model": args.model,
            "base_url": args.base_url,
            "timeout": args.timeout,
            "num_predict": args.num_predict,
            "reuse_json": str(args.reuse_json) if args.reuse_json else None,
        },
        "summary": summary,
        "results": results,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(_render_markdown(payload), encoding="utf-8")
    print(json.dumps({"json": str(args.output_json), "markdown": str(args.output_md), "summary": summary}, ensure_ascii=False, indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/raw_data"))
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--output-json", type=Path, default=Path("reports/request_segment_llm_pregate_shadow_eval.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/request_segment_llm_pregate_shadow_eval.md"))
    parser.add_argument("--reuse-json", type=Path, default=None)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--model", default="exaone3.5:7.8b")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--num-predict", type=int, default=256)
    return parser.parse_args()


def _iter_raw_records(input_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict):
                records.append({"__file": path.name, **item})
    return records


def _sample_candidates(input_dir: Path, *, sample_size: int, seed: int) -> list[dict[str, Any]]:
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
        candidates.append(
            {
                "source_id": processed.get("source_id") or raw.get("__file"),
                "source_file": raw.get("__file"),
                "title": processed.get("title") or "",
                "question": processed.get("client_question") or "",
                "source_text": source_text,
                "fallback_reasons": decision.reasons,
                "rule_segments": rule_output.get("request_segments") or [],
                "rule_trace": rule_output.get("complexity_trace") or {},
                "topic_type": processed.get("consulting_category") or "general",
            }
        )

    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[:sample_size]


def _evaluate_candidates(candidates: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        rule_output = {
            "request_segments": candidate["rule_segments"],
            "complexity_trace": candidate["rule_trace"],
        }
        pre_gate = assess_llm_pre_gate(
            policy="v2_strict",
            fallback_reasons=candidate["fallback_reasons"],
            source_text=candidate["source_text"],
            rule_output=rule_output,
            prompt_style="block",
        )
        row = {
            **candidate,
            "index": index,
            "llm_pre_gate": pre_gate.decision,
            "llm_pre_gate_reason": pre_gate.reason,
            "llm_pre_gate_risk_tags": pre_gate.risk_tags,
            "llm_called": False,
            "latency_sec": None,
            "raw_response": None,
            "accepted": False,
            "reject_reason": None,
            "hallucination_suspected": False,
            "llm_segments": [],
            "llm_decision": None,
            "llm_assist_gate": "not_evaluated",
            "llm_assist_gate_reason": None,
            "llm_assist_gate_risk_tags": [],
            "llm_assist_gate_evidence_count": 0,
        }
        if pre_gate.decision != "allow_call":
            results.append(row)
            continue

        source_blocks = build_source_blocks(candidate["source_text"], max_blocks=30)
        prompt = build_block_prompt(source_blocks, rule_output)
        start = time.perf_counter()
        raw_response = _call_ollama(prompt, args)
        latency = time.perf_counter() - start
        row["llm_called"] = True
        row["latency_sec"] = round(latency, 3)
        row["source_block_count"] = len(source_blocks)
        row["raw_response"] = raw_response
        if raw_response is None:
            row["reject_reason"] = "llm_call_failed"
            results.append(row)
            continue

        validation = validate_block_llm_segments(
            raw_response,
            source_blocks=source_blocks,
            rule_output=rule_output,
            fallback_reasons=candidate["fallback_reasons"],
        )
        _apply_validation_and_gate(row, validation, candidate, raw_response)
        results.append(row)
    return results


def _reuse_results(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reused: list[dict[str, Any]] = []
    for row in payload.get("results", []):
        candidate = {
            "source_id": row.get("source_id"),
            "source_file": row.get("source_file"),
            "title": row.get("title") or "",
            "question": row.get("question") or "",
            "source_text": row.get("source_text") or "",
            "fallback_reasons": row.get("fallback_reasons") or [],
            "rule_segments": row.get("rule_segments") or [],
            "rule_trace": row.get("rule_trace") or {},
            "topic_type": row.get("topic_type") or "general",
            "index": row.get("index"),
        }
        rule_output = {"request_segments": candidate["rule_segments"], "complexity_trace": candidate["rule_trace"]}
        pre_gate = assess_llm_pre_gate(
            policy="v2_strict",
            fallback_reasons=candidate["fallback_reasons"],
            source_text=candidate["source_text"],
            rule_output=rule_output,
            prompt_style="block",
        )
        new_row = {
            **candidate,
            "llm_pre_gate": pre_gate.decision,
            "llm_pre_gate_reason": pre_gate.reason,
            "llm_pre_gate_risk_tags": pre_gate.risk_tags,
            "llm_called": row.get("llm_called", False) and pre_gate.decision == "allow_call",
            "latency_sec": row.get("latency_sec") if row.get("llm_called") else None,
            "raw_response": row.get("raw_response"),
            "source_block_count": row.get("source_block_count"),
            "accepted": False,
            "reject_reason": None,
            "hallucination_suspected": False,
            "llm_segments": [],
            "llm_decision": None,
            "llm_assist_gate": "not_evaluated",
            "llm_assist_gate_reason": None,
            "llm_assist_gate_risk_tags": [],
            "llm_assist_gate_evidence_count": 0,
        }
        if pre_gate.decision != "allow_call":
            reused.append(new_row)
            continue
        if not new_row["raw_response"]:
            new_row["reject_reason"] = "missing_reused_raw_response"
            reused.append(new_row)
            continue
        source_blocks = build_source_blocks(candidate["source_text"], max_blocks=30)
        validation = validate_block_llm_segments(
            new_row["raw_response"],
            source_blocks=source_blocks,
            rule_output=rule_output,
            fallback_reasons=candidate["fallback_reasons"],
        )
        _apply_validation_and_gate(new_row, validation, candidate, new_row["raw_response"])
        reused.append(new_row)
    return reused


def _apply_validation_and_gate(row: dict[str, Any], validation: LLMValidationResult, candidate: dict[str, Any], raw_response: str) -> None:
    rule_output = {"request_segments": candidate["rule_segments"], "complexity_trace": candidate["rule_trace"]}
    gate = evaluate_assist_limited_v2_strict_gate(
        validation=validation,
        rule_output=rule_output,
        fallback_reasons=candidate["fallback_reasons"],
        source_text=candidate["source_text"],
        prompt_style="block",
        raw_response=raw_response,
    )
    row.update(
        {
            "accepted": validation.accepted,
            "reject_reason": validation.reject_reason,
            "hallucination_suspected": validation.hallucination_suspected,
            "llm_segments": validation.segments,
            "llm_decision": validation.decision,
            "llm_assist_gate": gate.decision,
            "llm_assist_gate_reason": gate.reason,
            "llm_assist_gate_risk_tags": gate.risk_tags,
            "llm_assist_gate_evidence_count": gate.evidence_reference_count,
        }
    )


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


def _summarize(results: list[dict[str, Any]], *, seed: int, mode: str) -> dict[str, Any]:
    total = len(results)
    called = [row for row in results if row.get("llm_called")]
    accepted = [row for row in results if row.get("accepted")]
    allow = [row for row in results if row.get("llm_assist_gate") == "allow_assist"]
    latencies = [float(row["latency_sec"]) for row in called if row.get("latency_sec") is not None]
    pre_gate_counts = Counter(row.get("llm_pre_gate") for row in results)
    gate_counts = Counter(row.get("llm_assist_gate") for row in results)
    reject_counts = Counter(
        row.get("reject_reason") or row.get("llm_assist_gate_reason") or row.get("llm_pre_gate_reason") or "none"
        for row in results
    )
    risk_counts = Counter(tag for row in results for tag in (row.get("llm_pre_gate_risk_tags") or row.get("llm_assist_gate_risk_tags") or []))
    segment_counts = Counter(len(row.get("llm_segments") or []) for row in allow)
    return {
        "seed": seed,
        "mode": mode,
        "total_fallback_candidates": total,
        "pre_gate_counts": dict(pre_gate_counts),
        "pre_gate_allow_call": pre_gate_counts.get("allow_call", 0),
        "pre_gate_skipped": total - pre_gate_counts.get("allow_call", 0),
        "llm_called": len(called),
        "llm_call_rate": len(called) / total if total else 0.0,
        "validation_accepted": len(accepted),
        "validation_accepted_rate": len(accepted) / len(called) if called else 0.0,
        "strict_gate_counts": dict(gate_counts),
        "strict_allow_assist": len(allow),
        "strict_allow_rate_total": len(allow) / total if total else 0.0,
        "strict_allow_rate_called": len(allow) / len(called) if called else 0.0,
        "hallucination_suspected": sum(1 for row in results if row.get("hallucination_suspected")),
        "reject_reason_counts": dict(reject_counts),
        "risk_tag_counts": dict(risk_counts),
        "allow_segment_count_distribution": dict(segment_counts),
        "latency": _latency_summary(latencies),
        "representative_allow_ids": [row.get("source_id") for row in allow[:10]],
        "representative_skip_ids": [row.get("source_id") for row in results if row.get("llm_pre_gate") != "allow_call"][:10],
        "representative_reject_ids": [row.get("source_id") for row in results if row.get("llm_assist_gate") in {"review_required", "reject"}][:10],
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


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    settings = payload["settings"]
    lines = [
        "# request_segments pre-gate shadow 평가",
        "",
        "## 평가 설정",
        "",
        f"- mode: {settings['mode']}",
        f"- seed: {settings['seed']}",
        f"- sample_size: {settings['sample_size']}",
        f"- model: {settings['model']}",
        f"- reuse_json: {settings['reuse_json'] or '-'}",
        "",
        "## 핵심 지표",
        "",
        "| 지표 | 값 |",
        "| --- | ---: |",
        f"| fallback candidates | {summary['total_fallback_candidates']} |",
        f"| pre_gate allow_call | {summary['pre_gate_allow_call']} |",
        f"| pre_gate skipped | {summary['pre_gate_skipped']} |",
        f"| LLM called | {summary['llm_called']} |",
        f"| LLM call rate | {summary['llm_call_rate']:.1%} |",
        f"| validation accepted | {summary['validation_accepted']} |",
        f"| strict allow_assist | {summary['strict_allow_assist']} |",
        f"| strict allow / total | {summary['strict_allow_rate_total']:.1%} |",
        f"| hallucination suspected | {summary['hallucination_suspected']} |",
        "",
        "## latency",
        "",
        f"- avg: {summary['latency']['avg']}",
        f"- p50: {summary['latency']['p50']}",
        f"- p95: {summary['latency']['p95']}",
        f"- max: {summary['latency']['max']}",
        "",
        "## pre_gate 분포",
        "",
        "```json",
        json.dumps(summary["pre_gate_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## strict gate 분포",
        "",
        "```json",
        json.dumps(summary["strict_gate_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## reject/review reason",
        "",
        "```json",
        json.dumps(summary["reject_reason_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## 해석",
        "",
        "이 평가는 accepted/allow를 사람 검수 정답으로 간주하지 않는다. strict allow는 내부 실험 후보이며, BE3 action-item 확정값으로 바로 쓰면 안 된다.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
