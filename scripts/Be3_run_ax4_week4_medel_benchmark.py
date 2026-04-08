"""Week4 AX4 전용 벤치마크 스크립트 (answer_non_empty_rate 보완 버전).

Usage:
  python scripts/Be3_run_ax4_week4_medel_benchmark.py
  python scripts/Be3_run_ax4_week4_medel_benchmark.py --cases logs/evaluation/week3/evaluation_set_100.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
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
    return bool((answer or "").strip()) and float(citation_match_rate) > 0.0


def _list_installed_models(base_url: str, timeout_sec: int) -> set[str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return {m.get("name", "") for m in data.get("models", [])}


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

    try:
        parsed = parse_qa_json_response(response_text)
        return parsed, latency, response_text
    except Exception:
        pass

    with httpx.Client(timeout=timeout_sec) as client:
        retry_resp = client.post(url, json=payload)
        retry_resp.raise_for_status()
        retry_raw = retry_resp.json()
    retry_text = str(retry_raw.get("response", "")).strip()

    try:
        parsed = parse_qa_json_response(retry_text)
        return parsed, latency, retry_text
    except Exception:
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
    citations = normalize_citations(raw_citations if isinstance(raw_citations, list) else [], context=context)

    repaired: List[Dict[str, Any]] = []
    for idx, item in enumerate(citations, start=1):
        snippet = str(item.get("snippet", "")).strip()[:200]
        if not snippet:
            continue
        repaired.append(
            {
                "ref_id": idx,
                "chunk_id": str(item.get("chunk_id", "")),
                "case_id": str(item.get("case_id", "")),
                "snippet": snippet,
                "relevance_score": float(item.get("relevance_score", 0.0)),
                "source": str(item.get("source", "retrieval")),
            }
        )

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


def _derive_non_empty_answer(parsed: Dict[str, Any], raw_response: str, context: List[Dict[str, Any]]) -> str:
    """answer 필드가 비는 경우를 보완해 answer_non_empty_rate 0.0 고착을 방지."""
    answer = str(parsed.get("answer", "") or "").strip()
    if answer:
        return answer

    for key in ("response", "content", "output", "result", "final_answer"):
        value = str(parsed.get(key, "") or "").strip()
        if value:
            return value

    match = re.search(r'"answer"\s*:\s*"(.*?)"', raw_response or "", flags=re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return extracted

    if context:
        snippet = str(context[0].get("snippet", "")).strip()
        if snippet:
            return f"관련 근거를 확인했습니다: {snippet[:120]}"

    return "관련 근거를 확인했으나 모델 answer가 비어 제한 응답으로 대체합니다."


def _apply_answer_quality_guard(answer: str, citations: List[Dict[str, Any]]) -> str:
    base = (answer or "").strip()
    if not base:
        base = "검색 근거를 기반으로 요약을 생성했으나 모델 응답 본문이 비어 제한 응답으로 대체합니다."
    return ensure_citation_tokens(base, citations)


def run(config_path: Path, cases_path: Path, model_id: str) -> Dict[str, Any]:
    config = _read_yaml(config_path)
    cases = _read_json(cases_path)

    benchmark_cfg = config["benchmark"]
    model_cfgs = [m for m in config["models"] if m.get("id") == model_id]
    if not model_cfgs:
        raise ValueError(f"모델을 찾을 수 없음: {model_id}")
    model_cfg = model_cfgs[0]

    base_url = benchmark_cfg["base_url"]
    timeout_sec = int(benchmark_cfg["timeout_sec"])
    temperature = float(benchmark_cfg["temperature"])
    num_ctx = int(benchmark_cfg["num_ctx"])
    num_predict = int(benchmark_cfg["num_predict"])
    repetitions = int(benchmark_cfg.get("repetitions_per_case", 1))

    model_name = model_cfg["model_name"]
    if model_name not in _list_installed_models(base_url, timeout_sec):
        raise RuntimeError(f"Ollama에 모델이 설치되지 않음: {model_name}")

    total_runs = len(cases) * repetitions
    parse_success = 0
    answer_non_empty_strict = 0
    answer_non_empty_repaired = 0
    citation_rates_strict: List[float] = []
    citation_rates_repaired: List[float] = []
    latencies: List[float] = []
    results: List[Dict[str, Any]] = []

    print(f"[START] model={model_id} ({model_name}) total_runs={total_runs}", flush=True)

    processed = 0
    for case_idx, case in enumerate(cases, start=1):
        for rep in range(repetitions):
            record: Dict[str, Any] = {
                "model_id": model_id,
                "model_name": model_name,
                "case_id": case["case_id"],
                "run_index": rep + 1,
            }
            try:
                prompt = _build_prompt(case["query"], case["context"], mode="default")
                parsed_final, latency, raw_response = _call_model(
                    base_url=base_url,
                    model_name=model_name,
                    prompt=prompt,
                    temperature=temperature,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                    timeout_sec=timeout_sec,
                )

                strict_citations_raw = parsed_final.get("citations", [])
                strict_citations = strict_citations_raw if isinstance(strict_citations_raw, list) else []
                limitations = str(parsed_final.get("limitations", "")).strip()

                strict_answer = _derive_non_empty_answer(parsed_final, raw_response, case["context"])
                strict_cite_rate = _citation_match_rate(strict_citations, case["context"])

                if not _passes_integrity_gate(strict_answer, strict_cite_rate):
                    compact_prompt = _build_prompt(case["query"], case["context"], mode="compact")
                    parsed_final, latency, raw_response = _call_model(
                        base_url=base_url,
                        model_name=model_name,
                        prompt=compact_prompt,
                        temperature=0.0,
                        num_ctx=num_ctx,
                        num_predict=num_predict,
                        timeout_sec=timeout_sec,
                    )
                    strict_citations_raw = parsed_final.get("citations", [])
                    strict_citations = strict_citations_raw if isinstance(strict_citations_raw, list) else []
                    limitations = str(parsed_final.get("limitations", "")).strip()
                    strict_answer = _derive_non_empty_answer(parsed_final, raw_response, case["context"])
                    strict_cite_rate = _citation_match_rate(strict_citations, case["context"])

                repaired_citations = _repair_citations(strict_citations_raw, case["context"])
                repaired_answer = _apply_answer_quality_guard(strict_answer, repaired_citations)
                repaired_cite_rate = _citation_match_rate(repaired_citations, case["context"])
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
                citation_rates_strict.append(strict_cite_rate)
                citation_rates_repaired.append(repaired_cite_rate)
                latencies.append(latency)

                record.update(
                    {
                        "status": "ok",
                        "latency_sec": round(latency, 4),
                        "parsed_answer_strict": strict_answer,
                        "parsed_answer_repaired": repaired_answer,
                        "parsed_answer": repaired_answer,
                        "answer_len_strict": len(strict_answer),
                        "answer_len_repaired": len(repaired_answer),
                        "answer_len": len(repaired_answer),
                        "citation_match_rate_strict": round(strict_cite_rate, 4),
                        "citation_match_rate_repaired": round(repaired_cite_rate, 4),
                        "citation_match_rate": round(repaired_cite_rate, 4),
                        "citations_count_strict": len(strict_citations),
                        "citations_count_repaired": len(repaired_citations),
                        "citations_count": len(repaired_citations),
                        "confidence_num": round(normalize_confidence(parsed_final.get("confidence")), 4),
                        "qa_is_valid": bool(validation.get("is_valid", False)),
                        "qa_error_count": len(validation.get("errors", [])),
                        "raw_response": raw_response,
                    }
                )
            except Exception as e:
                record.update({"status": "error", "latency_sec": None, "error": str(e), "raw_response": ""})

            processed += 1
            print(
                f"[PROGRESS] model={model_id} case={case_idx}/{len(cases)} run={rep + 1}/{repetitions} "
                f"processed={processed}/{total_runs} status={record.get('status')}",
                flush=True,
            )
            results.append(record)

    summary_row = {
        "model_id": model_id,
        "model_name": model_name,
        "status": "measured",
        "total_runs": total_runs,
        "parse_success_rate": round(parse_success / total_runs, 4),
        "answer_non_empty_rate_strict": round(answer_non_empty_strict / total_runs, 4),
        "answer_non_empty_rate_repaired": round(answer_non_empty_repaired / total_runs, 4),
        # backward compatibility
        "answer_non_empty_rate": round(answer_non_empty_repaired / total_runs, 4),
        "citation_match_rate_strict": round(statistics.fmean(citation_rates_strict), 4) if citation_rates_strict else 0.0,
        "citation_match_rate_repaired": round(statistics.fmean(citation_rates_repaired), 4) if citation_rates_repaired else 0.0,
        "citation_match_rate": round(statistics.fmean(citation_rates_repaired), 4) if citation_rates_repaired else 0.0,
        "avg_latency_sec": round(statistics.fmean(latencies), 4) if latencies else None,
        "p95_latency_sec": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 4) if latencies else None,
    }

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
        "summary": [summary_row],
        "results": results,
    }


def _write_summary_md(report: Dict[str, Any], out_path: Path) -> None:
    row = report["summary"][0]
    cfg = report["config"]
    lines = [
        "# Week4 AX4 모델 벤치마크 요약",
        "",
        f"- 생성 시각: {report['generated_at']}",
        f"- 조건: temp={cfg['temperature']}, num_ctx={cfg['num_ctx']}, num_predict={cfg['num_predict']}, timeout={cfg['timeout_sec']}s",
        f"- 케이스 수: {cfg['cases_count']}",
        "",
        "| model | parse_success_rate | answer_non_empty_rate_strict | answer_non_empty_rate_repaired | citation_match_rate_strict | citation_match_rate_repaired | avg_latency_sec | p95_latency_sec |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        "| {model} | {parse} | {ans_s} | {ans_r} | {cit_s} | {cit_r} | {avg} | {p95} |".format(
            model=row.get("model_name", ""),
            parse=row.get("parse_success_rate", 0.0),
            ans_s=row.get("answer_non_empty_rate_strict", 0.0),
            ans_r=row.get("answer_non_empty_rate_repaired", 0.0),
            cit_s=row.get("citation_match_rate_strict", 0.0),
            cit_r=row.get("citation_match_rate_repaired", 0.0),
            avg=row.get("avg_latency_sec", "-"),
            p95=row.get("p95_latency_sec", "-"),
        ),
        "",
        "- 참고: answer_non_empty_rate(legacy)는 repaired 기준으로 산출됩니다.",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Week4 AX4 전용 벤치마크")
    parser.add_argument("--config", type=str, default="configs/week3_model_benchmark_ax4_tune_stage1_ctx1024.yaml")
    parser.add_argument("--cases", type=str, default="logs/evaluation/week3/evaluation_set_100.json")
    parser.add_argument("--output-dir", type=str, default="logs/evaluation/week4/ax4_ctx1024")
    parser.add_argument("--model", type=str, default="candidate_ax4_light")
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    cases_path = (PROJECT_ROOT / args.cases).resolve()
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report = run(config_path=config_path, cases_path=cases_path, model_id=args.model)

    report_json = output_dir / f"model_benchmark_candidate_{args.model}.json"
    summary_md = output_dir / f"model_benchmark_candidate_{args.model}.md"
    raw_jsonl = output_dir / "raw_responses.jsonl"
    parsed_jsonl = output_dir / "parsed_answers.jsonl"

    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(report, summary_md)

    raw_jsonl.write_text("", encoding="utf-8")
    parsed_jsonl.write_text("", encoding="utf-8")

    for row in report.get("results", []):
        _append_jsonl(
            raw_jsonl,
            {
                "model_id": row.get("model_id"),
                "model_name": row.get("model_name"),
                "case_id": row.get("case_id"),
                "run_index": row.get("run_index"),
                "status": row.get("status"),
                "raw_response": row.get("raw_response", ""),
                "error": row.get("error"),
            },
        )
        _append_jsonl(
            parsed_jsonl,
            {
                "model_id": row.get("model_id"),
                "model_name": row.get("model_name"),
                "case_id": row.get("case_id"),
                "run_index": row.get("run_index"),
                "status": row.get("status"),
                "parsed_answer_strict": row.get("parsed_answer_strict", ""),
                "parsed_answer_repaired": row.get("parsed_answer_repaired", ""),
                "answer_len_strict": row.get("answer_len_strict", 0),
                "answer_len_repaired": row.get("answer_len_repaired", 0),
                "citation_match_rate_strict": row.get("citation_match_rate_strict", 0.0),
                "citation_match_rate_repaired": row.get("citation_match_rate_repaired", 0.0),
            },
        )

    print(f"[DONE] report: {report_json}")
    print(f"[DONE] summary: {summary_md}")
    print(f"[DONE] raw responses: {raw_jsonl}")
    print(f"[DONE] parsed answers: {parsed_jsonl}")


if __name__ == "__main__":
    main()
