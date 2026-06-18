"""Runtime Civil Complaint LLM-Rubric evaluator.

This module implements the vNext rubric described in
docs/40_delivery/week11/llm_evaluation/Civil_Complaint_LLM_Rubric.md.
The first production version stores Q0-Q7 distributions, rule features,
manual-completeness features, calibration status, and safety-capped final Q0.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

LLMCall = Callable[..., Awaitable[str]]


RUBRIC_OPTIONS: dict[str, dict[str, Any]] = {
    "q0": {
        "name": "전체 민원 회신 만족도",
        "question": "이 답변은 민원인이 받아들일 만한 전체 민원 회신으로 얼마나 만족스러운가?",
        "options": {
            1: "민원 요지, 근거, 절차, 표현 중 핵심 결함이 커서 실제 회신으로 부적절하다.",
            2: "일부 요소는 갖추었지만 중요한 근거, 절차, 명확성 또는 안전성 결함이 있다.",
            3: "대체로 실제 회신으로 사용할 수 있으나 일부 보완할 부분이 있다.",
            4: "근거와 절차, 문체, 간결성이 모두 좋아 실제 회신으로 매우 적절하다.",
        },
    },
    "q1": {
        "name": "공공기관 회신 문체와 정중성",
        "question": "공공기관 민원 회신에 맞는 정중하고 공감적인 문체로 작성되었는가?",
        "options": {
            1: "불친절하거나 감정적 대응, 단정적 표현이 두드러진다.",
            2: "공식 문체는 일부 있으나 딱딱하거나 설명이 불친절하다.",
            3: "대체로 정중하고 공공기관 회신 문체에 맞는다.",
            4: "정중성, 공감, 눈높이 설명이 모두 우수하다.",
        },
    },
    "q2": {
        "name": "근거 자료 충분성",
        "question": "제공된 근거 자료만 보았을 때 민원 답변을 작성하기에 충분하고 관련성이 높은가?",
        "options": {
            1: "근거 자료가 없거나 민원과 거의 관련이 없다.",
            2: "일부 관련 근거는 있으나 핵심 판단이나 절차를 설명하기에는 부족하다.",
            3: "답변 작성에 필요한 주요 근거가 대체로 포함되어 있다.",
            4: "직접적이고 신뢰도 높은 근거가 충분히 제공되어 있다.",
        },
        "reference_only": True,
    },
    "q3": {
        "name": "핵심 주장 인용 포함성",
        "question": "답변의 핵심 주장에 구조화된 citation이 충분히 붙어 있는가?",
        "options": {
            1: "핵심 주장 대부분에 citation이 없다.",
            2: "citation은 있으나 핵심 주장 대비 부족하다.",
            3: "주요 주장 대부분에 citation이 붙어 있다.",
            4: "핵심 주장마다 필요한 citation이 명확하게 붙어 있다.",
        },
    },
    "q4": {
        "name": "인용 근거 정확성",
        "question": "citation이 답변의 주장을 실제로 뒷받침하는가?",
        "options": {
            1: "citation이 주장과 맞지 않거나 검증되지 않는다.",
            2: "일부 citation만 주장을 뒷받침한다.",
            3: "대부분의 citation이 주장을 적절히 뒷받침한다.",
            4: "citation과 주장의 대응이 매우 정확하다.",
        },
    },
    "q5": {
        "name": "최적 근거 선택성",
        "question": "제공 source 중 가장 직접적이고 신뢰도 높은 근거를 선택했는가?",
        "options": {
            1: "더 좋은 근거가 있는데 약한 근거를 사용했거나 근거 선택이 부적절하다.",
            2: "근거 선택이 일부 적절하지만 더 직접적인 근거를 놓쳤다.",
            3: "대체로 직접적이고 신뢰도 높은 근거를 사용했다.",
            4: "가장 적절한 고신뢰 근거를 우선적으로 선택했다.",
        },
    },
    "q6": {
        "name": "반복·불필요 요소 없음",
        "question": "반복, 복붙 문구, 동문서답, 내부 메타데이터 노출이 없는가?",
        "options": {
            1: "반복이나 불필요 요소가 심해 답변 품질을 크게 해친다.",
            2: "일부 반복, 군더더기, 내부 흔적이 보인다.",
            3: "대체로 반복이나 불필요 요소가 적다.",
            4: "불필요한 반복과 내부 노출 없이 깔끔하다.",
        },
    },
    "q7": {
        "name": "응답 효율성 및 간결성",
        "question": "민원 요구의 복잡도에 비해 답변 길이와 정보 밀도가 적절한가?",
        "options": {
            1: "지나치게 장황하거나 과도하게 압축되어 이해하기 어렵다.",
            2: "대체로 이해는 가능하지만 다소 길거나 설명 밀도가 낮다.",
            3: "길이와 설명 밀도가 대체로 적절하다.",
            4: "필요한 범위에서 매우 간결하고 정보 밀도가 높다.",
        },
    },
}

RISK_FIXES = {
    "retrieval_insufficient": "검색 query reformulation 또는 source 보강이 필요합니다.",
    "missing_citation": "핵심 주장별 citation 삽입을 강화해야 합니다.",
    "weak_citation_support": "citation verifier로 claim-support 정합성을 재검토해야 합니다.",
    "suboptimal_source": "법령·조례·공식 지침 우선 source reranking이 필요합니다.",
    "tone_inappropriate": "공공기관 회신 문체와 감정적 대응 방지 prompt를 강화해야 합니다.",
    "redundant_or_template_answer": "반복 문구와 내부 메타데이터 노출을 제거해야 합니다.",
    "incomplete_procedure_guidance": "접수, 검토, 보완, 후속 문의 등 업무 절차 안내를 보강해야 합니다.",
    "missing_legal_basis": "법령·규정·업무 기준 근거를 보강해야 합니다.",
    "unsafe_promise": "권한 밖 직접 조치나 확정적 약속을 조건부 검토 표현으로 바꿔야 합니다.",
    "emotional_response": "비난, 경고, 맞대응 표현을 제거하고 원칙적 안내로 바꿔야 합니다.",
    "special_complaint_safety_missing": "반복·폭언·협박 등 특이민원 절차와 담당자 보호 기준을 반영해야 합니다.",
    "debug_or_metadata_leakage": "JSON, 로그, chunk_id 등 내부 메타데이터 노출을 차단해야 합니다.",
}

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
SENTENCE_RE = re.compile(r"[^.!?\n。！？]+[.!?。！？]?")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _score_from_expected(expected_1_4: float) -> float:
    return _round((_clamp(expected_1_4, 1.0, 4.0) - 1.0) / 3.0 * 10.0, 2)


def _expected_from_probs(probs: list[float]) -> float:
    return sum((index + 1) * prob for index, prob in enumerate(probs))


def _entropy(probs: list[float]) -> float:
    return _round(-sum(prob * math.log(prob) for prob in probs if prob > 0.0), 4)


def _probs_from_expected(expected_1_4: float) -> list[float]:
    expected = _clamp(expected_1_4, 1.0, 4.0)
    lower = int(math.floor(expected))
    upper = int(math.ceil(expected))
    probs = [0.0, 0.0, 0.0, 0.0]
    if lower == upper:
        probs[lower - 1] = 1.0
    else:
        upper_weight = expected - lower
        probs[lower - 1] = 1.0 - upper_weight
        probs[upper - 1] = upper_weight
    return [_round(prob) for prob in probs]


def _probs_from_choice(choice: int, confidence: float | None = None) -> list[float]:
    argmax = max(1, min(4, int(choice)))
    conf = _clamp(float(confidence if confidence is not None else 0.7), 0.25, 0.95)
    rest = (1.0 - conf) / 3.0
    probs = [rest, rest, rest, rest]
    probs[argmax - 1] = conf
    return [_round(prob) for prob in probs]


def _rubric_item(
    *,
    qid: str,
    probs: list[float],
    source: str,
    reason: str = "",
    error: str = "",
) -> dict[str, Any]:
    expected = _expected_from_probs(probs)
    argmax = int(max(range(4), key=lambda index: probs[index]) + 1)
    return {
        "qid": qid,
        "name": RUBRIC_OPTIONS[qid]["name"],
        "probs": probs,
        "argmax": argmax,
        "expected_1_4": _round(expected, 4),
        "score_0_10": _score_from_expected(expected),
        "entropy": _entropy(probs),
        "source": source,
        "reason": reason,
        "error": error,
    }


def extract_generated_body(answer: str) -> str:
    """Return the generated review body when the standard reply shell exists."""
    text = str(answer or "").strip()
    if not text:
        return ""

    match = re.search(
        r"3\.\s*검토\s*의견은\s*다음과\s*같습니다\.?\s*(.*?)(?:\n\s*\n?\s*4\.|\Z)",
        text,
        flags=re.DOTALL,
    )
    if match:
        return match.group(1).strip()

    match = re.search(r"3\.\s*(.*?)(?:\n\s*\n?\s*4\.|\Z)", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip()

    return text


def _sentences(text: str) -> list[str]:
    sentences = [item.strip() for item in SENTENCE_RE.findall(str(text or ""))]
    return [item for item in sentences if len(item) >= 8]


def _keywords(text: str) -> set[str]:
    stopwords = {
        "민원",
        "문의",
        "요청",
        "답변",
        "안내",
        "관련",
        "귀하",
        "내용",
        "사항",
        "검토",
        "처리",
        "해당",
        "있습니다",
        "합니다",
    }
    return {token for token in TOKEN_RE.findall(str(text or "").casefold()) if token not in stopwords}


def _contains(pattern: str, text: str) -> bool:
    return re.search(pattern, str(text or ""), flags=re.IGNORECASE) is not None


def _source_priority(item: dict[str, Any]) -> int:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    haystack = " ".join(
        str(value)
        for value in (
            item.get("source"),
            item.get("source_type"),
            item.get("title"),
            item.get("snippet"),
            item.get("text"),
            metadata.get("source"),
            metadata.get("category"),
        )
        if value is not None
    ).casefold()

    if _contains(r"법령|시행령|조례|고시|제\s*\d+\s*조|law|ordinance|article", haystack):
        return 1
    if _contains(r"지침|기준|매뉴얼|업무|manual|guideline|policy", haystack):
        return 2
    if _contains(r"홈페이지|faq|자주\s*묻|official", haystack):
        return 3
    if _contains(r"보도자료|설명자료|안내문|notice|press", haystack):
        return 4
    return 5


def _extract_responsible_units(query_signals: dict[str, Any] | None) -> list[str]:
    if not isinstance(query_signals, dict):
        return []
    units = query_signals.get("responsible_units")
    if not isinstance(units, list):
        return []
    return [str(item).strip() for item in units if str(item).strip()]


@dataclass
class CivilComplaintRubricEvaluator:
    rubric_version: str = settings.CIVIL_LLM_RUBRIC_VERSION
    judge_prompt_version: str = settings.CIVIL_LLM_RUBRIC_JUDGE_PROMPT_VERSION
    use_llm_judge: bool = settings.CIVIL_LLM_RUBRIC_USE_LLM_JUDGE
    max_contexts: int = settings.CIVIL_LLM_RUBRIC_MAX_CONTEXTS
    temperature: float = settings.CIVIL_LLM_RUBRIC_TEMPERATURE

    async def evaluate(
        self,
        *,
        case_id: str,
        complaint_text: str,
        generated_answer: str,
        references: list[dict[str, Any]] | None = None,
        citations: list[dict[str, Any]] | None = None,
        routing_trace: dict[str, Any] | None = None,
        quality_signals: dict[str, Any] | None = None,
        citation_validation: dict[str, Any] | None = None,
        legal_citations: list[dict[str, Any]] | None = None,
        legal_citation_warnings: list[str] | None = None,
        query_signals: dict[str, Any] | None = None,
        generation_metadata: dict[str, Any] | None = None,
        llm_call: LLMCall | None = None,
    ) -> dict[str, Any]:
        references = references or []
        citations = citations or []
        quality_signals = quality_signals or {}
        citation_validation = citation_validation or {}
        legal_citations = legal_citations or []
        legal_citation_warnings = legal_citation_warnings or []
        generation_metadata = generation_metadata or {}
        routing_trace = routing_trace or {}
        generated_body = extract_generated_body(generated_answer)

        rule_features = self._extract_rule_features(
            complaint_text=complaint_text,
            generated_answer=generated_answer,
            generated_body=generated_body,
            references=references,
            citations=citations,
            quality_signals=quality_signals,
            citation_validation=citation_validation,
            legal_citation_warnings=legal_citation_warnings,
        )
        manual_features = self._extract_manual_completeness_features(
            complaint_text=complaint_text,
            generated_answer=generated_answer,
            generated_body=generated_body,
            routing_trace=routing_trace,
            quality_signals=quality_signals,
            legal_citations=legal_citations,
            query_signals=query_signals,
        )
        rule_baseline = self._rule_baseline_raw(
            rule_features=rule_features,
            manual_features=manual_features,
            reference_count=len(references),
        )

        llm_raw: dict[str, Any] = {}
        llm_errors: list[str] = []
        can_call_llm = self.use_llm_judge and callable(llm_call)
        if can_call_llm:
            for qid in RUBRIC_OPTIONS:
                try:
                    llm_raw[qid] = await self._judge_question(
                        qid=qid,
                        complaint_text=complaint_text,
                        generated_answer=generated_answer,
                        references=references,
                        citations=citations,
                        llm_call=llm_call,
                    )
                except Exception as exc:  # noqa: BLE001
                    llm_errors.append(f"{qid}:{type(exc).__name__}")
                    llm_raw[qid] = _rubric_item(
                        qid=qid,
                        probs=rule_baseline[qid]["probs"],
                        source="rule_fallback_after_llm_error",
                        reason="LLM judge failed; rule baseline was used.",
                        error=f"{type(exc).__name__}: {exc}",
                    )
        else:
            for qid in RUBRIC_OPTIONS:
                llm_raw[qid] = _rubric_item(
                    qid=qid,
                    probs=rule_baseline[qid]["probs"],
                    source="rule_fallback",
                    reason="LLM judge callable was unavailable or disabled.",
                )

        judge_status = self._judge_status(can_call_llm=can_call_llm, llm_errors=llm_errors)
        q0_raw_score = float(llm_raw["q0"]["score_0_10"])
        q0_rule_score = float(rule_baseline["q0"]["score_0_10"])

        calibrated_prediction = {
            "available": False,
            "reason": "human calibration data is not configured; using uncalibrated q0 raw score.",
            "model_version": None,
            "q0_expected_1_4": llm_raw["q0"]["expected_1_4"],
            "q0_score_0_10": q0_raw_score,
        }
        safety_layer = self._apply_safety_layer(
            q0_score_0_10=q0_raw_score,
            rule_features=rule_features,
            manual_features=manual_features,
            generation_metadata=generation_metadata,
        )
        diagnostics = self._build_diagnostics(
            llm_raw=llm_raw,
            rule_features=rule_features,
            manual_features=manual_features,
            safety_layer=safety_layer,
        )

        return {
            "case_id": str(case_id or ""),
            "rubric_version": self.rubric_version,
            "judge_prompt_version": self.judge_prompt_version,
            "judge_status": judge_status,
            "probability_source": self._probability_source(judge_status),
            "llm_rubric_raw": llm_raw,
            "rule_features": rule_features,
            "manual_completeness_features": manual_features,
            "calibrated_prediction": calibrated_prediction,
            "safety_layer": safety_layer,
            "score_summary": {
                "q0_llm_raw": q0_raw_score if llm_raw["q0"]["source"].startswith("llm") else None,
                "q0_rule_baseline": q0_rule_score,
                "q0_calibrated": float(calibrated_prediction["q0_score_0_10"]),
                "q0_final": float(safety_layer["final_q0_score_0_10"]),
            },
            "diagnostics": diagnostics,
        }

    async def _judge_question(
        self,
        *,
        qid: str,
        complaint_text: str,
        generated_answer: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        llm_call: LLMCall,
    ) -> dict[str, Any]:
        prompt = self._build_judge_prompt(
            qid=qid,
            complaint_text=complaint_text,
            generated_answer=generated_answer,
            references=references,
            citations=citations,
        )
        schema = {
            "type": "object",
            "properties": {
                "choice": {"type": "integer", "minimum": 1, "maximum": 4},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["choice"],
        }
        try:
            text = await llm_call(
                prompt,
                temperature=self.temperature,
                response_schema=schema,
            )
        except TypeError:
            text = await llm_call(prompt)

        payload = self._parse_judge_response(text)
        choice = int(payload["choice"])
        confidence = payload.get("confidence")
        probs = _probs_from_choice(choice, confidence)
        return _rubric_item(
            qid=qid,
            probs=probs,
            source="llm_judge_synthetic_probs",
            reason="Ollama logprobs are unavailable; choice/confidence was converted to a probability vector.",
        )

    def _build_judge_prompt(
        self,
        *,
        qid: str,
        complaint_text: str,
        generated_answer: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> str:
        rubric = RUBRIC_OPTIONS[qid]
        reference_block = self._format_references(references)
        citation_block = self._format_citations(citations)
        input_parts = [
            "[민원 원문]",
            str(complaint_text or "").strip(),
            "",
            "[민원 요약]",
            self._summarize_complaint(complaint_text),
            "",
            "[제공된 근거 자료]",
            reference_block or "(제공된 근거 없음)",
        ]
        if not rubric.get("reference_only"):
            input_parts.extend(
                [
                    "",
                    "[생성 답변]",
                    str(generated_answer or "").strip(),
                    "",
                    "[구조화 citation]",
                    citation_block or "(citation 없음)",
                ]
            )

        options = "\n".join(
            f"{number}. {text}" for number, text in rubric["options"].items()
        )
        return (
            "You are evaluating a Korean public-sector civil complaint response.\n"
            "Choose exactly one option for the rubric question.\n"
            "Return only JSON: {\"choice\": 1|2|3|4, \"confidence\": 0.0-1.0}.\n\n"
            "[Input]\n"
            + "\n".join(input_parts)
            + "\n\n[Question]\n"
            + str(rubric["question"])
            + "\n\n[Options]\n"
            + options
        )

    def _format_references(self, references: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, item in enumerate(references[: self.max_contexts], start=1):
            title = str(item.get("title") or item.get("case_id") or item.get("doc_id") or f"R{index}")
            text = str(item.get("snippet") or item.get("text") or "")[:500]
            priority = _source_priority(item)
            lines.append(f"R{index}. title={title} priority={priority} text={text}")
        return "\n".join(lines)

    @staticmethod
    def _format_citations(citations: list[dict[str, Any]]) -> str:
        lines = []
        for index, item in enumerate(citations, start=1):
            source = str(item.get("doc_id") or item.get("case_id") or item.get("source") or "")
            quote = str(item.get("quote") or item.get("snippet") or "")[:300]
            lines.append(f"C{index}. source={source} quote={quote}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_complaint(complaint_text: str) -> str:
        text = " ".join(str(complaint_text or "").split())
        return text[:240]

    @staticmethod
    def _parse_judge_response(text: str) -> dict[str, Any]:
        cleaned = str(text or "").strip()
        if re.fullmatch(r"[1-4]", cleaned):
            return {"choice": int(cleaned)}
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"[1-4]", cleaned)
            if match:
                return {"choice": int(match.group(0))}
            raise
        if isinstance(payload, dict):
            if "choice" in payload:
                return payload
            for key in ("answer", "score", "label"):
                if key in payload and str(payload[key]).strip() in {"1", "2", "3", "4"}:
                    return {"choice": int(payload[key])}
        raise ValueError("judge response does not contain choice 1-4")

    def _extract_rule_features(
        self,
        *,
        complaint_text: str,
        generated_answer: str,
        generated_body: str,
        references: list[dict[str, Any]],
        citations: list[dict[str, Any]],
        quality_signals: dict[str, Any],
        citation_validation: dict[str, Any],
        legal_citation_warnings: list[str],
    ) -> dict[str, Any]:
        body_sentences = _sentences(generated_body)
        claim_count = max(1, len(body_sentences))
        citation_count = len(citations)
        mismatch_count = int(citation_validation.get("mismatch_count", 0) or 0)
        valid_citation_count = max(0, citation_count - max(0, mismatch_count))
        coverage = float(
            quality_signals.get(
                "citation_coverage",
                min(1.0, citation_count / claim_count) if claim_count else 0.0,
            )
            or 0.0
        )
        support_rate = valid_citation_count / citation_count if citation_count else 0.0

        sentence_norms = [" ".join(TOKEN_RE.findall(item.casefold())) for item in body_sentences]
        duplicate_count = len(sentence_norms) - len(set(sentence_norms))
        repetition_ratio = duplicate_count / len(sentence_norms) if sentence_norms else 0.0
        template_hits = sum(
            1
            for phrase in (
                "검토 결과를 다음과 같이 답변드립니다",
                "추가 설명이 필요한 경우",
                "감사합니다",
                "담당부서",
            )
            if phrase in str(generated_answer or "")
        )
        debug_tokens = len(
            re.findall(
                r"chunk_id|case_id|metadata|retrieval|score|JSON|```|\{|\}|prompt|schema",
                str(generated_answer or ""),
                flags=re.IGNORECASE,
            )
        )
        reference_priorities = [_source_priority(item) for item in references]
        cited_priorities = self._priorities_for_citations(citations, references)
        source_priority_mean = (
            sum(cited_priorities) / len(cited_priorities)
            if cited_priorities
            else None
        )
        best_source_missed_count = self._best_source_missed_count(
            reference_priorities=reference_priorities,
            cited_priorities=cited_priorities,
        )
        unsafe_promise_flag = _contains(
            r"즉시\s*(설치|철거|보수|완료|처리)|반드시\s*(조치|해결)|"
            r"(설치|철거|보수|정비|완료)하겠습니다|확정되었습니다",
            generated_body,
        )
        emotional_response_flag = _contains(
            r"무고|처벌|고발|경고합니다|법적\s*조치|부당한\s*요구|악성|허위",
            generated_body,
        )
        special_complaint_flag = _contains(
            r"반복\s*민원|반복적으로|폭언|협박|욕설|위협|악성",
            complaint_text,
        )
        legal_anchor_count = len(re.findall(r"법|조례|규정|기준|근거|제\s*\d+\s*조", generated_body))
        procedure_anchor_count = len(re.findall(r"절차|신청|접수|보완|현장|확인|검토|협의|처리", generated_body))
        followup_anchor_count = len(re.findall(r"문의|추가\s*설명|연락|이의|재신청|담당부서", generated_body))

        risk_flags = []
        if debug_tokens:
            risk_flags.append("debug_or_metadata_leakage")
        if unsafe_promise_flag:
            risk_flags.append("unsafe_promise")
        if emotional_response_flag:
            risk_flags.append("emotional_response")
        if legal_citation_warnings:
            risk_flags.append("legal_citation_warning")
        if not citations:
            risk_flags.append("missing_citation")

        return {
            "strict_citation_count": valid_citation_count,
            "postprocessed_citation_count": citation_count,
            "claim_count": claim_count,
            "citation_coverage_rate": _round(_clamp(coverage, 0.0, 1.0), 4),
            "citation_support_rate_strict": _round(support_rate, 4),
            "source_priority_mean": _round(source_priority_mean, 4) if source_priority_mean is not None else None,
            "best_source_missed_count": best_source_missed_count,
            "repetition_ratio": _round(repetition_ratio, 4),
            "template_ratio": _round(template_hits / 4.0, 4),
            "debug_token_count": debug_tokens,
            "answer_token_length": len(str(generated_body or "")),
            "consultant_length_ratio": None,
            "procedure_anchor_count": procedure_anchor_count,
            "legal_anchor_count": legal_anchor_count,
            "followup_anchor_count": followup_anchor_count,
            "unsafe_promise_flag": unsafe_promise_flag,
            "emotional_response_flag": emotional_response_flag,
            "special_complaint_flag": special_complaint_flag,
            "risk_flags": risk_flags,
        }

    @staticmethod
    def _priorities_for_citations(
        citations: list[dict[str, Any]],
        references: list[dict[str, Any]],
    ) -> list[int]:
        if not citations:
            return []
        by_id: dict[str, int] = {}
        for item in references:
            priority = _source_priority(item)
            for key in ("doc_id", "case_id", "chunk_id", "source"):
                value = str(item.get(key) or "").strip()
                if value:
                    by_id[value] = priority

        priorities = []
        for citation in citations:
            matched = None
            for key in ("doc_id", "case_id", "chunk_id", "source"):
                value = str(citation.get(key) or "").strip()
                if value and value in by_id:
                    matched = by_id[value]
                    break
            priorities.append(matched if matched is not None else 5)
        return priorities

    @staticmethod
    def _best_source_missed_count(
        *,
        reference_priorities: list[int],
        cited_priorities: list[int],
    ) -> int:
        if not reference_priorities or not cited_priorities:
            return 0
        best_reference = min(reference_priorities)
        best_cited = min(cited_priorities)
        if best_cited <= best_reference:
            return 0
        return sum(1 for priority in reference_priorities if priority < best_cited)

    def _extract_manual_completeness_features(
        self,
        *,
        complaint_text: str,
        generated_answer: str,
        generated_body: str,
        routing_trace: dict[str, Any],
        quality_signals: dict[str, Any],
        legal_citations: list[dict[str, Any]],
        query_signals: dict[str, Any] | None,
    ) -> dict[str, Any]:
        request_segments = routing_trace.get("request_segments")
        segments = request_segments if isinstance(request_segments, list) else []
        overlap = self._complaint_answer_overlap(complaint_text, generated_answer)
        segment_coverage = float(quality_signals.get("segment_coverage", 0.0) or 0.0)
        responsible_units = _extract_responsible_units(query_signals)
        special_flag = _contains(r"반복\s*민원|폭언|협박|욕설|위협|악성", complaint_text)
        special_process = None
        if special_flag:
            special_process = _contains(
                r"민원조정|반복민원|종결|이의|경고|부서장|담당자\s*보호|전담부서",
                generated_body,
            )

        return {
            "complaint_issue_identified": bool(
                segment_coverage >= 0.5 or overlap >= 0.2 or not segments
            ),
            "judgment_or_answer_present": _contains(
                r"검토|확인|조치|가능|불가|어렵|예정|안내|처리|협의",
                generated_body,
            ),
            "legal_basis_present": bool(legal_citations)
            or _contains(r"법|조례|규정|기준|근거|제\s*\d+\s*조", generated_body),
            "procedure_guidance_present": _contains(
                r"절차|신청|접수|보완|현장|확인|검토|협의|처리|안내",
                generated_body,
            ),
            "limitation_or_constraint_explained": _contains(
                r"다만|불가|어렵|제한|한계|소관|권한|여건|달라질\s*수|확정",
                generated_body,
            ),
            "followup_guidance_present": _contains(
                r"문의|추가\s*설명|연락|이의|재신청|담당부서",
                generated_body,
            ),
            "responsible_party_or_contact_present": bool(responsible_units)
            or _contains(r"담당\s*부서|담당부서|[가-힣]{2,}과|[가-힣]{2,}팀|연락처|전화", generated_body),
            "special_complaint_process_present": special_process,
        }

    @staticmethod
    def _complaint_answer_overlap(complaint_text: str, generated_answer: str) -> float:
        complaint_terms = _keywords(complaint_text)
        if not complaint_terms:
            return 0.0
        answer_terms = _keywords(generated_answer)
        return len(complaint_terms & answer_terms) / len(complaint_terms)

    def _rule_baseline_raw(
        self,
        *,
        rule_features: dict[str, Any],
        manual_features: dict[str, Any],
        reference_count: int,
    ) -> dict[str, Any]:
        q_expected: dict[str, float] = {}
        debug_penalty = 0.8 if rule_features["debug_token_count"] else 0.0
        emotional_penalty = 1.4 if rule_features["emotional_response_flag"] else 0.0
        q_expected["q1"] = _clamp(3.4 - debug_penalty - emotional_penalty, 1.0, 4.0)

        if reference_count <= 0:
            q_expected["q2"] = 1.0
        elif reference_count == 1:
            q_expected["q2"] = 2.7
        elif reference_count <= 3:
            q_expected["q2"] = 3.2
        else:
            q_expected["q2"] = 3.5

        citation_rate = min(
            1.0,
            rule_features["postprocessed_citation_count"] / max(1, rule_features["claim_count"]),
        )
        q_expected["q3"] = 1.0 + 3.0 * citation_rate
        q_expected["q4"] = 1.0 + 3.0 * float(rule_features["citation_support_rate_strict"])

        priority = rule_features.get("source_priority_mean")
        if priority is None:
            q_expected["q5"] = 1.2 if reference_count else 1.0
        elif priority <= 1.5:
            q_expected["q5"] = 3.8
        elif priority <= 2.5:
            q_expected["q5"] = 3.4
        elif priority <= 3.5:
            q_expected["q5"] = 2.8
        else:
            q_expected["q5"] = 2.0
        if rule_features["best_source_missed_count"]:
            q_expected["q5"] -= 0.5

        q_expected["q6"] = _clamp(
            4.0
            - float(rule_features["repetition_ratio"]) * 2.0
            - min(1.2, rule_features["debug_token_count"] * 0.25)
            - float(rule_features["template_ratio"]) * 0.5,
            1.0,
            4.0,
        )

        length = int(rule_features["answer_token_length"])
        if length < 80:
            q_expected["q7"] = 1.8
        elif length < 180:
            q_expected["q7"] = 2.5
        elif length <= 1200:
            q_expected["q7"] = 3.5
        elif length <= 1800:
            q_expected["q7"] = 2.8
        else:
            q_expected["q7"] = 2.0

        core_missing = self._manual_core_missing_count(manual_features)
        q0_base = sum(q_expected[f"q{index}"] for index in range(1, 8)) / 7.0
        q0_base -= min(0.8, core_missing * 0.25)
        if rule_features["unsafe_promise_flag"]:
            q0_base = min(q0_base, 2.2)
        q_expected["q0"] = _clamp(q0_base, 1.0, 4.0)

        return {
            qid: _rubric_item(
                qid=qid,
                probs=_probs_from_expected(expected),
                source="rule_baseline",
                reason="Rule-derived baseline used as fallback and comparison signal.",
            )
            for qid, expected in q_expected.items()
        }

    @staticmethod
    def _manual_core_missing_count(manual_features: dict[str, Any]) -> int:
        core_keys = (
            "complaint_issue_identified",
            "judgment_or_answer_present",
            "legal_basis_present",
            "procedure_guidance_present",
            "followup_guidance_present",
        )
        return sum(1 for key in core_keys if manual_features.get(key) is False)

    def _apply_safety_layer(
        self,
        *,
        q0_score_0_10: float,
        rule_features: dict[str, Any],
        manual_features: dict[str, Any],
        generation_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        caps: list[tuple[float, str]] = []
        if int(rule_features["answer_token_length"]) <= 0:
            caps.append((0.0, "empty_answer"))
        if rule_features["debug_token_count"] >= 3:
            caps.append((3.0, "debug_or_metadata_leakage"))
        if not manual_features.get("complaint_issue_identified", True):
            caps.append((3.5, "complaint_misalignment"))
        if rule_features["unsafe_promise_flag"]:
            caps.append((4.0, "unsafe_promise"))
        if rule_features["postprocessed_citation_count"] <= 0:
            caps.append((4.0, "missing_citation"))
        if rule_features["emotional_response_flag"] and rule_features["special_complaint_flag"]:
            caps.append((4.5, "special_complaint_emotional_response"))
        if rule_features["legal_anchor_count"] == 0 and not manual_features.get("legal_basis_present", False):
            caps.append((5.0, "missing_legal_basis"))
        if (
            rule_features["special_complaint_flag"]
            and manual_features.get("special_complaint_process_present") is False
        ):
            caps.append((5.5, "special_complaint_process_missing"))
        if (
            generation_metadata.get("generation_mode") == "api_answer_fallback"
            or generation_metadata.get("fallback_used") is True
        ):
            caps.append((6.5, "fallback_answer"))

        if not caps:
            return {
                "cap_applied": False,
                "cap": None,
                "cap_reason": None,
                "final_q0_score_0_10": _round(q0_score_0_10, 2),
            }

        cap, reason = min(caps, key=lambda item: item[0])
        return {
            "cap_applied": q0_score_0_10 > cap,
            "cap": cap,
            "cap_reason": reason,
            "final_q0_score_0_10": _round(min(q0_score_0_10, cap), 2),
        }

    def _build_diagnostics(
        self,
        *,
        llm_raw: dict[str, Any],
        rule_features: dict[str, Any],
        manual_features: dict[str, Any],
        safety_layer: dict[str, Any],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if llm_raw["q2"]["expected_1_4"] < 2.5:
            reasons.append("retrieval_insufficient")
        if rule_features["postprocessed_citation_count"] <= 0:
            reasons.append("missing_citation")
        if llm_raw["q4"]["expected_1_4"] < 2.5:
            reasons.append("weak_citation_support")
        priority = rule_features.get("source_priority_mean")
        if priority is not None and priority > 3.0:
            reasons.append("suboptimal_source")
        if llm_raw["q1"]["expected_1_4"] < 2.5:
            reasons.append("tone_inappropriate")
        if rule_features["repetition_ratio"] > 0.15 or rule_features["debug_token_count"] > 0:
            reasons.append("redundant_or_template_answer")
        if manual_features.get("procedure_guidance_present") is False:
            reasons.append("incomplete_procedure_guidance")
        if manual_features.get("legal_basis_present") is False:
            reasons.append("missing_legal_basis")
        if rule_features["unsafe_promise_flag"]:
            reasons.append("unsafe_promise")
        if rule_features["emotional_response_flag"]:
            reasons.append("emotional_response")
        if (
            rule_features["special_complaint_flag"]
            and manual_features.get("special_complaint_process_present") is False
        ):
            reasons.append("special_complaint_safety_missing")
        if rule_features["debug_token_count"] > 0:
            reasons.append("debug_or_metadata_leakage")

        reasons = list(dict.fromkeys(reasons))
        recommended_fix = [RISK_FIXES[reason] for reason in reasons if reason in RISK_FIXES]
        final_q0 = float(safety_layer["final_q0_score_0_10"])
        human_review_required = (
            final_q0 < 5.0
            or bool(safety_layer["cap_applied"])
            or llm_raw["q4"]["expected_1_4"] < 2.5
            or llm_raw["q7"]["expected_1_4"] < 2.5
            or self._manual_core_missing_count(manual_features) >= 2
            or bool(rule_features["unsafe_promise_flag"])
        )

        return {
            "main_failure_reasons": reasons,
            "recommended_fix": recommended_fix,
            "human_review_required": human_review_required,
            "manual_completeness_core_missing_count": self._manual_core_missing_count(
                manual_features
            ),
        }

    @staticmethod
    def _judge_status(*, can_call_llm: bool, llm_errors: list[str]) -> str:
        if not can_call_llm:
            return "rule_fallback"
        if llm_errors:
            return "llm_judge_partial_with_rule_fallback"
        return "llm_judge"

    @staticmethod
    def _probability_source(judge_status: str) -> str:
        if judge_status == "llm_judge":
            return "synthetic_from_llm_choice_confidence"
        if judge_status == "llm_judge_partial_with_rule_fallback":
            return "mixed_synthetic_llm_and_rule_baseline"
        return "rule_baseline_distribution"


_evaluator: CivilComplaintRubricEvaluator | None = None


def get_civil_llm_rubric_evaluator() -> CivilComplaintRubricEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = CivilComplaintRubricEvaluator()
    return _evaluator
