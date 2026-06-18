"""Prometheus-style feedback layer for Civil Complaint LLM-Rubric.

Prometheus is used as an advisory feedback generator, not as the official
score source. It runs only when one or more rubric item scores are low enough
to justify a revision attempt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.evaluation.civil_llm_rubric import RUBRIC_OPTIONS, extract_generated_body

LLMCall = Callable[..., Awaitable[str]]


def _score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 10.0


def _as_string_list(value: Any, *, limit: int = 5) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:limit]
    text = str(value or "").strip()
    return [text] if text else []


def select_low_score_items(
    rubric_result: dict[str, Any],
    *,
    threshold_1_4: float,
) -> list[dict[str, Any]]:
    raw = rubric_result.get("llm_rubric_raw")
    if not isinstance(raw, dict):
        return []

    low_items: list[dict[str, Any]] = []
    for qid, item in raw.items():
        if not isinstance(item, dict):
            continue
        expected_1_4 = _score(item.get("expected_1_4"))
        argmax = int(_score(item.get("argmax")))
        should_trigger = expected_1_4 <= threshold_1_4 or argmax <= threshold_1_4
        if should_trigger:
            low_items.append(
                {
                    "qid": str(qid),
                    "name": str(item.get("name") or RUBRIC_OPTIONS.get(str(qid), {}).get("name") or ""),
                    "trigger_score_1_4": round(expected_1_4, 4),
                    "argmax": argmax,
                    "score_0_10": round(_score(item.get("score_0_10")), 2),
                }
            )
    safety_layer = rubric_result.get("safety_layer")
    if isinstance(safety_layer, dict):
        final_q0_0_10 = _score(safety_layer.get("final_q0_score_0_10"))
        final_q0_1_4 = 1.0 + max(0.0, min(10.0, final_q0_0_10)) / 10.0 * 3.0
        if final_q0_1_4 <= threshold_1_4 and not any(item["qid"] == "q0" for item in low_items):
            low_items.insert(
                0,
                {
                    "qid": "q0",
                    "name": "전체 민원 회신 만족도(safety cap 적용)",
                    "trigger_score_1_4": round(final_q0_1_4, 4),
                    "argmax": None,
                    "score_0_10": round(final_q0_0_10, 2),
                    "cap_reason": safety_layer.get("cap_reason"),
                },
            )
    return low_items


@dataclass
class PrometheusFeedbackEngine:
    trigger_max_choice: float = settings.PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE
    temperature: float = settings.PROMETHEUS_RUBRIC_TEMPERATURE
    max_contexts: int = settings.CIVIL_LLM_RUBRIC_MAX_CONTEXTS

    async def build_feedback(
        self,
        *,
        case_id: str,
        complaint_text: str,
        generated_answer: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        rubric_result: dict[str, Any],
        llm_call: LLMCall,
    ) -> dict[str, Any]:
        low_items = select_low_score_items(
            rubric_result,
            threshold_1_4=self.trigger_max_choice,
        )
        if not low_items:
            return {
                "triggered": False,
                "trigger_threshold_1_4": self.trigger_max_choice,
                "low_score_items": [],
                "source": "not_triggered",
            }

        prompt = self._build_feedback_prompt(
            case_id=case_id,
            complaint_text=complaint_text,
            generated_answer=generated_answer,
            references=references,
            citations=citations,
            rubric_result=rubric_result,
            low_items=low_items,
        )
        schema = self._feedback_schema()
        try:
            text = await llm_call(
                prompt,
                temperature=self.temperature,
                response_schema=schema,
            )
            payload = self._parse_json(text)
        except TypeError:
            text = await llm_call(prompt)
            payload = self._parse_json(text)

        return self._normalize_feedback(payload, low_items=low_items)

    def build_revision_prompt(
        self,
        *,
        complaint_text: str,
        current_answer: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        prometheus_feedback: dict[str, Any],
    ) -> str:
        context_block = self._format_references(references)
        citation_block = self._format_citations(citations)
        feedback = str(prometheus_feedback.get("feedback") or "").strip()
        revision_hint = str(prometheus_feedback.get("revision_hint") or "").strip()
        weaknesses = "\n".join(
            f"- {item}" for item in _as_string_list(prometheus_feedback.get("weaknesses"))
        )
        risk_flags = ", ".join(_as_string_list(prometheus_feedback.get("risk_flags"))) or "none"

        return (
            "[PROMETHEUS REVISION TASK]\n"
            "Revise the Korean public-sector civil complaint reply using the Prometheus-style feedback.\n"
            "Do not mention Prometheus, rubric scores, evaluation, or internal diagnostics in the public answer.\n"
            "Keep the official civil reply tone. Do not invent laws, departments, phone numbers, dates, or completed actions.\n"
            "Use only the provided references and existing citations. If evidence is insufficient, say that the 담당부서 확인이 필요합니다.\n\n"
            "[민원 원문]\n"
            f"{complaint_text}\n\n"
            "[현재 답변]\n"
            f"{current_answer}\n\n"
            "[Prometheus feedback]\n"
            f"{feedback}\n\n"
            "[Weaknesses]\n"
            f"{weaknesses or '- 구체적 약점 없음'}\n\n"
            "[Revision hint]\n"
            f"{revision_hint or '낮은 점수 항목을 중심으로 근거, 절차, 제약, 후속 안내를 보강하세요.'}\n\n"
            "[Risk flags]\n"
            f"{risk_flags}\n\n"
            "[제공 근거]\n"
            f"{context_block or '(제공 근거 없음)'}\n\n"
            "[기존 citations]\n"
            f"{citation_block or '(citation 없음)'}\n\n"
            "[Output JSON]\n"
            "Return exactly one JSON object with keys answer, citations, limitations, structured_output.\n"
            "structured_output must contain summary, action_items, request_segments.\n"
        )

    def _build_feedback_prompt(
        self,
        *,
        case_id: str,
        complaint_text: str,
        generated_answer: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        rubric_result: dict[str, Any],
        low_items: list[dict[str, Any]],
    ) -> str:
        low_item_text = "\n".join(
            f"- {item['qid']} {item['name']}: trigger_score_1_4={item['trigger_score_1_4']}, "
            f"argmax={item.get('argmax')}, score_0_10={item['score_0_10']}"
            for item in low_items
        )
        diagnostics = rubric_result.get("diagnostics")
        diagnostics_text = json.dumps(
            diagnostics if isinstance(diagnostics, dict) else {},
            ensure_ascii=False,
        )
        rule_features = rubric_result.get("rule_features")
        rule_text = json.dumps(
            rule_features if isinstance(rule_features, dict) else {},
            ensure_ascii=False,
        )
        return (
            "You are a Prometheus-style fine-grained evaluator for Korean civil complaint replies.\n"
            "Generate concise, actionable feedback for revising the answer. Do not change official scores.\n"
            "Focus only on rubric items whose 1-4 rubric choice/expected score is 2.0 or lower.\n"
            "Do not reveal hidden chain-of-thought. Provide reviewer-facing reasons and revision guidance only.\n\n"
            "[case_id]\n"
            f"{case_id}\n\n"
            "[민원 원문]\n"
            f"{complaint_text}\n\n"
            "[생성 답변]\n"
            f"{generated_answer}\n\n"
            "[생성 본문]\n"
            f"{extract_generated_body(generated_answer)}\n\n"
            "[낮은 rubric 항목]\n"
            f"{low_item_text}\n\n"
            "[diagnostics]\n"
            f"{diagnostics_text}\n\n"
            "[rule_features]\n"
            f"{rule_text}\n\n"
            "[references]\n"
            f"{self._format_references(references) or '(제공 근거 없음)'}\n\n"
            "[citations]\n"
            f"{self._format_citations(citations) or '(citation 없음)'}\n\n"
            "[Required JSON]\n"
            "feedback: one concise Korean paragraph.\n"
            "strengths: up to 3 strings.\n"
            "weaknesses: up to 5 strings, each tied to a low rubric item.\n"
            "revision_hint: one concrete Korean instruction paragraph for regeneration.\n"
            "risk_flags: short string flags.\n"
        )

    @staticmethod
    def _feedback_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "feedback": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
                "revision_hint": {"type": "string"},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["feedback", "weaknesses", "revision_hint"],
        }

    @staticmethod
    def _revision_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "object"}},
                "limitations": {"type": ["string", "array"]},
                "structured_output": {"type": "object"},
            },
            "required": ["answer", "limitations", "structured_output"],
        }

    @classmethod
    def revision_schema(cls) -> dict[str, Any]:
        return cls._revision_schema()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = str(text or "").strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match is None:
                raise
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("Prometheus feedback response must be a JSON object")
        return payload

    def _normalize_feedback(
        self,
        payload: dict[str, Any],
        *,
        low_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        feedback = str(payload.get("feedback") or "").strip()
        revision_hint = str(payload.get("revision_hint") or "").strip()
        weaknesses = _as_string_list(payload.get("weaknesses"), limit=5)

        return {
            "triggered": True,
            "trigger_threshold_1_4": self.trigger_max_choice,
            "low_score_items": low_items,
            "source": "prometheus_llm",
            "feedback": feedback or "낮은 점수 항목을 중심으로 근거, 절차, 제약 사항을 보강해야 합니다.",
            "strengths": _as_string_list(payload.get("strengths"), limit=3),
            "weaknesses": weaknesses,
            "revision_hint": revision_hint
            or "낮은 점수 항목을 중심으로 근거, 절차, 제약, 후속 안내를 보강하세요.",
            "risk_flags": _as_string_list(payload.get("risk_flags"), limit=5),
        }

    def _format_references(self, references: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, item in enumerate(references[: self.max_contexts], start=1):
            title = str(item.get("title") or item.get("case_id") or item.get("doc_id") or f"R{index}")
            snippet = str(item.get("snippet") or item.get("text") or "")[:500]
            lines.append(f"R{index}. {title}: {snippet}")
        return "\n".join(lines)

    @staticmethod
    def _format_citations(citations: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, item in enumerate(citations, start=1):
            source = str(item.get("doc_id") or item.get("case_id") or item.get("source") or "")
            quote = str(item.get("quote") or item.get("snippet") or "")[:300]
            lines.append(f"C{index}. source={source} quote={quote}")
        return "\n".join(lines)


_engine: PrometheusFeedbackEngine | None = None


def get_prometheus_feedback_engine() -> PrometheusFeedbackEngine:
    global _engine
    if _engine is None:
        _engine = PrometheusFeedbackEngine()
    _engine.trigger_max_choice = settings.PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE
    _engine.temperature = settings.PROMETHEUS_RUBRIC_TEMPERATURE
    _engine.max_contexts = settings.CIVIL_LLM_RUBRIC_MAX_CONTEXTS
    return _engine
