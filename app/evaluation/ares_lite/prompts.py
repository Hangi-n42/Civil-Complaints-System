"""Prompt builders for LLM-based ARES-lite judges."""

from __future__ import annotations

import json
from typing import Any

from app.evaluation.ares_lite.schemas import AresLiteCase, AresLiteContext

CONTEXT_RELEVANCE_QUESTION = (
    "검색된 context가 현재 민원의 핵심 이슈, 장소, 시설, 위험 요소, 담당 부서와 "
    "의미적으로 관련 있는가?"
)

ANSWER_FAITHFULNESS_QUESTION = (
    "생성 답변의 사실 주장, 조치 내용, 처리 일정, 담당 부서, 법령 언급이 "
    "검색 context 또는 citation으로 뒷받침되는가?"
)

ANSWER_RELEVANCE_QUESTION = (
    "답변이 민원인의 핵심 요청, 불편 사항, 위험 요소, 조치 요구에 직접 대응하는가?"
)

ARES_LITE_SCORE_GUIDE = {
    "9-10": "핵심 이슈와 직접 관련 있고 근거 또는 답변 대응성이 매우 높음",
    "7-8": "주요 이슈와 관련 있으나 일부 세부 조건은 약함",
    "5-6": "넓은 주제는 같지만 구체성이 부족하거나 일부만 대응함",
    "3-4": "일부 단어만 겹치고 실제 근거 또는 대응성이 약함",
    "0-2": "현재 민원과 거의 무관하거나 답변 근거로 쓰기 어려움",
}


def ares_lite_response_schema(metric: str) -> dict[str, Any]:
    if metric == "context_relevance":
        return {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "label": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["score", "label", "reason"],
        }
    if metric == "answer_faithfulness":
        return {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "label": {"type": "string"},
                "unsupported_claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["sentence", "reason"],
                    },
                },
                "revision_hint": {"type": "string"},
            },
            "required": ["score", "label", "unsupported_claims", "revision_hint"],
        }
    if metric == "answer_relevance":
        return {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "label": {"type": "string"},
                "missing_points": {"type": "array", "items": {"type": "string"}},
                "revision_hint": {"type": "string"},
            },
            "required": ["score", "label", "missing_points", "revision_hint"],
        }
    raise ValueError(f"unknown ARES-lite metric: {metric}")


def ares_lite_integrated_response_schema() -> dict[str, Any]:
    context_item_schema = {
        "type": "object",
        "properties": {
            "context_id": {"type": "string"},
            "score": {"type": "number"},
            "label": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["context_id", "score", "label", "reason"],
    }
    low_context_schema = {
        "type": "object",
        "properties": {
            "context_id": {"type": "string"},
            "score": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["context_id", "score", "reason"],
    }
    unsupported_claim_schema = {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["sentence", "reason"],
    }
    return {
        "type": "object",
        "properties": {
            "context_relevance": {
                "type": "object",
                "properties": {
                    "average_score": {"type": "number"},
                    "label": {"type": "string"},
                    "contexts": {"type": "array", "items": context_item_schema},
                    "low_relevance_contexts": {"type": "array", "items": low_context_schema},
                    "revision_hint": {"type": "string"},
                },
                "required": [
                    "average_score",
                    "label",
                    "contexts",
                    "low_relevance_contexts",
                    "revision_hint",
                ],
            },
            "answer_faithfulness": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "label": {"type": "string"},
                    "unsupported_claims": {"type": "array", "items": unsupported_claim_schema},
                    "revision_hint": {"type": "string"},
                },
                "required": ["score", "label", "unsupported_claims", "revision_hint"],
            },
            "answer_relevance": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "label": {"type": "string"},
                    "covered_segments": {"type": "array", "items": {"type": "string"}},
                    "missing_points": {"type": "array", "items": {"type": "string"}},
                    "revision_hint": {"type": "string"},
                },
                "required": ["score", "label", "covered_segments", "missing_points", "revision_hint"],
            },
        },
        "required": ["context_relevance", "answer_faithfulness", "answer_relevance"],
    }


def build_integrated_ares_lite_prompt(
    case: AresLiteCase,
    answer_body: str,
    *,
    max_contexts: int = 5,
) -> str:
    return (
        "You are an ARES-style evaluator for a Korean civil complaint RAG system.\n"
        "Judge the same generated answer on exactly three diagnostic dimensions in ONE pass:\n"
        "1) context_relevance: whether retrieved contexts can support an official reply to the complaint.\n"
        "2) answer_faithfulness: whether factual claims, administrative promises, schedules, legal basis, "
        "department names, and completed actions are supported by the contexts/citations.\n"
        "3) answer_relevance: whether the answer directly addresses every citizen request segment.\n\n"
        "Use 0-10 scores. Be strict about unsupported promises and irrelevant retrieved cases. "
        "Do not reward polite boilerplate. Do not penalize fixed civil-reply opening/closing text unless it hides "
        "missing substance. Return exactly one JSON object matching the schema.\n\n"
        f"[Score guide]\n{_score_guide_text()}\n\n"
        "[Metric questions]\n"
        f"- context_relevance: {CONTEXT_RELEVANCE_QUESTION}\n"
        f"- answer_faithfulness: {ANSWER_FAITHFULNESS_QUESTION}\n"
        f"- answer_relevance: {ANSWER_RELEVANCE_QUESTION}\n\n"
        "[Low-score risk examples for answer_faithfulness]\n"
        "- Unsupported completed action, immediate action, or confirmed schedule.\n"
        "- Legal article or department routing not visible in retrieved evidence.\n"
        "- A response conclusion that contradicts private-land, unavailable-service, or jurisdiction limits.\n\n"
        f"[Complaint]\n{case.query}\n\n"
        f"[Request segments]\n{json.dumps(case.request_segments, ensure_ascii=False)}\n\n"
        f"[Generated answer body]\n{answer_body[:3000]}\n\n"
        f"[Retrieved contexts]\n{_format_contexts(case, max_contexts=max_contexts)}\n\n"
        f"[Citations]\n{_format_citations(case)}\n\n"
        "[Required JSON shape]\n"
        "{context_relevance:{average_score,label,contexts,low_relevance_contexts,revision_hint}, "
        "answer_faithfulness:{score,label,unsupported_claims,revision_hint}, "
        "answer_relevance:{score,label,covered_segments,missing_points,revision_hint}}\n"
    )


def build_context_relevance_prompt(case: AresLiteCase, context: AresLiteContext) -> str:
    return (
        "You are an ARES-style evaluator for a Korean civil complaint RAG system.\n"
        "Evaluate ONLY Context Relevance: whether the retrieved context is useful for answering the citizen complaint.\n"
        "Use a 0-10 score. Do not reward generic keyword overlap if the context cannot support an official answer.\n"
        "Return exactly one JSON object matching the schema.\n\n"
        f"[Evaluation question]\n{CONTEXT_RELEVANCE_QUESTION}\n\n"
        f"[Score guide]\n{_score_guide_text()}\n\n"
        f"[Complaint]\n{case.query}\n\n"
        f"[Request segments]\n{json.dumps(case.request_segments, ensure_ascii=False)}\n\n"
        "[Retrieved context]\n"
        f"context_id={context.context_id}\n"
        f"source={context.source}\n"
        f"rank={context.rank}\n"
        f"retrieval_score={context.score}\n"
        f"{context.content[:2200]}\n\n"
        "[Required JSON keys]\n"
        "score, label, reason\n"
    )


def build_answer_faithfulness_prompt(
    case: AresLiteCase,
    answer_body: str,
    *,
    max_contexts: int = 5,
) -> str:
    return (
        "You are an ARES-style evaluator for a Korean civil complaint RAG system.\n"
        "Evaluate ONLY Answer Faithfulness: whether factual claims in the generated answer are supported by the retrieved contexts or citations.\n"
        "Be strict about administrative promises, schedules, legal basis, department names, completed actions, and unavailable evidence.\n"
        "Do not judge tone or general helpfulness here.\n"
        "Return exactly one JSON object matching the schema.\n\n"
        f"[Evaluation question]\n{ANSWER_FAITHFULNESS_QUESTION}\n\n"
        f"[Score guide]\n{_score_guide_text()}\n\n"
        "[Low-score risk examples]\n"
        "- 이미 완료되었습니다: unsupported completed action\n"
        "- 즉시 조치하겠습니다: unsupported authority/schedule\n"
        "- 다음 주까지 처리됩니다: unsupported schedule\n"
        "- 해당 법령에 따라 불가합니다: legal claim without evidence\n"
        "- 담당 부서는 ○○과입니다: department routing without evidence\n\n"
        f"[Complaint]\n{case.query}\n\n"
        f"[Generated answer body]\n{answer_body[:2600]}\n\n"
        f"[Retrieved contexts]\n{_format_contexts(case, max_contexts=max_contexts)}\n\n"
        f"[Citations]\n{_format_citations(case)}\n\n"
        "[Required JSON keys]\n"
        "score, label, unsupported_claims, revision_hint\n"
    )


def build_answer_relevance_prompt(case: AresLiteCase, answer_body: str) -> str:
    return (
        "You are an ARES-style evaluator for a Korean civil complaint RAG system.\n"
        "Evaluate ONLY Answer Relevance: whether the generated answer directly responds to the citizen's request, inconvenience, risk factors, and requested action.\n"
        "For complex complaints, check each request segment and list missing points.\n"
        "Do not judge whether claims are grounded; that belongs to Answer Faithfulness.\n"
        "Return exactly one JSON object matching the schema.\n\n"
        f"[Evaluation question]\n{ANSWER_RELEVANCE_QUESTION}\n\n"
        f"[Score guide]\n{_score_guide_text()}\n\n"
        f"[Complaint]\n{case.query}\n\n"
        f"[Request segments]\n{json.dumps(case.request_segments, ensure_ascii=False)}\n\n"
        f"[Generated answer body]\n{answer_body[:2600]}\n\n"
        "[Required JSON keys]\n"
        "score, label, missing_points, revision_hint\n"
    )


def _score_guide_text() -> str:
    return "\n".join(f"- {key}: {value}" for key, value in ARES_LITE_SCORE_GUIDE.items())


def _format_contexts(case: AresLiteCase, *, max_contexts: int = 5) -> str:
    lines = []
    for index, context in enumerate(case.retrieved_contexts[:max_contexts], start=1):
        lines.append(
            f"R{index}. context_id={context.context_id} source={context.source} rank={context.rank}\n"
            f"{context.content[:900]}"
        )
    return "\n\n".join(lines) or "(제공 근거 없음)"


def _format_citations(case: AresLiteCase) -> str:
    lines = []
    for index, citation in enumerate(case.citations, start=1):
        lines.append(
            f"C{index}. doc_id={citation.doc_id} source={citation.source}\n"
            f"{citation.quote[:500]}"
        )
    return "\n\n".join(lines) or "(citation 없음)"
