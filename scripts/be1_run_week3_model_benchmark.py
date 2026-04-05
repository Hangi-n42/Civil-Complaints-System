"""Week3 LLM 모델 동일조건 벤치마크 스크립트.

Usage:
  python scripts/run_week3_model_benchmark.py \
    --config configs/week3_model_benchmark.yaml \
                --cases docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
_TRANSFORMERS_CACHE: Dict[str, Any] = {}


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
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _extract_json_with_recovery(text: str, *, strict: bool = False) -> Dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise ValueError("empty_response")

    # Remove common markdown wrappers before strict parsing.
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return _extract_json(cleaned)
    except Exception:
        if strict:
            raise
        # Fallback: keep response usable for benchmarking even when strict JSON is absent.
        return {
            "answer": cleaned,
            "citations": [],
            "confidence": "low",
            "limitations": "non_json_response_recovered",
        }


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
        context_lines.append(
            f"[{i}] chunk_id={row['chunk_id']} case_id={row['case_id']} score={row.get('score', 0.0)}\\n"
            f"snippet={row['snippet']}"
        )

    return (
        "당신은 민원 검색 컨텍스트 기반 QA 응답기입니다.\\n"
        "역할: 질문에 답하되, 아래 컨텍스트 근거를 사용해 JSON 1개 객체로만 응답합니다.\\n"
        "출력 형식(키 고정): {\"answer\":\"string\",\"citations\":[{\"chunk_id\":\"string\",\"case_id\":\"string\",\"snippet\":\"string\",\"relevance_score\":0.0}],\"confidence\":\"low|medium|high\",\"limitations\":\"string\"}.\\n"
        "중요 규칙:\\n"
        "1) JSON 객체 외 텍스트(머리말/꼬리말/설명/마크다운/코드블록)를 출력하지 않습니다.\\n"
        "2) citations는 최소 1개 이상 포함합니다. 질문에 '최소 2개' 또는 '2개 이상'이 있으면 2개 이상 포함합니다.\\n"
        "3) citations의 chunk_id/case_id/snippet은 반드시 아래 검색 컨텍스트에 있는 값만 사용합니다.\\n"
        "4) 확실하지 않은 내용은 answer에서 단정하지 말고 limitations에 간단히 기록합니다.\\n"
        "5) JSON 문법을 정확히 지키고, 마지막 닫는 중괄호 이후 어떤 문자도 추가하지 않습니다.\\n\\n"
        f"질문: {query}\\n\\n"
        "검색 컨텍스트:\\n"
        + "\\n".join(context_lines)
    )


def _required_min_citations(query: str, default_min: int) -> int:
    q = str(query)
    if "최소 2개" in q or "2개 이상" in q:
        return max(2, default_min)
    return max(1, default_min)


def _validate_citations(
    citations: List[Dict[str, Any]],
    context: List[Dict[str, Any]],
    *,
    min_required: int,
    require_snippet_match: bool,
) -> Tuple[bool, str]:
    if len(citations) < min_required:
        return False, f"insufficient_citations:{len(citations)}<{min_required}"

    context_by_chunk = {str(c.get("chunk_id", "")): c for c in context}
    for c in citations:
        cid = str(c.get("chunk_id", ""))
        if cid not in context_by_chunk:
            return False, f"unknown_chunk_id:{cid}"
        if require_snippet_match:
            expected = str(context_by_chunk[cid].get("snippet", ""))
            got = str(c.get("snippet", ""))
            if got and got not in expected and expected not in got:
                return False, f"snippet_mismatch:{cid}"

    return True, "ok"


def _list_installed_models(base_url: str, timeout_sec: int) -> set[str]:
    url = f"{base_url.rstrip('/')}/api/tags"
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return {m.get("name", "") for m in data.get("models", [])}


def _is_model_installed(model_name: str, installed_models: set[str]) -> bool:
    """Treat an untagged name as ':latest' when checking Ollama installed models."""
    if model_name in installed_models:
        return True
    if ":" not in model_name and f"{model_name}:latest" in installed_models:
        return True
    return False


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
    parsed = _extract_json(response_text)
    return parsed, latency, response_text


def _resolve_model_path(model_ref: str) -> str:
    p = Path(model_ref)
    if p.is_absolute():
        return str(p)
    candidate = (PROJECT_ROOT / p).resolve()
    if candidate.exists():
        return str(candidate)
    return model_ref


def _call_model_transformers(
    *,
    model_ref: str,
    prompt: str,
    temperature: float,
    num_ctx: int,
    num_predict: int,
    parse_mode: str,
    enable_4bit: bool,
    bnb_4bit_quant_type: str,
    bnb_4bit_use_double_quant: bool,
    bnb_4bit_compute_dtype: str,
) -> Tuple[Dict[str, Any], float, str]:
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as e:
        raise RuntimeError(f"transformers_runtime_unavailable: {e}") from e

    resolved_model_ref = _resolve_model_path(model_ref)
    cache_key = (
        resolved_model_ref,
        bool(enable_4bit),
        str(bnb_4bit_quant_type),
        bool(bnb_4bit_use_double_quant),
        str(bnb_4bit_compute_dtype),
    )
    runtime = _TRANSFORMERS_CACHE.get(cache_key)
    if runtime is None:
        model_kwargs: Dict[str, Any] = {
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
        }

        use_4bit = enable_4bit and torch.cuda.is_available()
        if use_4bit:
            try:
                from transformers import BitsAndBytesConfig
            except Exception:
                use_4bit = False

        if use_4bit:
            compute_dtype = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }.get(str(bnb_4bit_compute_dtype).lower(), torch.float16)
            model_kwargs["device_map"] = "auto"
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type=bnb_4bit_quant_type,
                bnb_4bit_use_double_quant=bnb_4bit_use_double_quant,
                bnb_4bit_compute_dtype=compute_dtype,
            )
        else:
            # Fallback path when 4-bit quantization is unavailable.
            if torch.cuda.is_available():
                model_kwargs["torch_dtype"] = torch.float16
                model_kwargs["device_map"] = "auto"
            else:
                model_kwargs["torch_dtype"] = torch.float32
                model_kwargs["device_map"] = "cpu"

        tokenizer = AutoTokenizer.from_pretrained(resolved_model_ref, trust_remote_code=True)
        try:
            model = AutoModelForCausalLM.from_pretrained(resolved_model_ref, **model_kwargs)
        except Exception:
            if use_4bit:
                # Retry once without 4-bit when bitsandbytes/cuda runtime is not available.
                fallback_kwargs = {
                    "trust_remote_code": True,
                    "low_cpu_mem_usage": True,
                    "device_map": "auto" if torch.cuda.is_available() else "cpu",
                    "torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32,
                }
                model = AutoModelForCausalLM.from_pretrained(resolved_model_ref, **fallback_kwargs)
            else:
                raise
        if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        _TRANSFORMERS_CACHE[cache_key] = (tokenizer, model)
    else:
        tokenizer, model = runtime

    prompt_text = prompt
    if getattr(tokenizer, "chat_template", None):
        prompt_text = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True,
        )

    inputs = tokenizer(
        prompt_text,
        return_tensors="pt",
        truncation=True,
        max_length=max(512, num_ctx),
    )
    model_device = model.device
    inputs = {k: v.to(model_device) for k, v in inputs.items()}

    do_sample = temperature > 0
    start = time.perf_counter()
    with torch.no_grad():
        generation_kwargs: Dict[str, Any] = {
            "max_new_tokens": num_predict,
            "min_new_tokens": max(8, min(64, num_predict // 2)),
            "do_sample": do_sample,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if do_sample:
            generation_kwargs["temperature"] = max(0.01, temperature)

        outputs = model.generate(**inputs, **generation_kwargs)
        input_len = inputs["input_ids"].shape[1]
        generated_ids = outputs[0][input_len:]
        response_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

        # Retry once with deterministic decoding when output is empty.
        if not response_text:
            retry_kwargs = {
                **generation_kwargs,
                "do_sample": False,
                "temperature": None,
                "min_new_tokens": max(16, min(96, num_predict)),
            }
            retry_kwargs.pop("temperature", None)
            outputs = model.generate(**inputs, **retry_kwargs)
    latency = time.perf_counter() - start

    input_len = inputs["input_ids"].shape[1]
    generated_ids = outputs[0][input_len:]
    response_text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    parsed = _extract_json_with_recovery(response_text, strict=parse_mode == "strict")
    return parsed, latency, response_text


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


def _make_summary_row(
    *,
    model_id: str,
    model_name: str,
    model_backend: str,
    total_runs: int,
    parse_success: int,
    answer_non_empty: int,
    citation_rates: List[float],
    latencies: List[float],
    status: str,
) -> Dict[str, Any]:
    return {
        "model_id": model_id,
        "model_name": model_name,
        "backend": model_backend,
        "status": status,
        "total_runs": total_runs,
        "parse_success_rate": round(parse_success / total_runs, 4) if total_runs else 0.0,
        "answer_non_empty_rate": round(answer_non_empty / total_runs, 4) if total_runs else 0.0,
        "citation_match_rate": round(statistics.fmean(citation_rates), 4) if citation_rates else 0.0,
        "avg_latency_sec": round(statistics.fmean(latencies), 4) if latencies else None,
        "p95_latency_sec": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 4)
        if latencies
        else None,
    }


def _write_checkpoint_files(
    *,
    output_dir: Path,
    model_id: str,
    suffix: str,
    report: Dict[str, Any],
) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"model_benchmark_{model_id}.checkpoint_{suffix}.json"
    md_path = json_path.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_md(report, md_path)
    return json_path, md_path


def run(
    config_path: Path,
    cases_path: Path,
    target_model_id: str | None = None,
    checkpoint_dir: Path | None = None,
) -> Dict[str, Any]:
    config = _read_yaml(config_path)
    cases = _read_json(cases_path)

    benchmark_cfg = config["benchmark"]
    models = config["models"]
    default_backend = str(benchmark_cfg.get("backend", "ollama")).strip().lower()
    
    # 특정 모델만 선택
    if target_model_id:
        models = [m for m in models if m.get("id") == target_model_id]
        if not models:
            raise ValueError(f"모델을 찾을 수 없음: {target_model_id}")

    base_url = benchmark_cfg.get("base_url", "http://localhost:11434")
    timeout_sec = int(benchmark_cfg["timeout_sec"])
    temperature = float(benchmark_cfg["temperature"])
    num_ctx = int(benchmark_cfg["num_ctx"])
    num_predict = int(benchmark_cfg["num_predict"])
    repetitions = int(benchmark_cfg.get("repetitions_per_case", 1))
    parse_mode = str(benchmark_cfg.get("parse_mode", "lenient")).strip().lower()
    citation_retry_count = int(benchmark_cfg.get("citation_retry_count", 1))
    min_citations_default = int(benchmark_cfg.get("min_citations_default", 1))
    require_snippet_match = bool(benchmark_cfg.get("require_snippet_match", True))
    case_batch_size = int(benchmark_cfg.get("case_batch_size", 100))
    enable_4bit = bool(benchmark_cfg.get("enable_4bit", True))
    bnb_4bit_quant_type = str(benchmark_cfg.get("bnb_4bit_quant_type", "nf4"))
    bnb_4bit_use_double_quant = bool(benchmark_cfg.get("bnb_4bit_use_double_quant", True))
    bnb_4bit_compute_dtype = str(benchmark_cfg.get("bnb_4bit_compute_dtype", "float16"))
    if case_batch_size <= 0:
        case_batch_size = len(cases)

    requires_ollama = any(str(m.get("backend", default_backend)).strip().lower() == "ollama" for m in models)
    installed_models: set[str] = set()
    ollama_infra_error: Optional[str] = None
    if requires_ollama:
        try:
            installed_models = _list_installed_models(base_url, timeout_sec)
        except Exception as e:
            ollama_infra_error = f"Ollama 연결 실패: {e}"
    case_slices = _build_case_slices(cases)

    all_results: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    model_slice_metrics: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}

    def _build_report(
        *,
        summary_rows: List[Dict[str, Any]],
        interrupted: bool = False,
        progress: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "benchmark_name": benchmark_cfg["name"],
            "generated_at": datetime.now().astimezone().isoformat(),
            "interrupted": interrupted,
            "progress": progress or {},
            "config": {
                "backend": default_backend,
                "base_url": base_url,
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "timeout_sec": timeout_sec,
                "repetitions_per_case": repetitions,
                "cases_count": len(cases),
                "parse_mode": parse_mode,
                "citation_retry_count": citation_retry_count,
                "min_citations_default": min_citations_default,
                "require_snippet_match": require_snippet_match,
                "case_batch_size": case_batch_size,
                "enable_4bit": enable_4bit,
                "bnb_4bit_quant_type": bnb_4bit_quant_type,
                "bnb_4bit_use_double_quant": bnb_4bit_use_double_quant,
                "bnb_4bit_compute_dtype": bnb_4bit_compute_dtype,
            },
            "summary": summary_rows,
            "slice_summary": model_slice_metrics,
            "results": all_results,
        }

    for model_cfg in models:
        model_name = model_cfg["model_name"]
        model_id = model_cfg["id"]
        model_backend = str(model_cfg.get("backend", default_backend)).strip().lower()
        model_ref = str(model_cfg.get("model_path") or model_name)

        if model_backend not in {"ollama", "transformers"}:
            summary.append(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "backend": model_backend,
                    "status": "config_error",
                    "message": "지원하지 않는 backend 값 (ollama|transformers)",
                }
            )
            continue

        if model_backend == "ollama" and ollama_infra_error:
            summary.append(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "backend": model_backend,
                    "status": "infra_error",
                    "message": ollama_infra_error,
                }
            )
            continue

        if model_backend == "ollama" and not _is_model_installed(model_name, installed_models):
            summary.append(
                {
                    "model_id": model_id,
                    "model_name": model_name,
                    "backend": model_backend,
                    "status": "not_installed",
                    "message": "Ollama에 설치되지 않아 측정을 건너뜀",
                }
            )
            continue

        latencies: List[float] = []
        parse_success = 0
        answer_non_empty = 0
        citation_rates: List[float] = []

        batched_cases = [
            cases[i : i + case_batch_size] for i in range(0, len(cases), case_batch_size)
        ]
        total_runs = len(cases) * repetitions
        total_batches = len(batched_cases)
        current_batch_idx = 0

        try:
            for batch_idx, batch_cases in enumerate(batched_cases, start=1):
                current_batch_idx = batch_idx
                print(
                    f"[BATCH] model={model_id} {batch_idx}/{total_batches} size={len(batch_cases)}"
                )
                for case in batch_cases:
                    for rep in range(repetitions):
                        prompt = _build_prompt(case["query"], case["context"])
                        record: Dict[str, Any] = {
                        "model_id": model_id,
                        "model_name": model_name,
                        "backend": model_backend,
                        "case_id": case["case_id"],
                        "run_index": rep + 1,
                        "batch_index": batch_idx,
                    }
                    try:
                        required_min_citations = _required_min_citations(
                            case.get("query", ""),
                            min_citations_default,
                        )

                        parsed: Dict[str, Any] = {}
                        latency = 0.0
                        last_err: Optional[Exception] = None
                        for attempt in range(citation_retry_count + 1):
                            attempt_prompt = prompt
                            if attempt > 0:
                                attempt_prompt += (
                                    "\\n\\n이전 출력이 citations 규칙을 위반했습니다. "
                                    f"다시 생성하되 citations는 최소 {required_min_citations}개 포함하고, "
                                    "chunk_id는 검색 컨텍스트에 있는 값만 사용하세요."
                                )
                            try:
                                if model_backend == "ollama":
                                    parsed, latency, _ = _call_model(
                                        base_url=base_url,
                                        model_name=model_name,
                                        prompt=attempt_prompt,
                                        temperature=temperature,
                                        num_ctx=num_ctx,
                                        num_predict=num_predict,
                                        timeout_sec=timeout_sec,
                                    )
                                else:
                                    parsed, latency, _ = _call_model_transformers(
                                        model_ref=model_ref,
                                        prompt=attempt_prompt,
                                        temperature=temperature,
                                        num_ctx=num_ctx,
                                        num_predict=num_predict,
                                        parse_mode=parse_mode,
                                        enable_4bit=enable_4bit,
                                        bnb_4bit_quant_type=bnb_4bit_quant_type,
                                        bnb_4bit_use_double_quant=bnb_4bit_use_double_quant,
                                        bnb_4bit_compute_dtype=bnb_4bit_compute_dtype,
                                    )

                                citations = parsed.get("citations", [])
                                if isinstance(citations, dict):
                                    citations = [citations]
                                if not isinstance(citations, list):
                                    citations = []

                                valid, reason = _validate_citations(
                                    citations,
                                    case["context"],
                                    min_required=required_min_citations,
                                    require_snippet_match=require_snippet_match,
                                )
                                if not valid:
                                    raise ValueError(f"citation_validation_failed:{reason}")

                                break
                            except Exception as e:
                                last_err = e
                                if attempt >= citation_retry_count:
                                    raise

                        if last_err and not parsed:
                            raise last_err

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
                    r
                    for r in all_results
                    if r.get("model_id") == model_id and r.get("model_name") == model_name
                ]
                model_slice_metrics[model_name] = _slice_metrics_for_model(model_records, case_slices)

                interim_row = _make_summary_row(
                    model_id=model_id,
                    model_name=model_name,
                    model_backend=model_backend,
                    total_runs=total_runs,
                    parse_success=parse_success,
                    answer_non_empty=answer_non_empty,
                    citation_rates=citation_rates,
                    latencies=latencies,
                    status="in_progress",
                )
                interim_report = _build_report(
                    summary_rows=[*summary, interim_row],
                    interrupted=False,
                    progress={
                        "model_id": model_id,
                        "batch_index": batch_idx,
                        "total_batches": total_batches,
                    },
                )
                if checkpoint_dir is not None:
                    ck_json, _ = _write_checkpoint_files(
                        output_dir=checkpoint_dir,
                        model_id=model_id,
                        suffix=f"batch_{batch_idx}",
                        report=interim_report,
                    )
                    print(f"[CHECKPOINT] saved: {ck_json}")

        except KeyboardInterrupt:
            interrupted_row = _make_summary_row(
                model_id=model_id,
                model_name=model_name,
                model_backend=model_backend,
                total_runs=total_runs,
                parse_success=parse_success,
                answer_non_empty=answer_non_empty,
                citation_rates=citation_rates,
                latencies=latencies,
                status="interrupted",
            )
            partial_report = _build_report(
                summary_rows=[*summary, interrupted_row],
                interrupted=True,
                progress={
                    "model_id": model_id,
                    "batch_index": current_batch_idx,
                    "total_batches": total_batches,
                },
            )
            if checkpoint_dir is not None:
                ck_json, _ = _write_checkpoint_files(
                    output_dir=checkpoint_dir,
                    model_id=model_id,
                    suffix=f"interrupted_batch_{current_batch_idx}",
                    report=partial_report,
                )
                print(f"[CHECKPOINT] interrupted partial saved: {ck_json}")
            return partial_report

        summary.append(
            _make_summary_row(
                model_id=model_id,
                model_name=model_name,
                model_backend=model_backend,
                total_runs=total_runs,
                parse_success=parse_success,
                answer_non_empty=answer_non_empty,
                citation_rates=citation_rates,
                latencies=latencies,
                status="measured",
            )
        )

    return _build_report(summary_rows=summary, interrupted=False)


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
    lines.append("| model | status | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")

    for row in report["summary"]:
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

    report = run(
        config_path=config_path,
        cases_path=cases_path,
        target_model_id=args.model,
        checkpoint_dir=output_dir,
    )

    # 모델별 파일명 결정
    if args.model:
        # 특정 모델 운영 중: model_benchmark_{model_id}.json
        model_id = args.model
        report_json = output_dir / f"model_benchmark_{model_id}.json"
    else:
        # 모든 모델 운영: model_benchmark_report.json
        report_json = output_dir / "model_benchmark_report.json"
    
    summary_md = report_json.with_suffix(".md")

    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_summary_md(report, summary_md)

    if report.get("interrupted"):
        print("[WARN] benchmark interrupted, partial result persisted.")
    print(f"[DONE] report: {report_json}")
    print(f"[DONE] summary: {summary_md}")


if __name__ == "__main__":
    main()
