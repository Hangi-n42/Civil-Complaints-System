"""Generation API 라우터"""

from __future__ import annotations

import asyncio
import json
import re
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.error_utils import error_response, make_request_id, now_iso
from app.api.schemas.generation import QARequest, QAResponse
from app.core.config import settings
from app.core.exceptions import GenerationError, RetrievalError
from app.core.logging import api_logger
from app.evaluation.civil_llm_rubric import get_civil_llm_rubric_evaluator
from app.evaluation.prometheus_feedback import (
    get_prometheus_feedback_engine,
    select_low_score_items,
)
from app.generation.context_mapper import map_retrieval_to_qa_context
from app.generation.citation.citation_mapper import get_citation_mapper
from app.generation.normalization.response_normalizer import (
    normalize_response,
    validate_unified_contract,
)
from app.generation.service import get_generation_service
from app.generation.validators.qa_response_validator import (
    build_validation_result,
    ensure_citation_tokens,
    normalize_citations,
    normalize_structured_output,
)
from app.retrieval.router.adaptive_router import (
    DEFAULT_COMPLEXITY_LEVEL,
    build_route_key,
    build_strategy_id,
    parse_route_key,
)
from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output
from app.retrieval.service import get_retrieval_service

router = APIRouter(prefix="/api/v1", tags=["generation"])

CONTRACT_VERSION = "qa-v1.1"
QA_LATENCY_WARN_MS = 8000
QA_GROUNDING_TOP_K = 5
QA_STAGE_LABELS = {
    "retrieving": "유사 사례 분석 중",
    "grounding": "관련 근거 정리 중",
    "generating": "초안 작성 중",
}
StageCallback = Callable[[str], Awaitable[None]]
NO_SIMILAR_CASE_LIMITATION = (
    "LLM 관련성 필터 적용 결과 참고할 만한 유사 민원 근거가 충분하지 않아 "
    "과거 사례 citation 없이 일반 민원 회신 원칙에 따라 작성했습니다."
)


def _derive_request_segments(query: str) -> list[str]:
    cleaned = str(query or "").strip()
    if not cleaned:
        return []

    # /search와 /qa fallback이 같은 의미 기반 요청 분해 규칙을 쓰도록 BE1 analyzer에 위임한다.
    try:
        output = build_analyzer_output(cleaned, "general")
        segments = output.get("request_segments")
    except Exception:
        segments = None

    if isinstance(segments, list):
        normalized = [str(item or "").strip() for item in segments if str(item or "").strip()]
        if normalized:
            return normalized
    return [cleaned]


def _is_strategy_consistent(strategy_id: str, route_key: str) -> bool:
    topic, complexity = parse_route_key(route_key)
    expected = build_strategy_id(topic, complexity)
    return strategy_id == expected


def _normalize_route_key(route_key: str) -> str:
    topic, complexity = parse_route_key(route_key)
    return build_route_key(topic, complexity)


def _validate_week6_qa_request(request: QARequest) -> str | None:
    if not str(request.complaint_id or "").strip():
        return "complaint_id is required"
    if not request.query.strip():
        return "query is required"
    if request.routing_hint is None:
        return "routing_hint is required"

    if not str(request.routing_hint.strategy_id or "").strip():
        return "routing_hint.strategy_id is required"
    if not str(request.routing_hint.route_key or "").strip():
        return "routing_hint.route_key is required"
    if "/" not in request.routing_hint.route_key:
        return "routing_hint.route_key must contain topic/complexity format"

    normalized_route_key = _normalize_route_key(request.routing_hint.route_key)
    if request.routing_hint.route_key.count("/") != 1:
        return "routing_hint.route_key must contain exactly one slash (topic/complexity)"

    if not _is_strategy_consistent(
        request.routing_hint.strategy_id,
        normalized_route_key,
    ):
        return "routing_hint.strategy_id and routing_hint.route_key are inconsistent"
    if request.routing_hint.top_k < 1:
        return "routing_hint.top_k must be >= 1"
    if request.routing_hint.snippet_max_chars < 120:
        return "routing_hint.snippet_max_chars must be >= 120"
    return None


def _build_trace_from_route_key(route_key: str, query: str) -> dict:
    topic_type, complexity_level = parse_route_key(route_key)
    try:
        analyzer_output = build_analyzer_output(query, topic_type)
    except Exception:
        analyzer_output = {}

    if complexity_level == "high":
        complexity_score = 0.8
    elif complexity_level == "low":
        complexity_score = 0.3
    else:
        complexity_score = 0.55

    return {
        "topic_type": topic_type,
        "complexity_level": complexity_level,
        "complexity_score": float(analyzer_output.get("complexity_score") or complexity_score),
        "request_segments": analyzer_output.get("request_segments") or _derive_request_segments(query),
        "complexity_trace": analyzer_output.get("complexity_trace")
        or {
            "intent_count": 1,
            "constraint_count": 0,
            "entity_diversity": 1,
            "policy_reference_count": 0,
            "cross_sentence_dependency": False,
        },
        "route_reason": "search 단계 routing_hint 값을 그대로 계승했습니다.",
    }


def _log_error(
    *,
    endpoint: str,
    request_id: str,
    error_code: str,
    retryable: bool,
    took_ms: int,
    message: str,
) -> None:
    api_logger.error(
        "api_error endpoint=%s request_id=%s error_code=%s retryable=%s latency_ms=%s message=%s",
        endpoint,
        request_id,
        error_code,
        retryable,
        took_ms,
        message,
    )


def _log_success(*, endpoint: str, request_id: str, took_ms: int, retrieved_count: int) -> None:
    api_logger.info(
        "api_success endpoint=%s request_id=%s latency_ms=%s retrieved_count=%s",
        endpoint,
        request_id,
        took_ms,
        retrieved_count,
    )

    if took_ms > QA_LATENCY_WARN_MS:
        api_logger.warning(
            "api_perf_warning endpoint=%s request_id=%s code=PERF_LATENCY_THRESHOLD_EXCEEDED latency_ms=%s threshold_ms=%s",
            endpoint,
            request_id,
            took_ms,
            QA_LATENCY_WARN_MS,
        )


def _compose_answer_from_payload(result: dict, citations: list[dict]) -> str:
    """모델 answer가 비거나 템플릿 문구일 때 공문형 최소 답변을 합성한다."""
    raw_answer = str(result.get("answer", "") or "").strip()
    fallback_marker = "본문이 비어 있어 요약 문장을 제공하지 못했습니다"
    if raw_answer and fallback_marker not in raw_answer:
        return raw_answer

    structured = result.get("structured_output") if isinstance(result.get("structured_output"), dict) else {}
    summary = str(structured.get("summary", "") or "").strip()
    actions = structured.get("action_items") if isinstance(structured.get("action_items"), list) else []
    actions = [str(item).strip() for item in actions if str(item).strip()]

    action_phrase = ", ".join(actions[:3]) if actions else "현황 확인, 관계기관/운수업체 협의, 개선방안 검토"

    # 공문형(민원회신) 기본 뼈대
    parts: list[str] = [
        "1. 우리 시 시정 발전에 관심을 두셔서 감사드리며, 귀 가정의 건강과 행복을 기원합니다.",
    ]
    if summary:
        parts.append(f"\n2. 귀하의 민원 내용은 \"{summary}\"에 관한 것으로 이해됩니다.")
    else:
        parts.append("\n2. 귀하의 민원 내용은 관련 불편사항 개선 요청에 관한 것으로 이해됩니다.")

    parts.append("\n3. 귀하의 질의 사항에 대한 검토 의견은 다음과 같습니다.")
    parts.append(f"\n   가. 관계 부서에서 사실관계 및 현황을 확인하겠습니다.")
    parts.append(f"\n   나. 우선 조치/검토 사항: {action_phrase}.")
    parts.append("\n   다. 일정 기간 모니터링 및 협의를 통해 불편이 최소화되도록 지속 점검하겠습니다.")
    parts.append("\n\n4. 추가 설명이 필요하시면 성남시 해당 업무 담당부서로 문의해 주시면 안내드리겠습니다. 감사합니다.")

    return "".join(parts).strip()


def _build_no_similar_case_answer(query: str) -> str:
    """유사 사례가 없을 때 citation 없이 제공하는 최소 회신문."""
    cleaned_query = str(query or "").strip()
    if cleaned_query:
        understood = f'귀하의 민원 내용은 "{cleaned_query}"에 관한 사항으로 이해됩니다.'
    else:
        understood = "귀하의 민원 내용은 접수된 불편사항에 대한 검토 요청으로 이해됩니다."

    return (
        "1. 우리 시 시정 발전에 관심을 두셔서 감사드리며, 귀 가정의 건강과 행복을 기원합니다.\n\n"
        f"2. {understood}\n\n"
        "3. 현재 검색된 과거 민원 중 답변 근거로 삼을 만큼 충분히 유사한 사례는 확인되지 않았습니다. "
        "따라서 담당부서에서는 접수 내용의 사실관계, 현장 여건, 관련 법령 및 내부 처리 기준을 우선 확인한 뒤 "
        "조치 가능 여부와 처리 방향을 안내드릴 예정입니다.\n\n"
        "4. 추가 설명이 필요하시면 해당 업무 담당부서로 문의해 주시면 세부 검토 절차를 안내해 드리겠습니다. 감사합니다."
    )


def _build_no_similar_case_payload(
    *,
    request: QARequest,
    route_key: str,
    strategy_id: str,
    routing_trace: dict,
    retrieval_elapsed_ms: int,
) -> dict:
    request_segments = routing_trace.get("request_segments") or _derive_request_segments(request.query)
    return normalize_response(
        {
            "complaint_id": request.complaint_id,
            "strategy_id": strategy_id,
            "route_key": route_key,
            "routing_trace": routing_trace,
            "structured_output": {
                "summary": str(request.query).strip(),
                "action_items": [
                    "담당부서 사실관계 확인",
                    "관련 법령 및 처리 기준 검토",
                    "검토 결과와 후속 절차 안내",
                ],
                "request_segments": request_segments,
            },
            "answer": _build_no_similar_case_answer(request.query),
            "citations": [],
            "limitations": [NO_SIMILAR_CASE_LIMITATION],
            "latency_ms": {
                "analyzer": 0,
                "router": 0,
                "retrieval": retrieval_elapsed_ms,
                "generation": 0,
            },
            "quality_signals": {
                "citation_coverage": 0.0,
                "hallucination_flag": False,
                "segment_coverage": 1.0 if request_segments else 0.0,
            },
            "generation_metadata": {
                "fallback_used": True,
                "parse_retry_count": 0,
                "grounding_evidence_count": 0,
                "citation_count": 0,
                "generation_mode": "no_evidence_fallback",
            },
        }
    )


async def _apply_qa_grounding_filter(
    *,
    retrieval_service,
    query: str,
    raw_context: list[dict],
    top_k: int,
    query_signals: dict | None = None,
) -> list[dict]:
    """QA 답변 grounding에 쓰기 전 참고 선례를 BE2 LLM 필터로 정밀화한다."""
    if not raw_context:
        return []

    normalize_signals = getattr(retrieval_service, "_normalize_query_signals", None)
    apply_soft_rerank = getattr(retrieval_service, "_apply_metadata_soft_rerank", None)
    if query_signals and callable(normalize_signals) and callable(apply_soft_rerank):
        raw_context = apply_soft_rerank(raw_context, normalize_signals(query_signals))

    apply_filter = getattr(retrieval_service, "_apply_grounding_filter", None)
    if apply_filter is None:
        return raw_context[:top_k]

    return await apply_filter(query, raw_context, top_k)


def _citation_coverage(citation_count: int, mismatch_count: int) -> float:
    """Return the share of citations verified against retrieval context.

    Citation markers are intentionally absent from the public answer, so coverage
    is based on evidence validity rather than answer-token counting.
    """
    if citation_count <= 0:
        return 0.0
    valid_count = max(0, citation_count - max(0, mismatch_count))
    return round(min(1.0, valid_count / citation_count), 4)


async def _attach_civil_llm_rubric(
    *,
    unified_payload: dict,
    request: QARequest,
    references: list[dict],
    generation_service,
    citation_validation: dict | None = None,
    query_signals: dict | None = None,
) -> dict | None:
    """Attach runtime Civil Complaint LLM-Rubric report to the QA payload."""
    if not settings.ENABLE_CIVIL_LLM_RUBRIC:
        return None

    generation_metadata = (
        unified_payload.get("generation_metadata")
        if isinstance(unified_payload.get("generation_metadata"), dict)
        else {}
    )
    quality_signals = (
        unified_payload.get("quality_signals")
        if isinstance(unified_payload.get("quality_signals"), dict)
        else {}
    )
    llm_call = (
        getattr(generation_service, "call_ollama", None)
        if settings.CIVIL_LLM_RUBRIC_USE_LLM_JUDGE
        else None
    )

    try:
        rubric_result = await get_civil_llm_rubric_evaluator().evaluate(
            case_id=str(request.complaint_id or ""),
            complaint_text=request.query,
            generated_answer=str(unified_payload.get("answer") or ""),
            references=references,
            citations=unified_payload.get("citations")
            if isinstance(unified_payload.get("citations"), list)
            else [],
            routing_trace=unified_payload.get("routing_trace")
            if isinstance(unified_payload.get("routing_trace"), dict)
            else {},
            quality_signals=quality_signals,
            citation_validation=citation_validation or {},
            legal_citations=unified_payload.get("legal_citations")
            if isinstance(unified_payload.get("legal_citations"), list)
            else [],
            legal_citation_warnings=unified_payload.get("legal_citation_warnings")
            if isinstance(unified_payload.get("legal_citation_warnings"), list)
            else [],
            query_signals=query_signals,
            generation_metadata=generation_metadata,
            llm_call=llm_call if callable(llm_call) else None,
        )
    except Exception as exc:  # noqa: BLE001
        api_logger.warning(
            "civil_llm_rubric_failed request_id=%s error=%s",
            str(request.request_id or ""),
            str(exc),
        )
        rubric_result = {
            "case_id": str(request.complaint_id or ""),
            "rubric_version": settings.CIVIL_LLM_RUBRIC_VERSION,
            "judge_prompt_version": settings.CIVIL_LLM_RUBRIC_JUDGE_PROMPT_VERSION,
            "judge_status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "diagnostics": {
                "main_failure_reasons": ["rubric_runtime_error"],
                "recommended_fix": ["런타임 평가기 오류 로그를 확인해야 합니다."],
                "human_review_required": True,
            },
        }

    generation_metadata = dict(generation_metadata)
    generation_metadata["civil_llm_rubric"] = rubric_result
    unified_payload["generation_metadata"] = generation_metadata

    safety_layer = (
        rubric_result.get("safety_layer")
        if isinstance(rubric_result.get("safety_layer"), dict)
        else {}
    )
    diagnostics = (
        rubric_result.get("diagnostics")
        if isinstance(rubric_result.get("diagnostics"), dict)
        else {}
    )
    quality_signals = dict(quality_signals)
    quality_signals["civil_llm_rubric_q0"] = safety_layer.get(
        "final_q0_score_0_10"
    )
    quality_signals["civil_llm_rubric_human_review_required"] = bool(
        diagnostics.get("human_review_required", False)
    )
    quality_signals["civil_llm_rubric_judge_status"] = str(
        rubric_result.get("judge_status") or "unknown"
    )
    unified_payload["quality_signals"] = quality_signals
    return rubric_result


async def _parse_prometheus_revision_response(
    *,
    generation_service,
    response_text: str,
    context: list[dict],
) -> dict:
    parser = getattr(generation_service, "parse_json_response_relaxed", None)
    if callable(parser):
        return await parser(response_text, context)

    payload = json.loads(str(response_text or "").strip())
    if not isinstance(payload, dict):
        raise ValueError("Prometheus revision response must be a JSON object")
    return payload


async def _maybe_apply_prometheus_revision(
    *,
    unified_payload: dict,
    request: QARequest,
    generation_service,
    context: list[dict],
    current_citations: list,
    retrieval_elapsed_ms: int,
    generation_elapsed_ms: int,
    routing_trace: dict,
    strategy_id: str,
    route_key: str,
    query_signals: dict | None,
) -> dict | None:
    if (
        not settings.ENABLE_PROMETHEUS_RUBRIC_FEEDBACK
        or settings.PROMETHEUS_RUBRIC_MAX_REGENERATION_ATTEMPTS <= 0
    ):
        return None

    generation_metadata = (
        unified_payload.get("generation_metadata")
        if isinstance(unified_payload.get("generation_metadata"), dict)
        else {}
    )
    initial_rubric = generation_metadata.get("civil_llm_rubric")
    if not isinstance(initial_rubric, dict):
        return None

    low_items = select_low_score_items(
        initial_rubric,
        threshold_1_4=settings.PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE,
    )
    if not low_items:
        return None

    llm_call = getattr(generation_service, "call_ollama", None)
    if not callable(llm_call):
        return None

    engine = get_prometheus_feedback_engine()
    revision_summary = {
        "attempted": True,
        "applied": False,
        "attempt_count": 1,
        "trigger_threshold_1_4": settings.PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE,
        "initial_low_score_items": low_items,
        "initial_q0_final": (
            initial_rubric.get("safety_layer", {}).get("final_q0_score_0_10")
            if isinstance(initial_rubric.get("safety_layer"), dict)
            else None
        ),
    }

    try:
        prometheus_feedback = await engine.build_feedback(
            case_id=str(request.complaint_id or ""),
            complaint_text=request.query,
            generated_answer=str(unified_payload.get("answer") or ""),
            references=context,
            citations=unified_payload.get("citations")
            if isinstance(unified_payload.get("citations"), list)
            else [],
            rubric_result=initial_rubric,
            llm_call=llm_call,
        )
        if not prometheus_feedback.get("triggered"):
            return None

        revision_prompt = engine.build_revision_prompt(
            complaint_text=request.query,
            current_answer=str(unified_payload.get("answer") or ""),
            references=context,
            citations=unified_payload.get("citations")
            if isinstance(unified_payload.get("citations"), list)
            else [],
            prometheus_feedback=prometheus_feedback,
        )
        revision_start = perf_counter()
        response_text = await llm_call(
            revision_prompt,
            temperature=settings.PROMETHEUS_RUBRIC_TEMPERATURE,
            response_schema=engine.revision_schema(),
        )
        revised_result = await _parse_prometheus_revision_response(
            generation_service=generation_service,
            response_text=response_text,
            context=context,
        )
        generation_elapsed_ms += int((perf_counter() - revision_start) * 1000)
    except Exception as exc:  # noqa: BLE001
        revision_summary["error"] = f"{type(exc).__name__}: {exc}"
        _store_prometheus_revision_metadata(
            unified_payload=unified_payload,
            prometheus_feedback={
                "triggered": True,
                "source": "prometheus_error",
                "low_score_items": low_items,
                "error": revision_summary["error"],
            },
            revision_summary=revision_summary,
        )
        api_logger.warning(
            "prometheus_revision_failed request_id=%s error=%s",
            str(request.request_id or ""),
            revision_summary["error"],
        )
        return None

    revised_citations = normalize_citations(
        revised_result.get("citations") or current_citations,
        context=context,
    )
    revised_answer = ensure_citation_tokens(
        _compose_answer_from_payload(revised_result, revised_citations),
        citations=revised_citations,
        complaint=request.query,
        context=context,
    )
    revised_limitations = (
        str(revised_result.get("limitations") or "").strip()
        or "Prometheus-style 피드백을 반영해 재작성한 답변입니다."
    )
    revised_validation = build_validation_result(
        answer=revised_answer,
        citations=revised_citations,
        limitations=revised_limitations,
        context=context,
        complaint=request.query,
    )
    if not revised_validation["is_valid"]:
        revision_summary["error"] = "revised_answer_validation_failed"
        revision_summary["validation_errors"] = revised_validation.get("errors", [])
        _store_prometheus_revision_metadata(
            unified_payload=unified_payload,
            prometheus_feedback=prometheus_feedback,
            revision_summary=revision_summary,
        )
        return None

    citation_mapper = get_citation_mapper()
    revised_is_valid, revised_mismatch_count, revised_mismatch_details = (
        citation_mapper.validate_citations_against_context(
            citations=[
                c.model_dump() if hasattr(c, "model_dump") else c
                for c in revised_citations
            ],
            retrieval_context=context,
        )
    )
    response_citations = []
    for item in revised_citations:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        response_citations.append(
            {
                "doc_id": str(item.get("doc_id") or item.get("case_id") or ""),
                "source": str(item.get("source") or "retrieval"),
                "quote": str(item.get("snippet") or ""),
            }
        )

    revised_structured = normalize_structured_output(
        revised_result.get("structured_output"),
        request_segments=routing_trace.get("request_segments") or [],
    )
    next_generation_metadata = dict(generation_metadata)
    next_generation_metadata.pop("civil_llm_rubric", None)
    revision_summary.update(
        {
            "applied": True,
            "feedback_source": prometheus_feedback.get("source"),
            "revision_model": str(getattr(generation_service, "model", "") or ""),
        }
    )
    next_generation_metadata["prometheus_revision"] = revision_summary

    revised_payload = normalize_response(
        {
            "complaint_id": request.complaint_id,
            "strategy_id": strategy_id,
            "route_key": route_key,
            "routing_trace": routing_trace,
            "structured_output": {
                "summary": revised_structured.get("summary", ""),
                "action_items": revised_structured.get("action_items", []),
                "request_segments": revised_structured.get("request_segments", []),
            },
            "answer": revised_answer,
            "citations": response_citations,
            "legal_citations": unified_payload.get("legal_citations", []),
            "legal_citation_warnings": unified_payload.get(
                "legal_citation_warnings",
                [],
            ),
            "limitations": [revised_limitations],
            "latency_ms": {
                "analyzer": 0,
                "router": 0,
                "retrieval": retrieval_elapsed_ms,
                "generation": generation_elapsed_ms,
            },
            "quality_signals": {
                "citation_coverage": _citation_coverage(
                    len(response_citations),
                    revised_mismatch_count,
                ),
                "hallucination_flag": (
                    not revised_is_valid
                    or bool(unified_payload.get("legal_citation_warnings"))
                ),
                "segment_coverage": _segment_coverage(
                    revised_answer,
                    routing_trace.get("request_segments") or [],
                ),
            },
            "generation_metadata": next_generation_metadata,
        }
    )
    final_rubric = await _attach_civil_llm_rubric(
        unified_payload=revised_payload,
        request=request,
        references=context,
        generation_service=generation_service,
        citation_validation={
            "is_valid": revised_is_valid,
            "mismatch_count": revised_mismatch_count,
            "details": {"mismatches": revised_mismatch_details},
        },
        query_signals=query_signals,
    )
    if isinstance(final_rubric, dict):
        revision_summary["final_q0_final"] = (
            final_rubric.get("safety_layer", {}).get("final_q0_score_0_10")
            if isinstance(final_rubric.get("safety_layer"), dict)
            else None
        )
        final_rubric["prometheus_feedback"] = prometheus_feedback
        final_rubric["prometheus_revision"] = revision_summary
        revised_payload["generation_metadata"]["civil_llm_rubric"] = final_rubric
        revised_payload["generation_metadata"]["prometheus_revision"] = revision_summary

    return {
        "payload": revised_payload,
        "qa_validation": revised_validation,
        "citation_validation": {
            "is_valid": revised_is_valid,
            "mismatch_count": revised_mismatch_count,
            "details": {"mismatches": revised_mismatch_details},
        },
    }


def _store_prometheus_revision_metadata(
    *,
    unified_payload: dict,
    prometheus_feedback: dict,
    revision_summary: dict,
) -> None:
    generation_metadata = (
        unified_payload.get("generation_metadata")
        if isinstance(unified_payload.get("generation_metadata"), dict)
        else {}
    )
    generation_metadata = dict(generation_metadata)
    generation_metadata["prometheus_revision"] = revision_summary
    rubric = generation_metadata.get("civil_llm_rubric")
    if isinstance(rubric, dict):
        rubric["prometheus_feedback"] = prometheus_feedback
        rubric["prometheus_revision"] = revision_summary
        generation_metadata["civil_llm_rubric"] = rubric
    unified_payload["generation_metadata"] = generation_metadata


def _segment_coverage(answer: str, request_segments: list[str]) -> float:
    segments = [str(item).strip() for item in request_segments if str(item).strip()]
    if not segments:
        return 0.0
    normalized_answer = " ".join(str(answer or "").casefold().split())
    covered = 0
    for segment in segments:
        terms = [
            token
            for token in re.findall(r"[0-9a-zA-Z가-힣]{2,}", segment.casefold())
            if token not in {"민원", "요청", "문의"}
        ]
        if terms and any(term in normalized_answer for term in terms):
            covered += 1
    return round(covered / len(segments), 4)


async def _emit_stage(
    stage_callback: StageCallback | None,
    stage: str,
) -> None:
    if stage_callback is not None:
        await stage_callback(stage)


async def _generate_qa(
    request: QARequest,
    response: Response,
    stage_callback: StageCallback | None = None,
) -> QAResponse | JSONResponse:
    """검색 결과 기반 RAG QA 응답을 생성한다."""
    request_id = str(request.request_id or "").strip() or make_request_id()
    start = perf_counter()
    response.headers["X-Contract-Version"] = CONTRACT_VERSION

    validation_message = _validate_week6_qa_request(request)
    if validation_message:
        took_ms = int((perf_counter() - start) * 1000)
        error_code = (
            "ROUTING_STRATEGY_INCONSISTENT"
            if "inconsistent" in validation_message
            else "VALIDATION_ERROR"
        )
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code=error_code,
            retryable=False,
            took_ms=took_ms,
            message=validation_message,
        )
        return error_response(
            request_id=request_id,
            error_code=error_code,
            message=validation_message,
            status_code=400,
            retryable=False,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    await _emit_stage(stage_callback, "retrieving")
    retrieval_service = get_retrieval_service()
    generation_service = get_generation_service()
    query_signals = (
        request.query_signals.model_dump(exclude_none=True)
        if request.query_signals is not None
        else None
    )

    try:
        retrieval_start = perf_counter()
        effective_top_k = request.routing_hint.top_k if request.routing_hint else request.top_k
        grounding_top_k = max(1, min(QA_GROUNDING_TOP_K, int(effective_top_k)))
        if request.use_search_results and request.search_results:
            raw_context = [item.model_dump() for item in request.search_results]
            raw_context = await _apply_qa_grounding_filter(
                retrieval_service=retrieval_service,
                query=request.query,
                raw_context=raw_context,
                top_k=grounding_top_k,
                query_signals=query_signals,
            )
        else:
            filters = request.filters.model_dump(exclude_none=True) if request.filters else {}
            raw_context = await retrieval_service.search(
                query=request.query,
                top_k=grounding_top_k,
                filters=filters,
                grounding_filter=True,
                grounding_pool=max(5, grounding_top_k),
                query_signals=query_signals,
            )
        retrieval_elapsed_ms = int((perf_counter() - retrieval_start) * 1000)
        # retrieval 단계 종료 경계 — FE retrieving 단계/BE3 SSE가 쓸 실제 완료 신호 (#375)
        retrieval_completed_at = now_iso()
        await _emit_stage(stage_callback, "grounding")
    except RetrievalError as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            retryable=True,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INDEX_NOT_READY",
            message="검색 인덱스가 준비되지 않았습니다. 인덱싱 후 다시 시도해주세요.",
            retryable=True,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            retryable=False,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="검색 단계에서 예기치 못한 오류가 발생했습니다.",
            retryable=False,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    context_policy = (
        request.context_window_policy.model_dump()
        if request.context_window_policy
        else None
    )
    context, _context_trace = map_retrieval_to_qa_context(
        retrieval_results=raw_context,
        top_k=grounding_top_k,
        policy=context_policy,
    )

    grounded_result_count = len(raw_context)
    if not context:
        took_ms = int((perf_counter() - start) * 1000)
        if (
            request.use_search_results
            and request.search_results
            and grounded_result_count > 0
        ):
            _log_error(
                endpoint="/api/v1/qa",
                request_id=request_id,
                error_code="BAD_REQUEST",
                retryable=False,
                took_ms=took_ms,
                message="QA 컨텍스트를 구성할 수 없습니다. search_results 형식을 확인해주세요.",
            )
            return error_response(
                request_id=request_id,
                error_code="BAD_REQUEST",
                message="QA 컨텍스트를 구성할 수 없습니다. search_results 형식을 확인해주세요.",
                retryable=False,
                details={"hint": "chunk_id/case_id/snippet이 포함되어야 합니다."},
                headers={"X-Contract-Version": CONTRACT_VERSION},
            )

        route_key = (
            _normalize_route_key(request.routing_hint.route_key)
            if request.routing_hint
            else f"general/{DEFAULT_COMPLEXITY_LEVEL}"
        )
        strategy_id = (
            request.routing_hint.strategy_id
            if request.routing_hint
            else build_strategy_id("general", DEFAULT_COMPLEXITY_LEVEL)
        )
        routing_trace = (
            request.routing_trace.model_dump()
            if request.routing_trace is not None
            else _build_trace_from_route_key(route_key, request.query)
        )
        unified_payload = _build_no_similar_case_payload(
            request=request,
            route_key=route_key,
            strategy_id=strategy_id,
            routing_trace=routing_trace,
            retrieval_elapsed_ms=retrieval_elapsed_ms,
        )
        await _attach_civil_llm_rubric(
            unified_payload=unified_payload,
            request=request,
            references=[],
            generation_service=generation_service,
            citation_validation={"is_valid": False, "mismatch_count": 0},
            query_signals=query_signals,
        )
        contract_missing = validate_unified_contract(unified_payload)
        if contract_missing:
            return error_response(
                request_id=request_id,
                error_code="RESPONSE_SCHEMA_MISMATCH",
                message="/qa no-evidence fallback response contract validation failed",
                status_code=500,
                retryable=False,
                details={"missing_fields": contract_missing},
                headers={"X-Contract-Version": CONTRACT_VERSION},
            )

        api_logger.info(
            "qa_no_similar_case_fallback endpoint=%s request_id=%s latency_ms=%s grounding_filter=%s",
            "/api/v1/qa",
            request_id,
            took_ms,
            True,
        )
        return QAResponse(
            success=True,
            request_id=request_id,
            timestamp=now_iso(),
            data=unified_payload,
            search_trace={
                "used_top_k": grounding_top_k,
                "retrieved_count": 0,
                "retrieval_done": True,
                "retrieval_completed_at": retrieval_completed_at,
            },
        )

    try:
        await _emit_stage(stage_callback, "generating")
        generation_start = perf_counter()
        route_key = _normalize_route_key(request.routing_hint.route_key) if request.routing_hint else f"general/{DEFAULT_COMPLEXITY_LEVEL}"
        routing_trace = (
            request.routing_trace.model_dump()
            if request.routing_trace is not None
            else _build_trace_from_route_key(route_key, request.query)
        )
        result = await generation_service.generate_qa(
            query=request.query,
            context=context,
            routing_trace=routing_trace,
            query_signals=query_signals,
        )
        generation_elapsed_ms = int((perf_counter() - generation_start) * 1000)
    except GenerationError as e:
        error_code = getattr(e, "code", "PROCESSING_ERROR")
        retryable = bool(getattr(e, "retryable", True))
        details = getattr(e, "details", None) or {}
        upstream_status = getattr(e, "upstream_status", None)
        message = str(e)

        # 제너릭 PROCESSING_ERROR를 더 구체적인 코드로 분류
        if error_code == "PROCESSING_ERROR":
            upper = message.upper()
            if "TIMEOUT" in upper:
                error_code = "MODEL_TIMEOUT"
                message = "응답 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            elif "OOM" in upper:
                error_code = "OOM_DETECTED"
                message = "메모리 용량 초과로 답변 생성이 중단되었습니다. 검색 범위를 줄여 다시 시도해주세요."
            elif "JSON" in upper:
                error_code = "PARSE_JSON_DECODE_ERROR"
                message = "모델 응답을 JSON으로 파싱하지 못했습니다."

        if error_code == "PARSE_RETRY_EXHAUSTED" and not message.strip():
            message = "모델 응답을 JSON으로 안정적으로 파싱하지 못했습니다."
        
        # PARSE_RETRY_EXHAUSTED를 Week 4 표준 에러코드 QA_PARSE_ERROR로 변환
        if error_code == "PARSE_RETRY_EXHAUSTED":
            error_code = "QA_PARSE_ERROR"
            message = "JSON 파싱 실패 (재시도 정책 모두 소진)"

        # upstream_status를 details에 포함
        if upstream_status is not None:
            details["upstream_status"] = upstream_status

        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code=error_code,
            retryable=retryable,
            took_ms=took_ms,
            message=message,
        )

        return error_response(
            request_id=request_id,
            error_code=error_code,
            message=message,
            retryable=retryable,
            details=details,
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )
    except Exception as e:
        took_ms = int((perf_counter() - start) * 1000)
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            retryable=False,
            took_ms=took_ms,
            message=str(e),
        )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="생성 단계에서 예기치 못한 오류가 발생했습니다.",
            retryable=False,
            details={"reason": str(e)},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    took_ms = int((perf_counter() - start) * 1000)
    raw_generation_answer_empty = not str(result.get("answer", "") or "").strip()
    citations = normalize_citations(result.get("citations", []), context=context)
    answer = ensure_citation_tokens(
        _compose_answer_from_payload(result, citations),
        citations=citations,
        complaint=request.query,
        context=context,
    )
    limitations = str(result.get("limitations", "")).strip() or "검색 범위 내 데이터에 기반한 답변입니다."
    generation_metadata = dict(
        result.get("generation_metadata")
        if isinstance(result.get("generation_metadata"), dict)
        else {}
    )
    generation_metadata.update(
        {
            "grounding_evidence_count": len(context),
            "citation_count": len(citations),
        }
    )
    if raw_generation_answer_empty:
        generation_metadata.update(
            {
                "fallback_used": True,
                "generation_mode": "api_answer_fallback",
            }
        )
        limitations = (
            f"{limitations} 생성 결과의 answer가 비어 API 안전 폴백 답변으로 대체했습니다."
        )
        api_logger.warning(
            "qa_empty_answer_fallback request_id=%s parse_retry_count=%s",
            request_id,
            generation_metadata.get("parse_retry_count", 0),
        )
    validation = build_validation_result(
        answer=answer,
        citations=citations,
        limitations=limitations,
        context=context,
        complaint=request.query,
    )

    if not validation["is_valid"]:
        _log_error(
            endpoint="/api/v1/qa",
            request_id=request_id,
            error_code="PARSE_SCHEMA_MISMATCH",
            retryable=False,
            took_ms=took_ms,
            message="생성 응답 검증에 실패했습니다.",
        )
        return error_response(
            request_id=request_id,
            error_code="PARSE_SCHEMA_MISMATCH",
            message="생성 응답 검증에 실패했습니다.",
            retryable=False,
            details={"validation_errors": validation["errors"]},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    _log_success(
        endpoint="/api/v1/qa",
        request_id=request_id,
        took_ms=took_ms,
        retrieved_count=len(context),
    )

    # Citation 정합성 검증
    citation_mapper = get_citation_mapper()
    is_valid, mismatch_count, mismatch_details = citation_mapper.validate_citations_against_context(
        citations=[c.model_dump() if hasattr(c, 'model_dump') else c for c in citations],
        retrieval_context=context,
    )

    if not is_valid:
        api_logger.warning(
            "citation_validation_failed request_id=%s mismatch_count=%d",
            request_id,
            mismatch_count,
        )

    response_citations = []
    for item in citations:
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        response_citations.append(
            {
                "doc_id": str(item.get("doc_id") or item.get("case_id") or ""),
                "source": str(item.get("source") or "retrieval"),
                "quote": str(item.get("snippet") or ""),
            }
        )

    route_key = _normalize_route_key(request.routing_hint.route_key) if request.routing_hint else f"general/{DEFAULT_COMPLEXITY_LEVEL}"
    strategy_id = request.routing_hint.strategy_id if request.routing_hint else build_strategy_id("general", DEFAULT_COMPLEXITY_LEVEL)
    routing_trace = (
        request.routing_trace.model_dump()
        if request.routing_trace is not None
        else _build_trace_from_route_key(route_key, request.query)
    )

    request_segments = routing_trace.get("request_segments") or []
    generated_structured = normalize_structured_output(
        result.get("structured_output"),
        request_segments=request_segments,
    )
    legal_warnings = result.get("legal_citation_warnings", [])
    answer_warning_codes = [
        str(item.get("code") or "")
        for item in validation.get("warnings", [])
        if isinstance(item, dict) and str(item.get("code") or "").strip()
    ]
    safety_warning_codes = {
        "ANSWER_REQUEST_MISMATCH",
        "PRECEDENT_FACT_LEAKAGE_RISK",
        "UNSUPPORTED_COMMITMENT_RISK",
        "UNVERIFIED_FACT_RISK",
        "CONTEXT_CONSTRAINT_CONFLICT",
    }
    hallucination_flag = (
        (not is_valid)
        or bool(legal_warnings)
        or any(code in safety_warning_codes for code in answer_warning_codes)
    )
    generation_metadata["answer_quality_warning_codes"] = answer_warning_codes
    unified_payload = normalize_response(
        {
            "complaint_id": request.complaint_id,
            "strategy_id": strategy_id,
            "route_key": route_key,
            "routing_trace": routing_trace,
            "structured_output": {
                "summary": generated_structured.get("summary", ""),
                "action_items": generated_structured.get("action_items", []),
                "request_segments": generated_structured.get("request_segments", []),
            },
            "answer": answer,
            "citations": response_citations,
            "legal_citations": result.get("legal_citations", []),
            "legal_citation_warnings": result.get(
                "legal_citation_warnings",
                [],
            ),
            "limitations": [limitations],
            "latency_ms": {
                "analyzer": 0,
                "router": 0,
                "retrieval": retrieval_elapsed_ms,
                "generation": generation_elapsed_ms,
            },
            "quality_signals": {
                "citation_coverage": _citation_coverage(
                    len(response_citations),
                    mismatch_count,
                ),
                "hallucination_flag": hallucination_flag,
                "segment_coverage": _segment_coverage(answer, request_segments),
            },
            "generation_metadata": generation_metadata or {
                "fallback_used": False,
                "parse_retry_count": 0,
                "grounding_evidence_count": len(context),
                "citation_count": len(response_citations),
                "generation_mode": "default",
            },
        }
    )
    await _attach_civil_llm_rubric(
        unified_payload=unified_payload,
        request=request,
        references=context,
        generation_service=generation_service,
        citation_validation={
            "is_valid": is_valid,
            "mismatch_count": mismatch_count,
            "details": {"mismatches": mismatch_details},
        },
        query_signals=query_signals,
    )
    prometheus_revision_result = await _maybe_apply_prometheus_revision(
        unified_payload=unified_payload,
        request=request,
        generation_service=generation_service,
        context=context,
        current_citations=citations,
        retrieval_elapsed_ms=retrieval_elapsed_ms,
        generation_elapsed_ms=generation_elapsed_ms,
        routing_trace=routing_trace,
        strategy_id=strategy_id,
        route_key=route_key,
        query_signals=query_signals,
    )
    if prometheus_revision_result is not None:
        unified_payload = prometheus_revision_result["payload"]
        validation = prometheus_revision_result["qa_validation"]
        citation_result = prometheus_revision_result["citation_validation"]
        is_valid = bool(citation_result["is_valid"])
        mismatch_count = int(citation_result["mismatch_count"])
        mismatch_details = citation_result.get("details", {}).get("mismatches", [])

    contract_missing = validate_unified_contract(unified_payload)
    if contract_missing:
        return error_response(
            request_id=request_id,
            error_code="RESPONSE_SCHEMA_MISMATCH",
            message="/qa unified response contract validation failed",
            status_code=500,
            retryable=False,
            details={"missing_fields": contract_missing},
            headers={"X-Contract-Version": CONTRACT_VERSION},
        )

    return QAResponse(
        success=True,
        request_id=request_id,
        timestamp=now_iso(),
        data=unified_payload,
        qa_validation=validation,
        search_trace={
            "used_top_k": grounding_top_k,
            "retrieved_count": len(context),
            "context_budget_chars": _context_trace.get("context_budget_chars"),
            "context_used_chars": _context_trace.get("context_used_chars"),
            "context_truncated_count": _context_trace.get("truncated_count"),
            "context_dropped_count": _context_trace.get("dropped_count"),
            "retrieval_done": True,
            "retrieval_completed_at": retrieval_completed_at,
        },
        citation_validation={
            "is_valid": is_valid,
            "mismatch_count": mismatch_count,
            "details": {"mismatches": mismatch_details},
        },
    )


@router.post("/qa", response_model=QAResponse)
async def generate_qa(request: QARequest, response: Response) -> QAResponse | JSONResponse:
    """검색 결과 기반 RAG QA 응답을 생성한다."""
    return await _generate_qa(request, response)


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _response_payload(result: QAResponse | JSONResponse) -> tuple[str, dict]:
    if isinstance(result, JSONResponse):
        return "error", json.loads(result.body.decode("utf-8"))
    return "done", result.model_dump(mode="json")


@router.post("/qa/stream")
async def generate_qa_stream(request: QARequest) -> StreamingResponse:
    """QA 진행 단계를 SSE로 전달하고 기존 QA 응답을 done 이벤트로 반환한다."""

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_stage(stage: str) -> None:
            await queue.put(
                (
                    "stage",
                    {
                        "stage": stage,
                        "label": QA_STAGE_LABELS[stage],
                    },
                )
            )

        async def run_qa() -> None:
            response = Response()
            try:
                result = await _generate_qa(
                    request,
                    response,
                    stage_callback=on_stage,
                )
                await queue.put(_response_payload(result))
            except Exception as exc:
                api_logger.exception(
                    "qa_stream_unhandled_error endpoint=%s message=%s",
                    "/api/v1/qa/stream",
                    exc,
                )
                await queue.put(
                    (
                        "error",
                        {
                            "success": False,
                            "request_id": str(request.request_id or "").strip()
                            or make_request_id(),
                            "timestamp": now_iso(),
                            "error": {
                                "code": "INTERNAL_SERVER_ERROR",
                                "message": "QA 스트림 처리 중 예기치 못한 오류가 발생했습니다.",
                                "retryable": False,
                                "details": {"reason": str(exc)},
                            },
                        },
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_qa())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, payload = item
                yield _sse_event(event, payload)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Contract-Version": CONTRACT_VERSION,
        },
    )
