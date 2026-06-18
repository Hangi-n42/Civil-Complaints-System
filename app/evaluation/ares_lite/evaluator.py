"""Deterministic ARES-lite evaluator for civil complaint RAG outputs."""

from __future__ import annotations

import re
from statistics import fmean
from typing import Any

from app.evaluation.ares_lite.schemas import AresLiteCase, AresLiteContext

RUBRIC_CONNECTIONS = {
    "context_relevance": ["q2.reference_adequacy", "retrieval_failure_diagnostic"],
    "answer_faithfulness": ["q2.reference_adequacy", "q4.citation_support", "semantic_risk_flags"],
    "answer_relevance": ["q0.overall_quality", "manual_completeness_features", "q7.conciseness_if_overlong"],
}

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")
SENTENCE_RE = re.compile(r"[^.!?\n。！？]+[.!?。！？]?")
BODY_RE = re.compile(
    r"(?:^|\n|\s)3[.．)]\s*검토\s*의견은\s*다음과\s*같습니다[.。]?\s*(.*?)(?:\n\s*\n?\s*4[.．)]|\Z)",
    flags=re.DOTALL,
)

STOP_TERMS = {
    "귀하",
    "민원",
    "내용",
    "검토",
    "답변",
    "관련",
    "대한",
    "다음",
    "같습니다",
    "신청",
    "문의",
    "사항",
    "처리",
    "확인",
    "안내",
    "드립니다",
    "있습니다",
    "합니다",
    "경우",
    "담당부서",
    "추가",
    "설명",
    "필요",
    "후속",
    "감사합니다",
}

DOMAIN_KEYWORDS = {
    "도로",
    "보도",
    "교통",
    "주차",
    "불법",
    "위험",
    "안전",
    "소음",
    "쓰레기",
    "악취",
    "수도",
    "가로등",
    "공원",
    "시설",
    "버스",
    "택시",
    "자전거",
    "공사",
    "보수",
    "철거",
    "설치",
    "단속",
}

CLAIM_RE = re.compile(
    r"법|조례|규정|지침|제\s*\d+\s*조|담당\s*부서|"
    r"[가-힣A-Za-z]*(?:도로|교통|청소|건축|복지|환경|안전|행정|관리|수도|녹지|공원|주차)[가-힣A-Za-z]*과|"
    r"[가-힣A-Za-z]{2,}(?:팀|센터|공단|사업소)|"
    r"완료|예정|즉시|다음\s*주|이번\s*주|연내|상반기|하반기|"
    r"조치|설치|철거|보수|정비|단속|폐쇄|이전|신설|허가|승인|불가|가능|현장\s*확인"
)
STRONG_UNSUPPORTED_RE = re.compile(
    r"완료되었습니다|이미\s*완료|즉시\s*(?:조치|처리|시행)|다음\s*주까지|이번\s*주까지|"
    r"반드시|확정되었습니다|개최할\s*예정입니다|설치하겠습니다|철거하겠습니다|단속하겠습니다"
)
LAW_RE = re.compile(r"「[^」]+」|[가-힣A-Za-z]+법\s*제?\s*\d+\s*조|조례\s*제?\s*\d+\s*조")
DEPARTMENT_RE = re.compile(
    r"[가-힣A-Za-z]*(?:도로|교통|청소|건축|복지|환경|안전|행정|관리|수도|녹지|공원|주차)[가-힣A-Za-z]*과|"
    r"[가-힣A-Za-z]{2,}(?:팀|센터|공단|사업소)"
)
SCHEDULE_RE = re.compile(r"\d{4}\s*년|\d{1,2}\s*월|\d{1,2}\s*일|다음\s*주|이번\s*주|연내|상반기|하반기|예정")


class AresLiteEvaluator:
    """Evaluate context relevance, answer faithfulness, and answer relevance."""

    def evaluate(self, case: AresLiteCase | dict[str, Any]) -> dict[str, Any]:
        normalized = case if isinstance(case, AresLiteCase) else AresLiteCase.from_mapping(case)
        context_result = self.evaluate_context_relevance(normalized)
        faithfulness_result = self.evaluate_answer_faithfulness(normalized)
        relevance_result = self.evaluate_answer_relevance(normalized)

        overall = _round_score(
            0.30 * context_result["average_score"]
            + 0.40 * faithfulness_result["score"]
            + 0.30 * relevance_result["score"]
        )
        recommended_revision = self._recommended_revision(
            context_result=context_result,
            faithfulness_result=faithfulness_result,
            relevance_result=relevance_result,
        )

        return {
            "case_id": normalized.case_id,
            "ares_lite": {
                "overall_score": overall,
                "risk_level": _risk_level(
                    overall=overall,
                    context_score=context_result["average_score"],
                    faithfulness_score=faithfulness_result["score"],
                    relevance_score=relevance_result["score"],
                    unsupported_claims=faithfulness_result["unsupported_claims"],
                    missing_segments=relevance_result["missing_segments"],
                ),
                "context_relevance": context_result,
                "answer_faithfulness": faithfulness_result,
                "answer_relevance": relevance_result,
                "recommended_revision": recommended_revision,
                "rubric_connections": RUBRIC_CONNECTIONS,
                "evaluation_scope": {
                    "mode": "ares_lite_rule",
                    "llm_judge_used": False,
                    "note": "초기 구현은 문서 기준 ARES-lite 오프라인 평가이며, 선택적 LLM judge는 후속 확장 지점입니다.",
                },
                "weights": {
                    "context_relevance": 0.30,
                    "answer_faithfulness": 0.40,
                    "answer_relevance": 0.30,
                },
            },
        }

    def evaluate_context_relevance(self, case: AresLiteCase) -> dict[str, Any]:
        query_tokens = _tokens(case.query)
        segments = _segments(case)
        context_scores = [
            self._score_context(context, query_tokens=query_tokens, segments=segments)
            for context in case.retrieved_contexts
        ]
        average_score = _round_score(fmean(item["score"] for item in context_scores)) if context_scores else 0.0
        low_contexts = [
            {
                "context_id": item["context_id"],
                "score": item["score"],
                "reason": item["reason"],
            }
            for item in context_scores
            if item["score"] < 5.0
        ]
        return {
            "metric": "context_relevance",
            "average_score": average_score,
            "label": _label_context(average_score),
            "contexts": context_scores,
            "low_relevance_contexts": low_contexts,
        }

    def evaluate_answer_faithfulness(self, case: AresLiteCase) -> dict[str, Any]:
        answer_body = extract_generated_body(case.generated_answer)
        evidence_text = _evidence_text(case)
        evidence_tokens = _tokens(evidence_text)
        sentences = _claim_sentences(answer_body)

        if not answer_body:
            return {
                "metric": "answer_faithfulness",
                "score": 0.0,
                "label": "empty_answer",
                "unsupported_claims": [],
                "supported_claim_count": 0,
                "claim_count": 0,
                "revision_hint": "답변 본문을 생성해야 합니다.",
            }
        if not sentences:
            base_score = 5.0 if evidence_tokens else 3.0
            return {
                "metric": "answer_faithfulness",
                "score": base_score,
                "label": _label_faithfulness(base_score),
                "unsupported_claims": [],
                "supported_claim_count": 0,
                "claim_count": 0,
                "revision_hint": "근거로 확인 가능한 구체 검토 의견을 추가하세요.",
            }

        unsupported: list[dict[str, str]] = []
        supported_count = 0
        for sentence in sentences:
            supported, reason = _is_supported(sentence, evidence_text, evidence_tokens)
            if supported:
                supported_count += 1
            else:
                unsupported.append({"sentence": sentence, "reason": reason})

        supported_rate = supported_count / len(sentences)
        high_risk_count = sum(1 for item in unsupported if STRONG_UNSUPPORTED_RE.search(item["sentence"]))
        score = 10.0 * supported_rate
        score -= min(3.0, high_risk_count * 1.25)
        if not case.citations and sentences:
            score = min(score, 6.0)
        if not evidence_tokens:
            score = min(score, 3.0)
        score = _round_score(score)
        return {
            "metric": "answer_faithfulness",
            "score": score,
            "label": _label_faithfulness(score),
            "unsupported_claims": unsupported,
            "supported_claim_count": supported_count,
            "claim_count": len(sentences),
            "revision_hint": _faithfulness_hint(unsupported),
        }

    def evaluate_answer_relevance(self, case: AresLiteCase) -> dict[str, Any]:
        answer_body = extract_generated_body(case.generated_answer)
        answer_tokens = _tokens(answer_body)
        query_tokens = _tokens(case.query)
        segments = _segments(case)

        if not answer_body:
            return {
                "metric": "answer_relevance",
                "score": 0.0,
                "label": "empty_answer",
                "covered_segments": [],
                "missing_segments": segments,
                "missing_points": segments,
                "revision_hint": "민원 핵심 요청에 직접 답하는 본문을 작성해야 합니다.",
            }

        covered_segments = []
        missing_segments = []
        for segment in segments:
            if _segment_is_covered(segment, answer_tokens):
                covered_segments.append(segment)
            else:
                missing_segments.append(segment)

        segment_score = len(covered_segments) / len(segments) if segments else 0.0
        query_coverage = _coverage(query_tokens, answer_tokens)
        score = _round_score(10.0 * (0.70 * segment_score + 0.30 * query_coverage))
        return {
            "metric": "answer_relevance",
            "score": score,
            "label": _label_relevance(score),
            "covered_segments": covered_segments,
            "missing_segments": missing_segments,
            "missing_points": missing_segments,
            "query_token_coverage": round(query_coverage, 4),
            "revision_hint": _relevance_hint(missing_segments),
        }

    def _score_context(
        self,
        context: AresLiteContext,
        *,
        query_tokens: set[str],
        segments: list[str],
    ) -> dict[str, Any]:
        context_tokens = _tokens(context.content)
        token_coverage = _coverage(query_tokens, context_tokens)
        segment_coverage = _segment_coverage(segments, context_tokens)
        keyword_overlap = _coverage(query_tokens & DOMAIN_KEYWORDS, context_tokens & DOMAIN_KEYWORDS)
        score = _round_score(10.0 * (0.60 * token_coverage + 0.30 * segment_coverage + 0.10 * keyword_overlap))
        reason = (
            f"query_token_coverage={token_coverage:.2f}, "
            f"segment_coverage={segment_coverage:.2f}, "
            f"domain_keyword_overlap={keyword_overlap:.2f}"
        )
        return {
            "metric": "context_relevance",
            "context_id": context.context_id,
            "score": score,
            "label": _label_context(score),
            "rank": context.rank,
            "retrieval_score": context.score,
            "reason": reason,
        }

    @staticmethod
    def _recommended_revision(
        *,
        context_result: dict[str, Any],
        faithfulness_result: dict[str, Any],
        relevance_result: dict[str, Any],
    ) -> list[str]:
        recommendations: list[str] = []
        if context_result["average_score"] < 5.0:
            recommendations.append("검색 query 또는 router를 보강해 민원 핵심 이슈와 직접 관련된 근거를 확보하세요.")
        if faithfulness_result["unsupported_claims"]:
            recommendations.append("근거 없는 일정, 조치 완료, 담당 부서, 법령 단정 표현을 완화하거나 citation으로 뒷받침하세요.")
        if faithfulness_result["score"] < 6.0 and not faithfulness_result["unsupported_claims"]:
            recommendations.append("답변의 주요 사실 주장마다 검색 근거 또는 citation 연결을 보강하세요.")
        if relevance_result["missing_segments"]:
            recommendations.append("누락된 하위 민원 이슈에 대한 조치 방향 또는 담당 부서 검토 안내를 추가하세요.")
        if not recommendations:
            recommendations.append("큰 수정 필요성은 낮지만, citation과 후속 절차 표현을 최종 확인하세요.")
        return recommendations


def extract_generated_body(text: str) -> str:
    rendered = str(text or "").strip()
    if not rendered:
        return ""
    match = BODY_RE.search(rendered)
    if match:
        return match.group(1).strip()
    return rendered


def _tokens(text: str) -> set[str]:
    tokens = set()
    for token in TOKEN_RE.findall(str(text or "")):
        normalized = _normalize_token(token)
        if normalized and normalized not in STOP_TERMS and len(normalized) >= 2:
            tokens.add(normalized)
    return tokens


def _normalize_token(token: str) -> str:
    normalized = token.lower().strip()
    suffixes = (
        "드리겠습니다",
        "하겠습니다",
        "했습니다",
        "됩니다",
        "입니다",
        "합니다",
        "드립니다",
        "으로",
        "에서",
        "에게",
        "께서",
        "까지",
        "부터",
        "이며",
        "이고",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "과",
        "와",
        "도",
        "에",
        "의",
    )
    for suffix in suffixes:
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            return normalized[: -len(suffix)]
    return normalized


def _coverage(source_tokens: set[str], target_tokens: set[str]) -> float:
    if not source_tokens:
        return 0.0
    return len(source_tokens & target_tokens) / len(source_tokens)


def _segments(case: AresLiteCase) -> list[str]:
    if case.request_segments:
        return case.request_segments
    query = str(case.query or "").strip()
    if not query:
        return []
    parts = [query]
    for delimiter in (" 그리고 ", " 및 ", ",", ";", "\n"):
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend(part.split(delimiter))
        parts = next_parts
    return [part.strip() for part in parts if part.strip()] or [query]


def _segment_is_covered(segment: str, answer_tokens: set[str]) -> bool:
    segment_tokens = _tokens(segment)
    if not segment_tokens:
        return False
    overlap = len(segment_tokens & answer_tokens)
    return overlap >= 2 or overlap / len(segment_tokens) >= 0.35


def _segment_coverage(segments: list[str], target_tokens: set[str]) -> float:
    if not segments:
        return 0.0
    covered = sum(1 for segment in segments if _segment_is_covered(segment, target_tokens))
    return covered / len(segments)


def _evidence_text(case: AresLiteCase) -> str:
    context_text = "\n".join(context.content for context in case.retrieved_contexts)
    citation_text = "\n".join(citation.quote for citation in case.citations)
    return f"{context_text}\n{citation_text}".strip()


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_RE.findall(str(text or "")) if sentence.strip()]


def _claim_sentences(answer_body: str) -> list[str]:
    return [
        sentence
        for sentence in _sentences(answer_body)
        if len(_tokens(sentence)) >= 3 and CLAIM_RE.search(sentence)
    ]


def _is_supported(sentence: str, evidence_text: str, evidence_tokens: set[str]) -> tuple[bool, str]:
    if not evidence_tokens:
        return False, "검색 context 또는 citation 근거가 없어 주장을 확인할 수 없음"
    sentence_tokens = _tokens(sentence)
    overlap = _coverage(sentence_tokens, evidence_tokens)

    if STRONG_UNSUPPORTED_RE.search(sentence) and overlap < 0.55:
        return False, "처리 완료, 일정, 즉시 조치 등 강한 행정 약속을 뒷받침하는 근거가 부족함"
    if LAW_RE.search(sentence) and not _pattern_text_supported(LAW_RE, sentence, evidence_text):
        return False, "법령 또는 조문 언급이 검색 근거에서 확인되지 않음"
    if SCHEDULE_RE.search(sentence) and not _pattern_text_supported(SCHEDULE_RE, sentence, evidence_text):
        return False, "처리 일정 또는 예정 표현이 검색 근거에서 확인되지 않음"
    if DEPARTMENT_RE.search(sentence) and not _pattern_text_supported(DEPARTMENT_RE, sentence, evidence_text):
        return False, "담당 부서 또는 기관명이 검색 근거에서 확인되지 않음"
    if overlap >= 0.35:
        return True, "주요 표현이 검색 근거와 충분히 겹침"
    if overlap >= 0.22 and re.search(r"검토|확인|안내|필요|가능\s*여부", sentence):
        return True, "조건부 검토 표현이며 일부 근거와 연결됨"
    return False, f"검색 근거와의 토큰 겹침이 낮음(overlap={overlap:.2f})"


def _pattern_text_supported(pattern: re.Pattern[str], sentence: str, evidence_text: str) -> bool:
    sentence_values = {match.group(0).replace(" ", "") for match in pattern.finditer(sentence)}
    evidence_values = {match.group(0).replace(" ", "") for match in pattern.finditer(evidence_text)}
    return bool(sentence_values & evidence_values)


def _faithfulness_hint(unsupported_claims: list[dict[str, str]]) -> str:
    if not unsupported_claims:
        return "주요 주장과 citation 연결을 유지하세요."
    return "확정적 표현은 '현장 확인 후 검토/안내'처럼 근거 범위 안의 조건부 표현으로 수정하세요."


def _relevance_hint(missing_segments: list[str]) -> str:
    if not missing_segments:
        return "민원 핵심 요청에 대체로 대응하고 있습니다."
    return "누락된 이슈를 답변 본문에 반영하세요: " + "; ".join(missing_segments[:3])


def _round_score(value: float) -> float:
    return round(max(0.0, min(10.0, float(value))), 1)


def _label_context(score: float) -> str:
    if score >= 8.5:
        return "highly_relevant"
    if score >= 7.0:
        return "relevant"
    if score >= 5.0:
        return "partially_relevant"
    if score >= 3.0:
        return "weakly_relevant"
    return "irrelevant"


def _label_faithfulness(score: float) -> str:
    if score >= 8.5:
        return "grounded"
    if score >= 7.0:
        return "mostly_grounded"
    if score >= 5.0:
        return "partially_grounded"
    return "ungrounded"


def _label_relevance(score: float) -> str:
    if score >= 8.5:
        return "directly_answers"
    if score >= 7.0:
        return "mostly_relevant"
    if score >= 5.0:
        return "partially_relevant"
    return "misses_request"


def _risk_level(
    *,
    overall: float,
    context_score: float,
    faithfulness_score: float,
    relevance_score: float,
    unsupported_claims: list[dict[str, str]],
    missing_segments: list[str],
) -> str:
    if overall < 5.0 or faithfulness_score < 5.0 or len(unsupported_claims) >= 2:
        return "high"
    if overall < 7.0 or context_score < 5.0 or relevance_score < 6.0 or unsupported_claims or missing_segments:
        return "medium"
    return "low"
