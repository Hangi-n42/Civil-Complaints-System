"""Week3 LLM 모델 동일조건 벤치마크 스크립트.

Usage:
  python scripts/run_week3_model_benchmark.py \
    --config configs/week3_model_benchmark.yaml \
                --cases docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import yaml

PROJECT_ROOT = Path(__file__).parent.parent


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback 1: extract from fenced json block.
    fence = "```json"
    if fence in text and "```" in text[text.find(fence) + len(fence) :]:
        block_start = text.find(fence) + len(fence)
        block_end = text.find("```", block_start)
        if block_end > block_start:
            candidate = text[block_start:block_end].strip()
            if candidate:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    # Fallback 2: scan all { ... } ranges and pick the first valid object.
    starts = [i for i, ch in enumerate(text) if ch == "{"]
    ends = [i for i, ch in enumerate(text) if ch == "}"]
    for start in starts:
        for end in reversed(ends):
            if end <= start:
                continue
            candidate = text[start : end + 1]
            try:
                loaded = json.loads(candidate)
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("JSON object not found in model response", text, 0)


def _has_meaningful_payload(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict):
        return False
    answer = str(parsed.get("answer", "")).strip()
    citations = parsed.get("citations", [])
    if isinstance(citations, dict):
        citations = [citations]
    has_citations = isinstance(citations, list) and len(citations) > 0
    return bool(answer) or has_citations


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        v = value.strip().lower()
        if v == "high":
            return 0.85
        if v == "medium":
            return 0.6
        if v == "low":
            return 0.35
        try:
            return max(0.0, min(1.0, float(v)))
        except ValueError:
            return 0.0
    return 0.0


def _build_prompt(query: str, context: List[Dict[str, Any]]) -> str:
    context_lines = []
    for i, row in enumerate(context, start=1):
        snippet = str(row["snippet"]).replace("\n", " ").strip()
        snippet = snippet[:180]
        context_lines.append(
            f"[{i}] chunk_id={row['chunk_id']} case_id={row['case_id']} score={row.get('score', 0.0)}\\n"
            f"snippet={snippet}"
        )

    return (
        "검색 기반 QA입니다. 반드시 JSON 객체 1개만 출력하세요(설명 금지).\\n"
        "스키마: {\"answer\":\"string\",\"citations\":[{\"chunk_id\":\"string\",\"case_id\":\"string\",\"snippet\":\"string\",\"relevance_score\":0.0}],\"confidence\":\"low|medium|high\",\"limitations\":\"string\"}.\\n"
        "제약: answer는 2문장 이내, citations는 최대 2개.\\n"
        "주의: citations는 아래 근거 목록의 chunk_id/case_id/snippet만 사용하세요.\\n\\n"
        f"질문: {query}\\n\\n"
        "검색 컨텍스트:\\n"
        + "\\n".join(context_lines)
    )


def _recover_partial_payload(text: str) -> Dict[str, Any]:
    raw = text.strip()
    answer = ""
    citations: List[Dict[str, Any]] = []
    confidence = ""
    limitations = ""

    answer_match = re.search(r'"answer"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', raw)
    if answer_match:
        answer = answer_match.group(1).replace('\\n', ' ').replace('\\"', '"').strip()

    confidence_match = re.search(r'"confidence"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', raw)
    if confidence_match:
        confidence = confidence_match.group(1).strip()

    limitations_match = re.search(r'"limitations"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', raw)
    if limitations_match:
        limitations = limitations_match.group(1).replace('\\n', ' ').replace('\\"', '"').strip()

    if not answer:
        # Last-resort: keep a short clean plain-text answer so benchmark can track non-empty outputs.
        cleaned = raw.replace("\\n", " ").strip()
        answer = cleaned[:220]

    return {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "limitations": limitations,
    }


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
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        },
    }

    # First attempt: strict JSON mode for fast/clean parse.
    payload_json = dict(payload)
    payload_json["format"] = "json"

    start = time.perf_counter()
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(url, json=payload_json)
        resp.raise_for_status()
        raw = resp.json()
    latency = time.perf_counter() - start
    response_text = str(raw.get("response", "")).strip()
    parsed = _extract_json(response_text)

    # AX4 can return '{}' in strict mode even when normal mode has usable content.
    if _has_meaningful_payload(parsed):
        return parsed, latency, response_text

    start_fallback = time.perf_counter()
    with httpx.Client(timeout=timeout_sec) as client:
        resp_fb = client.post(url, json=payload)
        resp_fb.raise_for_status()
        raw_fb = resp_fb.json()
    latency += time.perf_counter() - start_fallback

    response_text_fb = str(raw_fb.get("response", "")).strip()
    try:
        parsed_fb = _extract_json(response_text_fb)
    except json.JSONDecodeError:
        parsed_fb = _recover_partial_payload(response_text_fb)
    return parsed_fb, latency, response_text_fb


def _citation_match_rate(citations: List[Dict[str, Any]], context: List[Dict[str, Any]]) -> float:
    if not citations:
        return 0.0
    valid_chunk_ids = {str(c.get("chunk_id", "")) for c in context}
    matched = 0
    for c in citations:
        if str(c.get("chunk_id", "")) in valid_chunk_ids:
            matched += 1
    return matched / len(citations)


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
                    "answer_non_empty_rate": 0.0,
                    "citation_match_rate": 0.0,
                    "avg_latency_sec": 0.0,
                }
                continue

            ok_rows = [r for r in rows if r.get("status") == "ok"]
            parse_success_rate = len(ok_rows) / len(rows)
            answer_non_empty_rate = (
                len([r for r in ok_rows if int(r.get("answer_len", 0)) > 0]) / len(rows)
            )
            citation_scores = [float(r.get("citation_match_rate", 0.0)) for r in ok_rows]
            latencies = [float(r.get("latency_sec", 0.0)) for r in ok_rows if r.get("latency_sec") is not None]

            out[slice_key][group_name] = {
                "runs": len(rows),
                "parse_success_rate": round(parse_success_rate, 4),
                "answer_non_empty_rate": round(answer_non_empty_rate, 4),
                "citation_match_rate": round(statistics.fmean(citation_scores), 4) if citation_scores else 0.0,
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
        answer_non_empty = 0
        citation_rates: List[float] = []

        for case in cases:
            for rep in range(repetitions):
                prompt = _build_prompt(case["query"], case["context"])
                record: Dict[str, Any] = {
                    "model_id": model_id,
                    "model_name": model_name,
                    "case_id": case["case_id"],
                    "run_index": rep + 1,
                }
                try:
                    parsed, latency, _ = _call_model(
                        base_url=base_url,
                        model_name=model_name,
                        prompt=prompt,
                        temperature=temperature,
                        num_ctx=num_ctx,
                        num_predict=num_predict,
                        timeout_sec=timeout_sec,
                    )
                    latencies.append(latency)

                    answer = str(parsed.get("answer", "")).strip()
                    citations = parsed.get("citations", [])
                    if isinstance(citations, dict):
                        citations = [citations]
                    if not isinstance(citations, list):
                        citations = []

                    parse_success += 1
                    if answer:
                        answer_non_empty += 1

                    cite_rate = _citation_match_rate(citations, case["context"])
                    citation_rates.append(cite_rate)

                    record.update(
                        {
                            "status": "ok",
                            "latency_sec": round(latency, 4),
                            "answer_len": len(answer),
                            "citations_count": len(citations),
                            "citation_match_rate": round(cite_rate, 4),
                            "confidence_num": round(_normalize_confidence(parsed.get("confidence")), 4),
                        }
                    )
                except Exception as e:
                    record.update(
                        {
                            "status": "error",
                            "latency_sec": None,
                            "error": str(e),
                        }
                    )
                all_results.append(record)

            model_records = [
                r for r in all_results if r.get("model_id") == model_id and r.get("model_name") == model_name
            ]
            model_slice_metrics[model_name] = _slice_metrics_for_model(model_records, case_slices)

        total_runs = len(cases) * repetitions
        summary.append(
            {
                "model_id": model_id,
                "model_name": model_name,
                "status": "measured",
                "total_runs": total_runs,
                "parse_success_rate": round(parse_success / total_runs, 4),
                "answer_non_empty_rate": round(answer_non_empty / total_runs, 4),
                "citation_match_rate": round(statistics.fmean(citation_rates), 4) if citation_rates else 0.0,
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
    cfg = report.get("config", {})
    if cfg:
        lines.append(
            f"- 조건: temp={cfg['temperature']}, num_ctx={cfg['num_ctx']}, num_predict={cfg['num_predict']}, timeout={cfg['timeout_sec']}s"
        )
        lines.append(f"- 케이스 수: {cfg['cases_count']}")
    else:
        lines.append("- 조건: N/A (실행 인프라 오류)")
        lines.append("- 케이스 수: N/A")
    lines.append("- 추가 지표: scenario_type/risk_level/requires_multi_request/time_sensitivity 슬라이스")
    lines.append("")
    lines.append("| model | status | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")

    for row in report.get("summary", []):
        lines.append(
            "| {model_name} | {status} | {parse_success_rate} | {answer_non_empty_rate} | {citation_match_rate} | {avg_latency_sec} | {p95_latency_sec} |".format(
                model_name=row.get("model_name", ""),
                status=row.get("status", ""),
                parse_success_rate=row.get("parse_success_rate", "-"),
                answer_non_empty_rate=row.get("answer_non_empty_rate", "-"),
                citation_match_rate=row.get("citation_match_rate", "-"),
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
                    "  - {group}: runs={runs}, parse={parse}, answer={answer}, citation={citation}, latency={latency}".format(
                        group=group_name,
                        runs=metrics.get("runs", 0),
                        parse=metrics.get("parse_success_rate", 0.0),
                        answer=metrics.get("answer_non_empty_rate", 0.0),
                        citation=metrics.get("citation_match_rate", 0.0),
                        latency=metrics.get("avg_latency_sec", 0.0),
                    )
                )
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

    # 모델별 파일명 결정
    if args.model:
        # 특정 모델 운영 중: model_benchmark_{model_id}.json
        model_id = args.model
        report_json = output_dir / f"model_benchmark_{model_id}.json"
    else:
        # 모든 모델 운영: model_benchmark_report.json
        report_json = output_dir / "model_benchmark_report.json"
    
    summary_md = report_json.with_suffix(".md")

    try:
        report = run(config_path=config_path, cases_path=cases_path, target_model_id=args.model)
    except Exception as exc:
        report = {
            "benchmark_name": "week3_llm_model_benchmark",
            "generated_at": datetime.now().astimezone().isoformat(),
            "status": "infra_error",
            "error": str(exc),
            "summary": [
                {
                    "model_id": args.model or "all",
                    "status": "infra_error",
                    "message": "Ollama 연결 실패 또는 모델 미기동",
                }
            ],
            "results": [],
        }

    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary_md(report, summary_md)

    print(f"[DONE] report: {report_json}")
    print(f"[DONE] summary: {summary_md}")


if __name__ == "__main__":
    main()
