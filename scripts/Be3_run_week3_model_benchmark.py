"""Week3 LLM 모델 동일조건 벤치마크 스크립트.

Usage:
  python scripts/Be3_run_week3_model_benchmark.py \
    --config configs/week3_model_benchmark.yaml \
                --cases docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.generation.parsing.json_utils import normalize_confidence, parse_qa_json_response
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
)


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _recover_minimal_response(raw_text: str) -> Dict[str, Any]:
    # 마지막 방어선: 제한 응답으로 스키마만 유지
    ans_match = re.search(r'"answer"\s*:\s*"(.*?)"', raw_text, flags=re.DOTALL)
    answer = ans_match.group(1).strip() if ans_match else ""
    return {
        "answer": answer,
        "citations": [],
        "confidence": "low",
        "limitations": "response_format_recovered",
    }


def _build_prompt(query: str, context: List[Dict[str, Any]], mode: str = "default") -> str:
    context_lines = []
    for i, row in enumerate(context, start=1):
        context_lines.append(
            f"[{i}] chunk_id={row['chunk_id']} case_id={row['case_id']} score={row.get('score', 0.0)}\\n"
            f"snippet={row['snippet']}"
        )

    mode_hint = ""
    if mode == "compact":
        mode_hint = "\n재요청: compact JSON 한 줄만 출력하세요. 부가 설명/코드블록 금지."

    return (
        "검색 기반 QA입니다. 오직 JSON만 출력하세요.\\n"
        "스키마: {\"answer\":\"string\",\"citations\":[{\"chunk_id\":\"string\",\"case_id\":\"string\",\"snippet\":\"string\",\"relevance_score\":0.0}],\"confidence\":\"low|medium|high\",\"limitations\":\"string\"}.\\n"
        "주의: citations는 아래 근거 목록의 chunk_id/case_id/snippet만 사용하세요.\\n\\n"
        + mode_hint
        + "\\n\\n"
        f"질문: {query}\\n\\n"
        "검색 컨텍스트:\\n"
        + "\\n".join(context_lines)
    )


def _passes_integrity_gate(answer: str, citation_match_rate: float) -> bool:
    """정합성 통과 기준: 비어있지 않은 answer + citation 매칭률 > 0."""
    return bool((answer or "").strip()) and float(citation_match_rate) > 0.0


def _list_installed_models(base_url: str, timeout_sec: int) -> set[str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    models = {m.get("name", "") for m in data.get("models", [])}
    # Normalize by adding both full name and base name (without tag)
    normalized = set()
    for name in models:
        normalized.add(name)
        if ':' in name:
            normalized.add(name.split(':')[0])  # Also add without tag
    return normalized


def _call_model(
    *,
    base_url: str,
    model_name: str,
    prompt: str,
    temperature: float,
    num_ctx: int,
    num_predict: int,
    timeout_sec: int,
) -> Tuple[Dict[str, Any], float, str]:
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }
    start = time.perf_counter()
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        raw = resp.json()
    latency = time.perf_counter() - start
    response_text = str(raw.get("response", "")).strip()

    # 1) API와 동일한 공용 파서 시도
    try:
        parsed = parse_qa_json_response(response_text)
        return parsed, latency, response_text
    except Exception:
        pass

    # 2) 재시도 1회 (동일 파라미터)
    with httpx.Client(timeout=timeout_sec) as client:
        retry_resp = client.post(url, json=payload)
        retry_resp.raise_for_status()
        retry_raw = retry_resp.json()
    retry_text = str(retry_raw.get("response", "")).strip()

    try:
        parsed = parse_qa_json_response(retry_text)
        return parsed, latency, retry_text
    except Exception:
        # 3) 제한 응답 반환
        return _recover_minimal_response(retry_text), latency, retry_text


def _citation_match_rate(citations: List[Dict[str, Any]], context: List[Dict[str, Any]]) -> float:
    if not citations:
        return 0.0
    valid_chunk_ids = {str(c.get("chunk_id", "")) for c in context}
    matched = 0
    for c in citations:
        if str(c.get("chunk_id", "")) in valid_chunk_ids:
            matched += 1
    return matched / len(citations)


def _repair_citations(raw_citations: Any, context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """API 정규화 기준을 따르되, 벤치마크에서는 최소 1개 citation을 보장한다."""
    citations = normalize_citations(raw_citations if isinstance(raw_citations, list) else [], context=context)

    repaired: List[Dict[str, Any]] = []
    for idx, item in enumerate(citations, start=1):
        snippet = str(item.get("snippet", "")).strip()[:200]
        if not snippet:
            continue

        repaired_item: Dict[str, Any] = {
            "ref_id": idx,
            "chunk_id": str(item.get("chunk_id", "")),
            "case_id": str(item.get("case_id", "")),
            "snippet": snippet,
            "relevance_score": float(item.get("relevance_score", 0.0)),
            "source": str(item.get("source", "retrieval")),
        }
        doc_id = str(item.get("doc_id", "")).strip()
        if doc_id:
            repaired_item["doc_id"] = doc_id

        repaired.append(repaired_item)

    # 최소 1개 citation 보장 (fallback)
    if not repaired and context:
        first = context[0]
        repaired.append(
            {
                "ref_id": 1,
                "chunk_id": str(first.get("chunk_id", "")),
                "case_id": str(first.get("case_id", "")),
                "snippet": str(first.get("snippet", "")).strip()[:200],
                "relevance_score": float(first.get("score", first.get("relevance_score", 0.0))),
                "source": "retrieval_fallback",
            }
        )

    return repaired


def _apply_answer_quality_guard(answer: str, citations: List[Dict[str, Any]]) -> str:
    """빈 answer를 제한 응답 템플릿으로 보정하고 citation 토큰을 보장한다."""
    base = (answer or "").strip()
    if not base:
        base = "검색 근거를 기반으로 요약을 생성했으나 모델 응답 본문이 비어 제한 응답으로 대체합니다."
    return ensure_citation_tokens(base, citations)


def _build_case_slices(cases: List[Dict[str, Any]]) -> Dict[str, Dict[str, set[str]]]:
    slices: Dict[str, Dict[str, set[str]]] = {
        "scenario_type": {},
        "risk_level": {},
        "requires_multi_request": {},
        "time_sensitivity": {},
    }
    for case in cases:
        cid = str(case.get("case_id", ""))
        for key in slices:
            raw = case.get(key)
            label = str(raw).strip().lower() if raw is not None else "unknown"
            slices[key].setdefault(label, set()).add(cid)
    return slices


def _slice_metrics_for_model(
    model_results: List[Dict[str, Any]],
    case_slices: Dict[str, Dict[str, set[str]]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    by_case: Dict[str, List[Dict[str, Any]]] = {}
    for row in model_results:
        by_case.setdefault(str(row.get("case_id", "")), []).append(row)

    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for slice_key, groups in case_slices.items():
        out[slice_key] = {}
        for group_name, case_ids in groups.items():
            rows: List[Dict[str, Any]] = []
            for cid in case_ids:
                rows.extend(by_case.get(cid, []))

            if not rows:
                out[slice_key][group_name] = {
                    "runs": 0,
                    "parse_success_rate": 0.0,
                    "answer_non_empty_rate_strict": 0.0,
                    "answer_non_empty_rate_repaired": 0.0,
                    "citation_match_rate_strict": 0.0,
                    "citation_match_rate_repaired": 0.0,
                    "answer_non_empty_rate": 0.0,
                    "citation_match_rate": 0.0,
                    "avg_latency_sec": 0.0,
                }
                continue

            ok_rows = [r for r in rows if r.get("status") == "ok"]
            parse_success_rate = len(ok_rows) / len(rows)
            answer_non_empty_rate_strict = (
                len([r for r in ok_rows if int(r.get("answer_len_strict", 0)) > 0]) / len(rows)
            )
            answer_non_empty_rate_repaired = (
                len([r for r in ok_rows if int(r.get("answer_len_repaired", 0)) > 0]) / len(rows)
            )
            citation_scores_strict = [float(r.get("citation_match_rate_strict", 0.0)) for r in ok_rows]
            citation_scores_repaired = [float(r.get("citation_match_rate_repaired", 0.0)) for r in ok_rows]
            latencies = [float(r.get("latency_sec", 0.0)) for r in ok_rows if r.get("latency_sec") is not None]

            out[slice_key][group_name] = {
                "runs": len(rows),
                "parse_success_rate": round(parse_success_rate, 4),
                "answer_non_empty_rate_strict": round(answer_non_empty_rate_strict, 4),
                "answer_non_empty_rate_repaired": round(answer_non_empty_rate_repaired, 4),
                "citation_match_rate_strict": round(statistics.fmean(citation_scores_strict), 4)
                if citation_scores_strict
                else 0.0,
                "citation_match_rate_repaired": round(statistics.fmean(citation_scores_repaired), 4)
                if citation_scores_repaired
                else 0.0,
                # Backward compatibility: 기본 필드는 repaired 기준으로 유지
                "answer_non_empty_rate": round(answer_non_empty_rate_repaired, 4),
                "citation_match_rate": round(statistics.fmean(citation_scores_repaired), 4)
                if citation_scores_repaired
                else 0.0,
                "avg_latency_sec": round(statistics.fmean(latencies), 4) if latencies else 0.0,
            }

    return out


def run(config_path: Path, cases_path: Path, target_model_id: str | None = None) -> Dict[str, Any]:
    config = _read_yaml(config_path)
    cases = _read_json(cases_path)

    benchmark_cfg = config["benchmark"]
    models = config["models"]
    
    # 특정 모델만 선택
    if target_model_id:
        models = [m for m in models if m.get("id") == target_model_id]
        if not models:
            raise ValueError(f"모델을 찾을 수 없음: {target_model_id}")

    base_url = benchmark_cfg["base_url"]
    timeout_sec = int(benchmark_cfg["timeout_sec"])
    temperature = float(benchmark_cfg["temperature"])
    num_ctx = int(benchmark_cfg["num_ctx"])
    num_predict = int(benchmark_cfg["num_predict"])
    repetitions = int(benchmark_cfg.get("repetitions_per_case", 1))

    installed_models = _list_installed_models(base_url, timeout_sec)
    case_slices = _build_case_slices(cases)

    all_results: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    model_slice_metrics: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}

    for model_cfg in models:
        model_name = model_cfg["model_name"]
        model_id = model_cfg["id"]

        if model_name not in installed_models:
            summary.append(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "status": "not_installed",
                    "message": "Ollama에 설치되지 않아 측정을 건너뜀",
                }
            )
            continue

        latencies: List[float] = []
        parse_success = 0
        answer_non_empty_strict = 0
        answer_non_empty_repaired = 0
        citation_rates_strict: List[float] = []
        citation_rates_repaired: List[float] = []
        total_runs = len(cases) * repetitions
        processed_runs = 0

        print(
            f"[START] model={model_id} ({model_name}) total_runs={total_runs}",
            flush=True,
        )

        for case_idx, case in enumerate(cases, start=1):
            for rep in range(repetitions):
                prompt = _build_prompt(case["query"], case["context"], mode="default")
                record: Dict[str, Any] = {
                    "model_id": model_id,
                    "model_name": model_name,
                    "case_id": case["case_id"],
                    "run_index": rep + 1,
                }
                try:
                    parsed_final, latency, raw_response = _call_model(
                        base_url=base_url,
                        model_name=model_name,
                        prompt=prompt,
                        temperature=temperature,
                        num_ctx=num_ctx,
                        num_predict=num_predict,
                        timeout_sec=timeout_sec,
                    )

                    raw_answer = str(parsed_final.get("answer", "")).strip()
                    limitations = str(parsed_final.get("limitations", "")).strip()
                    strict_citations_raw = parsed_final.get("citations", [])
                    strict_citations = strict_citations_raw if isinstance(strict_citations_raw, list) else []

                    # strict: 원문 모델 출력 기반
                    strict_answer = raw_answer
                    strict_cite_rate = _citation_match_rate(strict_citations, case["context"])
                    integrity_passed_initial = _passes_integrity_gate(strict_answer, strict_cite_rate)
                    retry_reason = ""
                    retry_stage = "none"

                    # 재시도 목표 확장: JSON 파싱 성공 이후에도 정합성 실패면 compact 재시도
                    if not integrity_passed_initial:
                        retry_reason = "INTEGRITY_GATE_FAILED"
                        retry_stage = "compact"
                        compact_prompt = _build_prompt(case["query"], case["context"], mode="compact")
                        parsed_compact, latency_compact, raw_response_compact = _call_model(
                            base_url=base_url,
                            model_name=model_name,
                            prompt=compact_prompt,
                            temperature=0.0,
                            num_ctx=num_ctx,
                            num_predict=num_predict,
                            timeout_sec=timeout_sec,
                        )

                        # compact 재시도 결과로 strict 기준 재평가
                        parsed_final = parsed_compact
                        raw_response = raw_response_compact
                        latency = latency_compact
                        raw_answer = str(parsed_compact.get("answer", "")).strip()
                        limitations = str(parsed_compact.get("limitations", "")).strip()
                        strict_citations_raw = parsed_compact.get("citations", [])
                        strict_citations = strict_citations_raw if isinstance(strict_citations_raw, list) else []
                        strict_answer = raw_answer
                        strict_cite_rate = _citation_match_rate(strict_citations, case["context"])

                    latencies.append(latency)

                    # repaired: 보정 후 기준
                    repaired_citations = _repair_citations(strict_citations_raw, case["context"])
                    repaired_answer = _apply_answer_quality_guard(strict_answer, repaired_citations)
                    validation = build_validation_result(
                        answer=repaired_answer,
                        citations=repaired_citations,
                        limitations=limitations,
                        context=case["context"],
                    )

                    parse_success += 1
                    if strict_answer:
                        answer_non_empty_strict += 1
                    if repaired_answer:
                        answer_non_empty_repaired += 1

                    repaired_cite_rate = _citation_match_rate(repaired_citations, case["context"])
                    citation_rates_strict.append(strict_cite_rate)
                    citation_rates_repaired.append(repaired_cite_rate)

                    record.update(
                        {
                            "status": "ok",
                            "latency_sec": round(latency, 4),
                            "answer_len_strict": len(strict_answer),
                            "answer_len_repaired": len(repaired_answer),
                            # Backward compatibility: answer_len은 repaired 기준으로 유지
                            "answer_len": len(repaired_answer),
                            "raw_response": raw_response,
                            "parsed_answer_strict": strict_answer,
                            "parsed_answer_repaired": repaired_answer,
                            # Backward compatibility: parsed_answer는 repaired 기준으로 유지
                            "parsed_answer": repaired_answer,
                            "citations_count_strict": len(strict_citations),
                            "citations_count_repaired": len(repaired_citations),
                            # Backward compatibility: citations_count는 repaired 기준으로 유지
                            "citations_count": len(repaired_citations),
                            "citation_match_rate_strict": round(strict_cite_rate, 4),
                            "citation_match_rate_repaired": round(repaired_cite_rate, 4),
                            # Backward compatibility: 기본 필드는 repaired 기준
                            "citation_match_rate": round(repaired_cite_rate, 4),
                            "confidence_num": round(normalize_confidence(parsed_final.get("confidence")), 4),
                            "qa_is_valid": bool(validation.get("is_valid", False)),
                            "qa_error_count": len(validation.get("errors", [])),
                            "integrity_gate_passed": _passes_integrity_gate(strict_answer, strict_cite_rate),
                            "retry_reason": retry_reason,
                            "retry_stage": retry_stage,
                        }
                    )
                except Exception as e:
                    record.update(
                        {
                            "status": "error",
                            "latency_sec": None,
                            "raw_response": "",
                            "parsed_answer": "",
                            "error": str(e),
                        }
                    )

                processed_runs += 1
                print(
                    f"[PROGRESS] model={model_id} case={case_idx}/{len(cases)} run={rep + 1}/{repetitions} "
                    f"processed={processed_runs}/{total_runs} status={record.get('status')}",
                    flush=True,
                )
                all_results.append(record)

            model_records = [
                r for r in all_results if r.get("model_id") == model_id and r.get("model_name") == model_name
            ]
            model_slice_metrics[model_name] = _slice_metrics_for_model(model_records, case_slices)

        summary.append(
            {
                "model_id": model_id,
                "model_name": model_name,
                "status": "measured",
                "total_runs": total_runs,
                "parse_success_rate": round(parse_success / total_runs, 4),
                "answer_non_empty_rate_strict": round(answer_non_empty_strict / total_runs, 4),
                "answer_non_empty_rate_repaired": round(answer_non_empty_repaired / total_runs, 4),
                "citation_match_rate_strict": round(statistics.fmean(citation_rates_strict), 4)
                if citation_rates_strict
                else 0.0,
                "citation_match_rate_repaired": round(statistics.fmean(citation_rates_repaired), 4)
                if citation_rates_repaired
                else 0.0,
                # Backward compatibility: 기본 필드는 repaired 기준으로 유지
                "answer_non_empty_rate": round(answer_non_empty_repaired / total_runs, 4),
                "citation_match_rate": round(statistics.fmean(citation_rates_repaired), 4)
                if citation_rates_repaired
                else 0.0,
                "avg_latency_sec": round(statistics.fmean(latencies), 4) if latencies else None,
                "p95_latency_sec": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 4)
                if latencies
                else None,
            }
        )

    return {
        "benchmark_name": benchmark_cfg["name"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "config": {
            "base_url": base_url,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "timeout_sec": timeout_sec,
            "repetitions_per_case": repetitions,
            "cases_count": len(cases),
        },
        "summary": summary,
        "slice_summary": model_slice_metrics,
        "results": all_results,
    }


def _write_summary_md(report: Dict[str, Any], out_path: Path) -> None:
    lines = []
    lines.append("# Week3 모델 벤치마크 요약")
    lines.append("")
    lines.append(f"- 생성 시각: {report['generated_at']}")
    cfg = report["config"]
    lines.append(
        f"- 조건: temp={cfg['temperature']}, num_ctx={cfg['num_ctx']}, num_predict={cfg['num_predict']}, timeout={cfg['timeout_sec']}s"
    )
    lines.append(f"- 케이스 수: {cfg['cases_count']}")
    lines.append("- 추가 지표: scenario_type/risk_level/requires_multi_request/time_sensitivity 슬라이스")
    lines.append("")
    lines.append("| model | status | parse_success_rate | answer_non_empty_rate_strict | answer_non_empty_rate_repaired | citation_match_rate_strict | citation_match_rate_repaired | avg_latency_sec | p95_latency_sec |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    for row in report["summary"]:
        lines.append(
            "| {model_name} | {status} | {parse_success_rate} | {answer_non_empty_rate_strict} | {answer_non_empty_rate_repaired} | {citation_match_rate_strict} | {citation_match_rate_repaired} | {avg_latency_sec} | {p95_latency_sec} |".format(
                model_name=row.get("model_name", ""),
                status=row.get("status", ""),
                parse_success_rate=row.get("parse_success_rate", "-"),
                answer_non_empty_rate_strict=row.get("answer_non_empty_rate_strict", "-"),
                answer_non_empty_rate_repaired=row.get("answer_non_empty_rate_repaired", "-"),
                citation_match_rate_strict=row.get("citation_match_rate_strict", "-"),
                citation_match_rate_repaired=row.get("citation_match_rate_repaired", "-"),
                avg_latency_sec=row.get("avg_latency_sec", "-"),
                p95_latency_sec=row.get("p95_latency_sec", "-"),
            )
        )

    lines.append("")
    lines.append("## 슬라이스 요약")
    lines.append("")
    for model_name, model_slices in report.get("slice_summary", {}).items():
        lines.append(f"### {model_name}")
        for slice_key, groups in model_slices.items():
            lines.append(f"- {slice_key}")
            for group_name, metrics in groups.items():
                lines.append(
                    "  - {group}: runs={runs}, parse={parse}, answer(strict/repaired)={answer_strict}/{answer_repaired}, citation(strict/repaired)={citation_strict}/{citation_repaired}, latency={latency}".format(
                        group=group_name,
                        runs=metrics.get("runs", 0),
                        parse=metrics.get("parse_success_rate", 0.0),
                        answer_strict=metrics.get("answer_non_empty_rate_strict", 0.0),
                        answer_repaired=metrics.get("answer_non_empty_rate_repaired", 0.0),
                        citation_strict=metrics.get("citation_match_rate_strict", 0.0),
                        citation_repaired=metrics.get("citation_match_rate_repaired", 0.0),
                        latency=metrics.get("avg_latency_sec", 0.0),
                    )
                )
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Week3 LLM 모델 벤치마크")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/week3_model_benchmark.yaml",
        help="벤치마크 설정 파일 경로",
    )
    parser.add_argument(
        "--cases",
        type=str,
        default="docs/40_delivery/week3/model_test_assets/evaluation_set.json",
        help="벤치마크 케이스 파일 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="logs/evaluation/week3",
        help="결과 출력 디렉터리",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="특정 모델만 실행 (모델 ID 지정, 예: candidate_exaone_3_5_7_8b)",
    )
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    cases_path = (PROJECT_ROOT / args.cases).resolve()
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_response_jsonl = output_dir / "raw_responses.jsonl"
    parsed_answer_jsonl = output_dir / "parsed_answers.jsonl"

    raw_response_jsonl.write_text("", encoding="utf-8")
    parsed_answer_jsonl.write_text("", encoding="utf-8")

    report = run(config_path=config_path, cases_path=cases_path, target_model_id=args.model)

    # 모델별 파일명 결정
    if args.model:
        # 특정 모델 운영 중: model_benchmark_candidate_{model_id}.json
        model_id = args.model
        report_json = output_dir / f"model_benchmark_candidate_{model_id}.json"
    else:
        # 모든 모델 운영: model_benchmark_report.json
        report_json = output_dir / "model_benchmark_report.json"
    
    summary_md = report_json.with_suffix(".md")

    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary_md(report, summary_md)

    for row in report.get("results", []):
        raw_response_row = {
            "model_id": row.get("model_id"),
            "model_name": row.get("model_name"),
            "case_id": row.get("case_id"),
            "run_index": row.get("run_index"),
            "status": row.get("status"),
            "raw_response": row.get("raw_response", ""),
            "error": row.get("error"),
        }
        parsed_answer_row = {
            "model_id": row.get("model_id"),
            "model_name": row.get("model_name"),
            "case_id": row.get("case_id"),
            "run_index": row.get("run_index"),
            "status": row.get("status"),
            "parsed_answer_strict": row.get("parsed_answer_strict", ""),
            "parsed_answer_repaired": row.get("parsed_answer_repaired", ""),
            "citations_count_strict": row.get("citations_count_strict", 0),
            "citations_count_repaired": row.get("citations_count_repaired", 0),
            "citation_match_rate_strict": row.get("citation_match_rate_strict", 0.0),
            "citation_match_rate_repaired": row.get("citation_match_rate_repaired", 0.0),
            # Backward compatibility
            "parsed_answer": row.get("parsed_answer", ""),
            "citations_count": row.get("citations_count", 0),
            "citation_match_rate": row.get("citation_match_rate", 0.0),
        }
        _append_jsonl(raw_response_jsonl, raw_response_row)
        _append_jsonl(parsed_answer_jsonl, parsed_answer_row)

    print(f"[DONE] report: {report_json}")
    print(f"[DONE] summary: {summary_md}")
    print(f"[DONE] raw responses: {raw_response_jsonl}")
    print(f"[DONE] parsed answers: {parsed_answer_jsonl}")


if __name__ == "__main__":
    main()

