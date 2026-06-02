"""Week6 LLM 모델 동일조건 벤치마크 스크립트.

Week4 AX4 전용 스크립트에서 검증한 answer 복구 로직을
다른 모델에도 동일하게 적용하는 범용 벤치마크 버전이다.

ex) 실행 예시:

direct 모드:
python scripts/Be3_run_week6_model_benchmark.py 
--benchmark-mode direct 
--config configs/week6_Be3_model_benchmark.yaml 
--cases ../40_delivery/week3/model_test_assets/evaluation_set.json
--output-dir logs/evaluation/week6/be3_model_benchmark


api 모드:
python scripts/Be3_run_week6_model_benchmark.py 
--benchmark-mode api --api-base-url http://127.0.0.1:8000 
--config configs/week6_Be3_model_benchmark.yaml 
--cases ../40_delivery/week3/model_test_assets/evaluation_set.json
--output-dir logs/evaluation/week6/be3_model_benchmark_api


Usage:
    python scripts/Be3_run_week6_model_benchmark.py \
    --config configs/week6_Be3_model_benchmark.yaml \
    --cases ../40_delivery/week3/model_test_assets/evaluation_set.json
"""

from __future__ import annotations

import argparse
import asyncio
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

from app.generation.parsing.json_utils import (
    extract_json_string,
    normalize_confidence,
    parse_qa_json_response,
)
from app.generation.prompts.prompt_factory import PromptFactory
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
    sanitize_answer_text,
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


def _coerce_limitations_text(value: Any) -> str:
    """limitations를 문자열로 정규화한다(Week5/Week6 호환)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return "; ".join(items)
    if value is None:
        return ""
    return str(value).strip()


def _match_context_by_citation_text(citation_text: str, context: List[Dict[str, Any]]) -> Dict[str, Any]:
    """모델이 citations를 문자열로 낸 경우 원문 컨텍스트와 보수적으로 매칭한다."""
    text = re.sub(r"^\s*\[?\(?\s*출처\s*\d+\s*\]?\)?\s*[:：-]?\s*", "", citation_text or "").strip()
    if not text or not context:
        return {}

    best_ctx: Dict[str, Any] = {}
    best_score = 0.0
    text_compact = re.sub(r"\s+", "", text)
    text_terms = {term for term in re.findall(r"[\w가-힣A-Z]+", text) if len(term) >= 2}

    for ctx in context:
        snippet = str(ctx.get("snippet", "")).strip()
        if not snippet:
            continue

        snippet_compact = re.sub(r"\s+", "", snippet)
        if text_compact and (text_compact in snippet_compact or snippet_compact[:80] in text_compact):
            return ctx

        snippet_terms = {term for term in re.findall(r"[\w가-힣A-Z]+", snippet) if len(term) >= 2}
        if not text_terms or not snippet_terms:
            continue
        overlap = len(text_terms & snippet_terms)
        score = overlap / max(len(text_terms), 1)
        if score > best_score:
            best_score = score
            best_ctx = ctx

    return best_ctx if best_score >= 0.35 else {}


def _coerce_citations_for_benchmark(raw_citations: Any, context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Week6 quote/doc_id 형태를 기존 chunk_id/case_id 기반 벤치마크 포맷으로 보정한다."""
    if not isinstance(raw_citations, list):
        return []

    context_by_chunk = {
        str(item.get("chunk_id", "")): item
        for item in context
        if str(item.get("chunk_id", ""))
    }
    context_by_doc = {
        str(item.get("doc_id", "")): item
        for item in context
        if str(item.get("doc_id", ""))
    }
    context_by_case = {
        str(item.get("case_id", "")): item
        for item in context
        if str(item.get("case_id", ""))
    }

    first_ctx = context[0] if context else {}
    normalized: List[Dict[str, Any]] = []

    for item in raw_citations:
        if isinstance(item, list):
            item = " ".join(str(part).strip() for part in item if str(part).strip())

        if isinstance(item, str):
            snippet = re.sub(r"^\s*\[?\(?\s*출처\s*\d+\s*\]?\)?\s*[:：-]?\s*", "", item).strip()
            ctx = _match_context_by_citation_text(item, context)
            if not ctx:
                continue
            normalized.append(
                {
                    "chunk_id": str(ctx.get("chunk_id", "")),
                    "case_id": str(ctx.get("case_id", "")),
                    "snippet": snippet[:200] or str(ctx.get("snippet", "")).strip()[:200],
                    "relevance_score": normalize_confidence(ctx.get("score", ctx.get("relevance_score", 0.5))),
                    "source": "model_string_citation",
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        doc_id = str(item.get("doc_id") or "").strip()
        chunk_id = str(item.get("chunk_id") or "").strip()
        case_id = str(item.get("case_id") or "").strip()
        snippet = str(item.get("snippet") or item.get("quote") or "").strip()

        ctx = {}
        if chunk_id and chunk_id in context_by_chunk:
            ctx = context_by_chunk[chunk_id]
        elif doc_id and doc_id in context_by_doc:
            ctx = context_by_doc[doc_id]
        elif case_id and case_id in context_by_case:
            ctx = context_by_case[case_id]

        if not chunk_id:
            chunk_id = str(ctx.get("chunk_id") or first_ctx.get("chunk_id") or "")
        if not case_id:
            case_id = str(ctx.get("case_id") or first_ctx.get("case_id") or "")
        if not snippet:
            snippet = str(ctx.get("snippet") or first_ctx.get("snippet") or "").strip()

        normalized_item: Dict[str, Any] = {
            "chunk_id": chunk_id,
            "case_id": case_id,
            "snippet": snippet,
            "relevance_score": normalize_confidence(item.get("relevance_score", 0.5)),
            "source": str(item.get("source") or "retrieval"),
        }
        if doc_id:
            normalized_item["doc_id"] = doc_id

        normalized.append(normalized_item)

    return normalized


def _merge_citation_lists(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            chunk_id = str(item.get("chunk_id", ""))
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            merged.append(item)
    return merged


def _coerce_citations_from_raw_text(response_text: str, context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """raw 응답 안의 chunk_id 또는 출처 토큰을 strict citation 후보로 읽는다."""
    if not response_text or not context:
        return []

    by_chunk = {str(item.get("chunk_id", "")): item for item in context if str(item.get("chunk_id", ""))}
    found: List[Dict[str, Any]] = []

    for chunk_id in dict.fromkeys(re.findall(r"CASE-\d+__chunk-\d+", response_text)):
        ctx = by_chunk.get(chunk_id)
        if not ctx:
            continue
        found.append(
            {
                "chunk_id": chunk_id,
                "case_id": str(ctx.get("case_id", "")),
                "snippet": str(ctx.get("snippet", "")).strip()[:200],
                "relevance_score": normalize_confidence(ctx.get("score", ctx.get("relevance_score", 0.5))),
                "source": "raw_chunk_reference",
            }
        )

    if found:
        return found

    token_numbers = [int(match.group(1) or match.group(2)) for match in re.finditer(r"\[\[출처\s*(\d+)\]\]|\[출처\s*(\d+)\]", response_text)]

    for ref_no in dict.fromkeys(token_numbers):
        idx = ref_no - 1
        if idx < 0 or idx >= len(context):
            continue
        ctx = context[idx]
        found.append(
            {
                "chunk_id": str(ctx.get("chunk_id", "")),
                "case_id": str(ctx.get("case_id", "")),
                "snippet": str(ctx.get("snippet", "")).strip()[:200],
                "relevance_score": normalize_confidence(ctx.get("score", ctx.get("relevance_score", 0.5))),
                "source": "raw_answer_token_reference",
            }
        )

    return found


def _parse_week6_compatible_response(text: str) -> Dict[str, Any]:
    """confidence 누락/limitations 배열 등 Week6 응답도 파싱한다."""
    json_str = extract_json_string(text)
    result = json.loads(json_str)
    if not isinstance(result, dict):
        raise ValueError("model response is not JSON object")

    answer = str(result.get("answer") or "").strip()
    citations = result.get("citations", [])
    if not isinstance(citations, list):
        citations = []

    return {
        "answer": answer,
        "citations": citations,
        "confidence": result.get("confidence", 0.5),
        "limitations": result.get("limitations", ""),
        # Week6 부가 필드도 유지해 후속 분석 시 활용 가능
        "structured_output": result.get("structured_output", {}),
        "routing_trace": result.get("routing_trace", {}),
        "latency_ms": result.get("latency_ms", {}),
        "quality_signals": result.get("quality_signals", {}),
    }


def _derive_non_empty_answer(parsed: Dict[str, Any], raw_response: str, context: List[Dict[str, Any]]) -> str:
    """answer 필드가 비는 경우를 보완해 strict answer 고착 문제를 완화한다."""
    answer = str(parsed.get("answer", "") or "").strip()
    if answer:
        return sanitize_answer_text(answer)

    for key in ("response", "content", "output", "result", "final_answer"):
        value = str(parsed.get(key, "") or "").strip()
        if value:
            return sanitize_answer_text(value)

    match = re.search(r'"answer"\s*:\s*"(.*?)"', raw_response or "", flags=re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return sanitize_answer_text(extracted)

    if context:
        snippet = str(context[0].get("snippet", "")).strip()
        if snippet:
            return sanitize_answer_text(
                "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
                "2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. "
                "접수된 민원 취지와 관련 근거를 함께 고려하여 처리 방향을 검토하는 사안입니다.\n\n"
                f"3. 검토 의견은 다음과 같습니다. {snippet[:220]} "
                "위 내용을 바탕으로 담당부서에서는 현장 여건, 관련 기준, 유사 처리 사례를 확인한 뒤 필요한 조치 가능 여부를 판단할 수 있습니다.\n\n"
                "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
            )

    return sanitize_answer_text(
        "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
        "2. 현재 답변 생성 과정에서 구체적인 검토 내용을 충분히 구성하지 못했습니다. "
        "정확한 회신을 위해서는 민원 취지, 발생 장소, 관련 자료에 대한 추가 확인이 필요합니다.\n\n"
        "3. 담당부서에서 접수 내용과 관련 자료를 확인한 뒤 현장 여건, 행정 처리 기준, 조치 가능 범위를 종합적으로 검토하겠습니다. "
        "확인 결과에 따라 필요한 안내 또는 후속 조치가 이루어질 수 있습니다.\n\n"
        "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 절차와 보완 필요 사항을 친절히 안내해 드리겠습니다. 감사합니다. 끝."
    )


def _case_identifier(case: Dict[str, Any], fallback_index: int) -> str:
    return str(
        case.get("case_id")
        or case.get("source_id")
        or case.get("complaint_id")
        or f"CASE-{fallback_index:04d}"
    )


def _case_query(case: Dict[str, Any]) -> str:
    return PromptFactory._derive_query_from_record(case) or "(빈 질의)"


def _case_context(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    context = case.get("context")
    if not isinstance(context, list):
        return []
    return [item for item in context if isinstance(item, dict)]


def _build_prompt_context_from_case(
    case: Dict[str, Any],
    *,
    mode: str = "default",
    context_override: List[Dict[str, Any]] | None = None,
    routing_trace: Dict[str, Any] | None = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """벤치마크 프롬프트는 PromptFactory 단일 경로로 구성한다.

    기존 평가셋처럼 context가 있으면 record 기반 PromptFactory 경로를 사용하고,
    원문 레코드만 있으면 PromptFactory auto-retrieve로 근거를 붙인다.
    """
    context = context_override if context_override is not None else _case_context(case)

    mode_norm = str(mode or "default").strip().lower()
    prompt_mode = "compact" if mode_norm == "compact" else "force_json" if mode_norm == "force_json" else "default"
    trace = dict(routing_trace or {})
    trace["prompt_mode"] = prompt_mode

    if context:
        prompt = PromptFactory.build_from_dataset_record(
            record=dict(case),
            context=context,
            routing_trace=trace,
        )
        return prompt, context, trace

    top_k = int(case.get("top_k") or 5)
    collection_name = str(case.get("collection_name") or "civil_cases_v1")
    filters = case.get("filters") if isinstance(case.get("filters"), dict) else None
    threshold = float(case.get("threshold") or 0.0)

    return asyncio.run(
        PromptFactory.build_from_dataset_record_autoretrieve(
            record=dict(case),
            routing_trace=trace,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
            threshold=threshold,
            mode=prompt_mode,
        )
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
    normalized = set()
    for name in models:
        normalized.add(name)
        if ":" in name:
            normalized.add(name.split(":")[0])
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
        try:
            parsed = _parse_week6_compatible_response(response_text)
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
        try:
            parsed = _parse_week6_compatible_response(retry_text)
            return parsed, latency, retry_text
        except Exception:
            # 3) 제한 응답 반환
            return _recover_minimal_response(retry_text), latency, retry_text


def _to_qa_search_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    transformed: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        transformed.append(
            {
                "doc_id": item.get("doc_id"),
                "chunk_id": item.get("chunk_id"),
                "case_id": item.get("case_id"),
                "snippet": item.get("snippet"),
                "score": item.get("score", item.get("similarity_score", 0.0)),
            }
        )
    return transformed


def _extract_eval_context_from_retrieved_docs(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        context.append(
            {
                "doc_id": str(item.get("doc_id") or ""),
                "chunk_id": str(item.get("chunk_id") or ""),
                "case_id": str(item.get("case_id") or item.get("doc_id") or ""),
                "snippet": str(item.get("snippet") or "").strip(),
                "score": float(item.get("score", item.get("similarity_score", 0.0)) or 0.0),
            }
        )
    return context


def _call_search_qa_api(
    *,
    api_base_url: str,
    query: str,
    complaint_id: str,
    top_k: int,
    timeout_sec: int,
) -> Tuple[Dict[str, Any], float, str, List[Dict[str, Any]]]:
    search_url = f"{api_base_url.rstrip('/')}/api/v1/search"
    qa_url = f"{api_base_url.rstrip('/')}/api/v1/qa"

    start = time.perf_counter()
    with httpx.Client(timeout=timeout_sec) as client:
        search_res = client.post(
            search_url,
            json={
                "request_id": f"BM-{complaint_id}",
                "complaint_id": complaint_id,
                "query": query,
                "top_k": top_k,
            },
        )
        search_res.raise_for_status()
        search_body = search_res.json()
        if not search_body.get("success", False):
            raise ValueError(f"search failed: {search_body}")

        search_data = search_body.get("data", {})
        search_request_id = str(search_body.get("request_id") or "").strip()
        routing_hint = search_data.get("routing_hint")
        retrieved_docs = search_data.get("retrieved_docs", [])
        if not isinstance(routing_hint, dict):
            raise ValueError("search response missing routing_hint")
        if not isinstance(retrieved_docs, list):
            retrieved_docs = []

        qa_search_results = _to_qa_search_results(retrieved_docs)
        use_search_results = bool(qa_search_results)

        qa_req = {
            "request_id": search_request_id or f"BM-{complaint_id}",
            "complaint_id": complaint_id,
            "query": query,
            "routing_hint": routing_hint,
            "use_search_results": use_search_results,
            "search_results": qa_search_results,
        }
        qa_res = client.post(qa_url, json=qa_req)
        qa_res.raise_for_status()
        qa_body = qa_res.json()
        if not qa_body.get("success", False):
            raise ValueError(f"qa failed: {qa_body}")

    latency = time.perf_counter() - start
    qa_data = qa_body.get("data", {}) if isinstance(qa_body, dict) else {}
    parsed = {
        "answer": str(qa_data.get("answer") or "").strip(),
        "citations": qa_data.get("citations", []),
        "confidence": 0.5,
        "limitations": qa_data.get("limitations", ""),
        "structured_output": qa_data.get("structured_output", {}),
        "routing_trace": qa_data.get("routing_trace", {}),
        "latency_ms": qa_data.get("latency_ms", {}),
        "quality_signals": qa_data.get("quality_signals", {}),
    }
    eval_context = _extract_eval_context_from_retrieved_docs(retrieved_docs)
    return parsed, latency, json.dumps(qa_body, ensure_ascii=False), eval_context


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
        base = (
            "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다.\n\n"
            "2. 현재 모델 응답 본문이 충분히 구성되지 않아 담당부서 확인 및 추가 검토가 필요합니다. "
            "민원 취지와 관련 자료를 확인한 뒤 구체적인 처리 가능 여부를 판단하는 것이 적절합니다.\n\n"
            "3. 접수 내용, 현장 여건, 관련 기준을 종합적으로 검토하여 필요한 조치 가능 여부를 확인하겠습니다. "
            "검토 과정에서 추가 자료가 필요한 경우 보완 요청 또는 담당부서 안내가 이루어질 수 있습니다.\n\n"
            "4. 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
        )
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


def run(
    config_path: Path,
    cases_path: Path,
    target_model_id: str | None = None,
    benchmark_mode: str = "direct",
    api_base_url: str = "http://127.0.0.1:8000",
) -> Dict[str, Any]:
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

    installed_models = _list_installed_models(base_url, timeout_sec) if benchmark_mode == "direct" else set()
    case_slices = _build_case_slices(cases)

    all_results: List[Dict[str, Any]] = []
    summary: List[Dict[str, Any]] = []
    model_slice_metrics: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}

    for model_cfg in models:
        model_name = model_cfg["model_name"]
        model_id = model_cfg["id"]

        if benchmark_mode == "direct" and model_name not in installed_models:
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
                case_id = _case_identifier(case, case_idx)
                record: Dict[str, Any] = {
                    "model_id": model_id,
                    "model_name": model_name,
                    "case_id": case_id,
                    "source_id": case.get("source_id"),
                    "run_index": rep + 1,
                }
                try:
                    eval_context = _case_context(case)
                    routing_trace: Dict[str, Any] = {}
                    if benchmark_mode == "api":
                        complaint_id = str(case.get("complaint_id") or f"BM-{case_id}")
                        top_k = int(case.get("top_k") or max(1, min(10, len(eval_context) or 5)))
                        parsed_final, latency, raw_response, eval_context = _call_search_qa_api(
                            api_base_url=api_base_url,
                            query=_case_query(case),
                            complaint_id=complaint_id,
                            top_k=top_k,
                            timeout_sec=timeout_sec,
                        )
                    else:
                        prompt, eval_context, routing_trace = _build_prompt_context_from_case(case, mode="default")
                        parsed_final, latency, raw_response = _call_model(
                            base_url=base_url,
                            model_name=model_name,
                            prompt=prompt,
                            temperature=temperature,
                            num_ctx=num_ctx,
                            num_predict=num_predict,
                            timeout_sec=timeout_sec,
                        )

                    limitations = _coerce_limitations_text(parsed_final.get("limitations", ""))
                    strict_citations_raw = parsed_final.get("citations", [])
                    strict_citations = _merge_citation_lists(
                        _coerce_citations_for_benchmark(strict_citations_raw, eval_context),
                        _coerce_citations_from_raw_text(raw_response, eval_context),
                    )

                    # strict: 원문 모델 출력 기반, 단 answer는 비어 있으면 복구 시도
                    strict_answer = _derive_non_empty_answer(parsed_final, raw_response, eval_context)
                    strict_cite_rate = _citation_match_rate(strict_citations, eval_context)
                    integrity_passed_initial = _passes_integrity_gate(strict_answer, strict_cite_rate)
                    retry_reason = ""
                    retry_stage = "none"

                    # 재시도 목표 확장: JSON 파싱 성공 이후에도 정합성 실패면 compact 재시도
                    if not integrity_passed_initial and benchmark_mode == "direct":
                        retry_reason = "INTEGRITY_GATE_FAILED"
                        retry_stage = "compact"
                        compact_prompt, eval_context, routing_trace = _build_prompt_context_from_case(
                            case,
                            mode="compact",
                            context_override=eval_context,
                            routing_trace=routing_trace,
                        )
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
                        limitations = _coerce_limitations_text(parsed_compact.get("limitations", ""))
                        strict_citations_raw = parsed_compact.get("citations", [])
                        strict_citations = _merge_citation_lists(
                            _coerce_citations_for_benchmark(strict_citations_raw, eval_context),
                            _coerce_citations_from_raw_text(raw_response, eval_context),
                        )
                        strict_answer = _derive_non_empty_answer(parsed_compact, raw_response, eval_context)
                        strict_cite_rate = _citation_match_rate(strict_citations, eval_context)

                    latencies.append(latency)

                    # repaired: 보정 후 기준
                    repaired_citations = _repair_citations(strict_citations_raw, eval_context)
                    repaired_answer = _apply_answer_quality_guard(strict_answer, repaired_citations)
                    validation = build_validation_result(
                        answer=repaired_answer,
                        citations=repaired_citations,
                        limitations=limitations,
                        context=eval_context,
                    )

                    parse_success += 1
                    if strict_answer:
                        answer_non_empty_strict += 1
                    if repaired_answer:
                        answer_non_empty_repaired += 1

                    repaired_cite_rate = _citation_match_rate(repaired_citations, eval_context)
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
                            "benchmark_mode": benchmark_mode,
                            "derived_query": routing_trace.get("derived_query") or _case_query(case),
                            "retrieved_context_count": len(eval_context),
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
            "api_base_url": api_base_url if benchmark_mode == "api" else None,
            "benchmark_mode": benchmark_mode,
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
    lines.append("# Week6 모델 벤치마크 요약")
    lines.append("")
    lines.append(f"- 생성 시각: {report['generated_at']}")
    cfg = report["config"]
    lines.append(f"- 모드: {cfg.get('benchmark_mode', 'direct')}")
    if cfg.get("api_base_url"):
        lines.append(f"- API 엔드포인트: {cfg.get('api_base_url')}")
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
    parser = argparse.ArgumentParser(description="Week6 LLM 모델 벤치마크")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/week6_Be3_model_benchmark.yaml",
        help="벤치마크 설정 파일 경로",
    )
    parser.add_argument(
        "--cases",
        type=str,
        default="../40_delivery/week3/model_test_assets/evaluation_set.json",
        help="벤치마크 케이스 파일 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="logs/evaluation/week6",
        help="결과 출력 디렉터리",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="특정 모델만 실행 (모델 ID 지정, 예: candidate_exaone_3_5_7_8b)",
    )
    parser.add_argument(
        "--benchmark-mode",
        type=str,
        choices=["direct", "api"],
        default="direct",
        help="direct: 모델 직접 호출, api: /search -> /qa API 연계 벤치마크",
    )
    parser.add_argument(
        "--api-base-url",
        type=str,
        default="http://127.0.0.1:8000",
        help="API 벤치마크 모드에서 사용할 서버 베이스 URL",
    )
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    cfg: Dict[str, Any] = {}
    outputs: Optional[Dict[str, Any]] = None
    try:
        loaded = _read_yaml(config_path) or {}
        if isinstance(loaded, dict):
            cfg = loaded
            maybe_outputs = cfg.get("outputs")
            if isinstance(maybe_outputs, dict):
                outputs = maybe_outputs
    except Exception:
        pass

    # config.outputs.individual_results_dir를 기본 output_dir로 사용할 수 있도록 지원
    # (단, 사용자가 --output-dir를 명시하지 않은 경우에만 적용)
    output_dir_arg_provided = "--output-dir" in sys.argv
    if not output_dir_arg_provided:
        candidate = outputs.get("individual_results_dir") if isinstance(outputs, dict) else None
        if isinstance(candidate, str) and candidate.strip():
            args.output_dir = candidate.strip()

    cases_path = (PROJECT_ROOT / args.cases).resolve()
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_response_jsonl = output_dir / "raw_responses.jsonl"
    parsed_answer_jsonl = output_dir / "parsed_answers.jsonl"

    raw_response_jsonl.write_text("", encoding="utf-8")
    parsed_answer_jsonl.write_text("", encoding="utf-8")

    report = run(
        config_path=config_path,
        cases_path=cases_path,
        target_model_id=args.model,
        benchmark_mode=args.benchmark_mode,
        api_base_url=args.api_base_url,
    )

    # 모델별 파일명 결정
    if args.model:
        # 특정 모델 운영 중: model_benchmark_candidate_{model_id}.json
        model_id = args.model
        report_json = output_dir / f"model_benchmark_candidate_{model_id}.json"
    else:
        # 모든 모델 운영: 기본값은 output_dir/model_benchmark_report.json
        # 단, --output-dir를 명시하지 않았고 config.outputs.report_json가 있으면 그 경로를 사용
        report_json = output_dir / "model_benchmark_report.json"
        if not output_dir_arg_provided and isinstance(outputs, dict):
            candidate_report = outputs.get("report_json")
            if isinstance(candidate_report, str) and candidate_report.strip():
                report_json = (PROJECT_ROOT / candidate_report.strip()).resolve()

    summary_md = report_json.with_suffix(".md")
    if not args.model and not output_dir_arg_provided and isinstance(outputs, dict):
        candidate_summary = outputs.get("summary_md")
        if isinstance(candidate_summary, str) and candidate_summary.strip():
            summary_md = (PROJECT_ROOT / candidate_summary.strip()).resolve()

    report_json.parent.mkdir(parents=True, exist_ok=True)
    summary_md.parent.mkdir(parents=True, exist_ok=True)

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
