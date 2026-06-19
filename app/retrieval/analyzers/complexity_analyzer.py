from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Literal

ComplexityLevel = Literal["low", "medium", "high"]

# Score -> level thresholds are split as constants for stable tuning.
COMPLEXITY_LEVEL_MEDIUM_THRESHOLD = 0.45
COMPLEXITY_LEVEL_HIGH_THRESHOLD = 0.75
MAX_REQUEST_SEGMENTS = 6
_KSS_SPLITTER_UNSET = object()
_KSS_SENTENCE_SPLITTER: Callable[..., object] | None | object = _KSS_SPLITTER_UNSET

_CONSTRAINT_TOKENS = (
    "기한",
    "예산",
    "규정",
    "절차",
    "우선순위",
    "근거",
    "조건",
)
_POLICY_TOKENS = ("법", "법령", "시행령", "조례", "규칙", "고시")
_ENTITY_TOKENS = (
    "기관",
    "부서",
    "주민",
    "사업자",
    "지자체",
    "담당자",
    "시설",
    "도로",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|[\r\n]+")
_SEMANTIC_SPLIT_PATTERNS = (
    re.compile(r"\s*(?:그리고|또한|아울러|동시에)\s*"),
    re.compile(r"\s*,\s*"),
    re.compile(r"\s*;\s*"),
    re.compile(r"\s*/\s*"),
    re.compile(r"\s+및\s+"),
    re.compile(r"(?<=(?:요청|문의|신고|건의))(?:과|와)\s+"),
)
_ADMIN_ACTION_RE = re.compile(
    r"(?:접수|전달|배정|검토|확인|조치|처리|안내|답변).{0,16}"
    r"(?:했습니다|하겠습니다|드립니다|드렸습니다|예정입니다|예정|완료|되었습니다)"
)
_REQUEST_INTENT_PATTERNS = (
    re.compile(
        r"(?:요청|문의|질의|신고|건의)"
        r"(?:합니다|드립니다|드려요|드리고|하고|입니다|$)"
    ),
    re.compile(
        r"(?:부탁드립니다|바랍니다|해\s*주세요|해\s*주십시오|해\s*주시기 바랍니다|해\s*주시고)"
    ),
    re.compile(
        r"(?:조치|점검|보수|수리|설치|교체|제거|단속|개선|확인|검토|처리|조사|복구|시정|안내|답변|공개|제공|연장|확대|감면|지원)"
        r".{0,24}(?:부탁|바랍니다|요청|해\s*주세요|해\s*주십시오|해\s*주시|필요합니다)"
    ),
    re.compile(r"(?:알려\s*주세요|알려\s*주시|답변.{0,12}(?:주세요|바랍니다|부탁)|궁금합니다)"),
    re.compile(
        r"(?:언제|어떻게|어디(?:서|에)?|무엇|가능한지|여부|일정|절차|방법)"
        r".{0,32}(?:\?|인가요|나요|습니까|문의|궁금|알려)"
    ),
)
_REQUEST_ACTION_TOKENS = (
    "조치",
    "점검",
    "보수",
    "수리",
    "설치",
    "교체",
    "제거",
    "단속",
    "개선",
    "개최",
    "확인",
    "검토",
    "처리",
    "조사",
    "보충",
    "복구",
    "시정",
    "안내",
    "답변",
    "공개",
    "제공",
    "연장",
    "확대",
    "부과",
    "감면",
    "지원",
)
_REQUEST_OBJECT_TOKENS = (
    "도로",
    "보도",
    "인도",
    "포트홀",
    "불법주정차",
    "주정차",
    "주차",
    "가로등",
    "보안등",
    "공원",
    "하천",
    "하수",
    "악취",
    "쓰레기",
    "폐기물",
    "쓰레기통",
    "환경미화",
    "인력",
    "울타리",
    "안내판",
    "버스",
    "정류장",
    "노선",
    "어린이집",
    "장애인",
    "임대주택",
    "공동주택",
)
_SHARED_REQUEST_PREDICATE_RE = re.compile(
    r"^(?P<body>.+?)(?:을|를)?\s*"
    r"(?P<predicate>(?:요청|문의|질의|신고|건의)(?:합니다|드립니다|드려요|드리고|하고|하니|입니다)?"
    r"|(?:해\s*주세요|해\s*주십시오|바랍니다))(?P<suffix>[.!?。！？]*)$"
)
_SHARED_REQUEST_SPLIT_RE = re.compile(r"\s*(?:그리고|및|과|와)\s*")
_COMPACT_REQUEST_LIST_SPLIT_RE = re.compile(r"\s*,\s*")
_ENUMERATED_ITEM_RE = re.compile(
    r"(?:^|\s)(?:[1-9][.),]|[①②③④⑤⑥⑦⑧⑨⑩]|(?:질의|문의|질문)\s*[1-9][.),]?)\s*"
)
_ENUMERATED_PREFIX_RE = re.compile(
    r"^(?:[1-9][.),]|[①②③④⑤⑥⑦⑧⑨⑩]|(?:질의|문의|질문)\s*[1-9][.),]?)\s*"
)
_BARE_ENUMERATED_MARKER_RE = re.compile(r"^(?:[1-9][.),]|[①②③④⑤⑥⑦⑧⑨⑩])$")
_TITLE_Q_PREFIX_RE = re.compile(r"^(?:제목\s*[:：]\s*)?.{0,90}?\bQ\s*[:：]\s*")
_TITLE_GREETING_PREFIX_RE = re.compile(
    r"^.{0,90}?(?:안녕하십니까|안녕하세요|수고가 많으십니다)[.!?。！？]?\s*"
)
_DIALOGUE_SPEAKER_PREFIX_RE = re.compile(r"^(?:고객|상담원|민원인|상담사)\s*[:：]\s*")
_CLOSING_ONLY_RE = re.compile(
    r"(?:감사드립니다|감사합니다|좋은 하루|더위 조심|협조에 깊이 감사|답변을 기다리|"
    r"긍정적인 답변|참여 부탁|만족도 평가 부탁)"
)
_GENERIC_CLOSING_REQUEST_RE = re.compile(
    r"(?:멋진|훌륭한|좋은).{0,25}(?:시장|도지사|공무원|담당자).{0,25}되어\s*주시"
)
_ANSWER_FORM_ONLY_RE = re.compile(
    r"(?:(?:반드시|직접).{0,25}답변.{0,25}(?:요청|부탁|바랍니다|주시)|"
    r"답변은.{0,40}(?:지양|삼가).{0,25}(?:바랍니다|주시))"
)
_FACTUAL_CONTEXT_RE = re.compile(r"(?:알고 있습니다|문의하니|문의하였|확인하였습니다|상황입니다|예정입니다)")
_PAST_FACT_ONLY_RE = re.compile(r"(?:신고|등록|신청|접수)(?:하였|했|되어 있|되었습니다|했습니다)")
_REQUEST_END_RE = re.compile(
    r"(?:요청드립니다|요청합니다|문의드립니다|질의합니다|신고합니다|건의합니다|"
    r"부탁드립니다|바랍니다|해\s*주세요|해\s*주십시오|궁금합니다|알려\s*주세요)[.!?。！？]?$"
)
_LOW_INFORMATION_REQUEST_RE = re.compile(r"^(?:라고 되어 있는데|[0-9]+번에 관한|상기 사항에 대해)?\s*질의입니다[.!?。！？]?$")
_GENERIC_REQUEST_ONLY_RE = re.compile(
    r"^(?:(?:이|그|본)\s*경우|아래\s*사항(?:을)?|상기\s*사항(?:을)?|이에\s*대해|관련하여)?\s*"
    r"(?:문의|질의|요청)(?:드립니다|합니다|바랍니다)?[.!?。！？]?$"
)
_GENERIC_ACTION_ONLY_RE = re.compile(
    r"^(?:빠른\s*시간\s*내\s*)?(?:신속한\s*)?(?:대응|처리|검토|응답|답변|확인|"
    r"살펴보도록|알려)\s*(?:해\s*주세요|하여\s*주시기\s*바랍니다|부탁드립니다|요청드립니다|바랍니다)?[.!?。！？~]*$"
)
_REDACTION_ONLY_RE = re.compile(r"^[▲△○□◇\s]+(?:요청|문의|질의|신고|건의|부탁|바랍니다|드립니다).*$")
_DIRECTION_PAIR_RE = re.compile(r"(?:남쪽|북쪽|동쪽|서쪽|좌측|우측)\s*,\s*(?:남쪽|북쪽|동쪽|서쪽|좌측|우측)")
_QUESTION_LIKE_SEGMENT_RE = re.compile(r"(?:\?|궁금|문의|질의|가능한지|여부|무엇|어떤|어떻게|왜|이유)")
_BACKGROUND_GUARD_TOKENS = (
    "때문",
    "위험",
    "불편",
    "피해",
    "파손",
    "고장",
    "발생",
    "심합니다",
    "쌓이고",
    "꺼져",
    "넘어질",
)
_BACKGROUND_ONLY_RE = re.compile(
    r"(?:불편|위험|피해|문제|파손|고장|막히|흔들리|어렵|힘듭|많습니다|있습니다|발생)"
)
_KOREAN_REQUEST_INTENT_RE = re.compile(
    r"(?:"
    r"(?:문의|질의|요청|신고|건의|신청).{0,80}(?:\?|요|지요|나요|까요|습니까|니까|드립니다|합니다|바랍니다|주세요|부탁)"
    r"|(?:알려|알고\s*싶|궁금).{0,80}(?:\?|요|지요|나요|까요|습니까|니까|니다|바랍니다|주세요|부탁|싶습니다)"
    r"|(?:어떻게|언제|어디|왜|무엇|어떤|여부|근거|이유|절차|방법|일정|시기|금액|예산|가능|되는지|있는지|수\s*있는지).{0,80}(?:\?|요|지요|나요|까요|습니까|니까|궁금|알려|싶습니다)"
    r"|(?:확인|검토|조치|설치|보수|개선|시정|철거|단속|지원|안내).{0,40}(?:부탁|바랍니다|주세요|주십시오|요청)"
    r")"
)
_KOREAN_NOMINAL_QUESTION_RE = re.compile(
    r"^[^.!。！]{2,90}(?:대상|마을|구간|방법|서류|절차|요건|금액|기간|기준|근거|범위|내용|서비스|사업|계획)"
    r"(?:은|는|이|가|인가요|인가|인지요)?[?？]$"
)
_INCOMPLETE_ENUMERATED_REQUEST_HEAD_RE = re.compile(
    r"^(?:[1-9][.),]|[①②③④⑤⑥⑦⑧⑨⑩])\s*[^.!?。！]{2,90}"
    r"(?:대상|마을|구간|방법|서류|절차|요건|금액|기간|기준|근거|범위|내용|서비스|사업|계획|지원|제작|등록|신고|허가)$"
)
_POLITE_REQUEST_TAIL_RE = re.compile(
    r"^(?:안내|알려|답변|설명|확인).{0,24}(?:주시면|주세요|부탁|바랍니다|감사)"
)
_OBJECTED_POLITE_REQUEST_RE = re.compile(
    r"^[^.!?。！]{2,120}(?:대상|마을|구간|방법|서류|절차|요건|금액|기간|기준|근거|범위|내용|서비스|사업|계획|지원|제작|등록|신고|허가)"
    r".{0,36}(?:안내|알려|답변|설명|확인).{0,36}(?:주시면|주세요|부탁|바랍니다|감사)"
)
_BROAD_INTRO_REQUEST_RE = re.compile(
    r"^.{0,120}(?:어떤|무엇|어느|어디서|어떻게).{0,60}(?:지원|상담|안내|도움).{0,36}(?:받고\s*싶|궁금|문의)"
)
_POLITE_CLOSING_ONLY_RE = re.compile(
    r"^(?:그럼\s*)?(?:바쁘시더라도\s*)?(?:이상\s*(?:세|두|몇)?\s*가지\s*)?"
    r"(?:빠른\s*)?(?:정확한\s*)?(?:적극적(?:인)?\s*)?"
    r"(?:(?:답변|회신|도움(?:\s*말씀)?|처리|검토|조치|행정|답변과\s*조치|궁금점(?:을)?\s*해소)\s*)?"
    r"\s*(?:부탁(?:드리겠습니다|드립니다|드릴게요|합니다)?|바랍니다|주세요|주십시오|드릴게요)[.!?。！？]*$"
)
_ANSWER_NOTICE_ONLY_RE = re.compile(
    r"^(?:문의하신|질의하신|요청하신).{0,40}(?:확인|검토|안내).{0,16}(?:드립니다|드리겠습니다)[.!?。！？]*$"
)
_GENERIC_CURIOSITY_ONLY_RE = re.compile(r"^(?:궁금합니다|궁금합니다만|궁금합니다\.)[.!?。！？]*$")
_GENERIC_INQUIRY_INTRO_RE = re.compile(
    r"^.{0,90}(?:관련|관해|대하여|대한).{0,24}(?:문의|질의)(?:드립니다|합니다|입니다)[.!?。！？]*$"
)
_GENERIC_INQUIRY_HEADING_RE = re.compile(
    r"^.{2,70}(?:관련\s*)?(?:문의|질의|질문)(?:드립니다|합니다)?[.!?。！？]*$"
)
_LOW_VALUE_CLOSING_SEGMENT_RE = re.compile(
    r"^(?:정말\s*)?(?:미리\s*)?(?:신경\s*써\s*주심을\s*)?(?:부탁드립니다|참고(?:하시길|해\s*주시기)?\s*바랍니다)[.!?。！？]*$"
)
_ATTACHMENT_REFERENCE_RE = re.compile(
    r"^(?:관련\s*)?(?:제품|자료|파일|제원|첨부).{0,40}(?:첨부|참고).{0,36}(?:바랍니다|주시기\s*바랍니다)[.!?。！？]*$"
)
_LOW_VALUE_REFERENCE_SEGMENT_RE = re.compile(
    r"^.{0,24}(?:참고하시길|참고해\s*주시기|참고)\s*바랍니다[.!?。！？]*$"
)
_LIST_CONTEXT_FRAGMENT_RE = re.compile(r"(?:후|이후|관련)$")
_GENERIC_TITLE_CONTENT_TERMS = {
    "관련",
    "관련한",
    "문의",
    "질의",
    "질문",
    "사항",
    "내용",
    "절차",
    "안내",
    "요청",
    "방법",
}
_GENERIC_CLOSING_CONTENT_TERMS = {
    "그럼",
    "빠른",
    "빠르",
    "정확한",
    "정확",
    "적극적",
    "적극적인",
    "적극",
    "답변",
    "회신",
    "도움",
    "말씀",
    "처리",
    "검토",
    "조치",
    "행정",
    "부탁",
    "부탁드립니다",
    "부탁드리겠습니다",
    "부탁드릴게요",
    "이상",
    "세",
    "두",
    "몇",
    "가지",
    "궁금점",
    "해소",
    "바쁘시더라",
    "바쁘시더라도",
}
_SIGNATURE_STOPWORDS = {
    "안녕하세요",
    "안녕하십니까",
    "수고",
    "많으십니다",
    "부탁드립니다",
    "바랍니다",
    "해주세요",
    "주십시오",
    "드립니다",
    "합니다",
    "이에",
    "위해",
    "대한",
    "관련",
    "경우",
    "내용",
    "민원",
    "무엇",
    "어떻게",
    "어디",
    "언제",
    "이유",
    "여부",
    "궁금",
    "관련",
}
_ACTION_SIGNATURE_TOKENS = (
    "요청",
    "문의",
    "질의",
    "신고",
    "건의",
    "신청",
    "부탁",
    "바랍니다",
    "주세요",
    "주십시오",
    *_REQUEST_ACTION_TOKENS,
)
_REPEATED_SINGLE_ISSUE_TERMS = {"사회자"}
_GENERIC_QUESTION_CONTENT_TERMS = {
    "가능",
    "기준",
    "방법",
    "절차",
    "처리",
    "신청",
    "사항",
    "합병",
}


@dataclass(frozen=True)
class ComplexityAnalysis:
    complexity_score: float
    complexity_level: ComplexityLevel
    intent_count: int
    constraint_count: int
    entity_diversity: int
    policy_reference_count: int
    complexity_trace: dict


@dataclass(frozen=True)
class RequestSegmentAnalysis:
    segments: list[str]
    sentence_splitter: str
    sentence_count: int
    candidate_count: int
    dropped_background_count: int
    dropped_admin_action_count: int
    shared_predicate_split_count: int
    fallback_used: bool
    truncated: bool
    boundary_used: bool = False
    title_segment_count: int = 0
    question_segment_count: int = 0
    title_duplicate_dropped_count: int = 0

    def trace(self) -> dict:
        return {
            "segment_count": len(self.segments),
            "sentence_splitter": self.sentence_splitter,
            "sentence_count": self.sentence_count,
            "segment_candidate_count": self.candidate_count,
            "dropped_background_count": self.dropped_background_count,
            "dropped_admin_action_count": self.dropped_admin_action_count,
            "shared_predicate_split_count": self.shared_predicate_split_count,
            "fallback_segment_used": self.fallback_used,
            "segment_limit": MAX_REQUEST_SEGMENTS,
            "segment_limit_applied": self.truncated,
            "title_question_boundary_used": self.boundary_used,
            "title_segment_count": self.title_segment_count,
            "question_segment_count": self.question_segment_count,
            "title_duplicate_dropped_count": self.title_duplicate_dropped_count,
        }


def build_analyzer_output(
    text: str,
    topic_type: str = "general",
    *,
    title: str | None = None,
    question: str | None = None,
) -> dict:
    analysis = _DEFAULT_ANALYZER.analyze(text=text, topic_type=topic_type)
    cleaned = str(text or "").strip()
    segment_analysis = _analyze_request_segments(cleaned, title=title, question=question)
    request_segments = segment_analysis.segments
    intent_count = len(request_segments) if request_segments else 0
    complexity_trace = dict(analysis.complexity_trace)
    complexity_trace["intent_count"] = intent_count
    complexity_trace.update(segment_analysis.trace())

    return {
        "topic_type": analysis.complexity_trace.get("topic_type", _normalize_topic_type(topic_type)),
        "complexity_level": analysis.complexity_level,
        "complexity_score": analysis.complexity_score,
        "intent_count": intent_count,
        "constraint_count": analysis.constraint_count,
        "entity_diversity": analysis.entity_diversity,
        "policy_reference_count": analysis.policy_reference_count,
        "cross_sentence_dependency": _detect_cross_sentence_dependency(cleaned),
        "complexity_trace": complexity_trace,
        "request_segments": request_segments,
        "length_bucket": _build_length_bucket(len(cleaned)),
        "is_multi": len(request_segments) >= 2,
    }


class ComplexityAnalyzer:
    def analyze(self, text: str, topic_type: str) -> ComplexityAnalysis:
        cleaned = str(text or "").strip()
        normalized_topic = str(topic_type or "general").strip().lower() or "general"

        if not cleaned:
            return ComplexityAnalysis(
                complexity_score=0.0,
                complexity_level="low",
                intent_count=0,
                constraint_count=0,
                entity_diversity=0,
                policy_reference_count=0,
                complexity_trace={
                    "topic_type": normalized_topic,
                    "text_length": 0,
                    "reason": "empty_text",
                },
            )

        text_length = len(cleaned)
        intent_count = _count_intents(cleaned)
        constraint_count = _count_tokens(cleaned, _CONSTRAINT_TOKENS)
        entity_diversity = _count_entity_diversity(cleaned)
        policy_reference_count = _count_tokens(cleaned, _POLICY_TOKENS)
        cross_sentence_dependency = _detect_cross_sentence_dependency(cleaned)

        score = _build_score(
            text_length=text_length,
            intent_count=intent_count,
            constraint_count=constraint_count,
            entity_diversity=entity_diversity,
            policy_reference_count=policy_reference_count,
        )
        level = _score_to_level(score)

        return ComplexityAnalysis(
            complexity_score=score,
            complexity_level=level,
            intent_count=intent_count,
            constraint_count=constraint_count,
            entity_diversity=entity_diversity,
            policy_reference_count=policy_reference_count,
            complexity_trace={
                "topic_type": normalized_topic,
                "text_length": text_length,
                "intent_count": intent_count,
                "constraint_count": constraint_count,
                "entity_diversity": entity_diversity,
                "policy_reference_count": policy_reference_count,
                "cross_sentence_dependency": cross_sentence_dependency,
                "weights": {
                    "length": min(0.25, text_length / 400.0),
                    "intent": min(0.20, max(0, intent_count - 1) * 0.08),
                    "constraint": min(0.20, constraint_count * 0.07),
                    "entity": min(0.15, entity_diversity * 0.05),
                    "policy": min(0.20, policy_reference_count * 0.10),
                },
            },
        )


def analyze(text: str, topic_type: str) -> ComplexityAnalysis:
    return _DEFAULT_ANALYZER.analyze(text=text, topic_type=topic_type)


def _count_tokens(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token in text)


def _count_entity_diversity(text: str) -> int:
    return sum(1 for token in _ENTITY_TOKENS if token in text)


def _normalize_topic_type(topic_type: str) -> str:
    cleaned = str(topic_type or "").strip().lower()
    return cleaned or "general"


def _build_request_segments(
    text: str,
    *,
    title: str | None = None,
    question: str | None = None,
) -> list[str]:
    return _analyze_request_segments(text, title=title, question=question).segments


def _analyze_request_segments(
    text: str,
    *,
    title: str | None = None,
    question: str | None = None,
) -> RequestSegmentAnalysis:
    cleaned = str(text or "").strip()
    title_text = str(title or "").strip()
    question_text = str(question or "").strip()
    boundary_used = title is not None or question is not None
    if not cleaned and not title_text and not question_text:
        return RequestSegmentAnalysis(
            segments=[],
            sentence_splitter="none",
            sentence_count=0,
            candidate_count=0,
            dropped_background_count=0,
            dropped_admin_action_count=0,
            shared_predicate_split_count=0,
            fallback_used=False,
            truncated=False,
            boundary_used=boundary_used,
        )

    source_inputs = _build_segment_source_inputs(
        cleaned,
        title=title_text,
        question=question_text,
        boundary_used=boundary_used,
    )
    request_segments_by_source: dict[str, list[str]] = {"title": [], "question": [], "text": []}
    candidate_count = 0
    dropped_background_count = 0
    dropped_admin_action_count = 0
    shared_predicate_split_count = 0
    sentence_count = 0
    sentence_splitters: list[str] = []
    for source, source_text in source_inputs:
        (
            source_segments,
            source_sentence_count,
            source_candidate_count,
            source_dropped_background_count,
            source_dropped_admin_action_count,
            source_shared_predicate_split_count,
            source_sentence_splitter,
        ) = _collect_request_segments(source_text)
        request_segments_by_source[source].extend(source_segments)
        sentence_count += source_sentence_count
        candidate_count += source_candidate_count
        dropped_background_count += source_dropped_background_count
        dropped_admin_action_count += source_dropped_admin_action_count
        shared_predicate_split_count += source_shared_predicate_split_count
        sentence_splitters.append(source_sentence_splitter)

    sentence_splitter = _merge_sentence_splitter_names(sentence_splitters)
    title_segments = _dedupe_request_segments(request_segments_by_source["title"])
    question_segments = _dedupe_request_segments(request_segments_by_source["question"])
    text_segments = _dedupe_request_segments(request_segments_by_source["text"])
    title_segments, title_duplicate_dropped_count = _drop_title_segments_covered_by_question(
        title_segments,
        question_segments,
    )
    deduped = _dedupe_request_segments([*title_segments, *question_segments, *text_segments])
    limit_exceeded = len(deduped) > MAX_REQUEST_SEGMENTS
    if limit_exceeded:
        deduped = _drop_broad_intro_for_segment_limit(deduped)
    truncated = limit_exceeded or len(deduped) > MAX_REQUEST_SEGMENTS
    if truncated:
        deduped = deduped[:MAX_REQUEST_SEGMENTS]
    if deduped:
        return RequestSegmentAnalysis(
            segments=deduped,
            sentence_splitter=sentence_splitter,
            sentence_count=sentence_count,
            candidate_count=candidate_count,
            dropped_background_count=dropped_background_count,
            dropped_admin_action_count=dropped_admin_action_count,
            shared_predicate_split_count=shared_predicate_split_count,
            fallback_used=False,
            truncated=truncated,
            boundary_used=boundary_used,
            title_segment_count=len(title_segments),
            question_segment_count=len(question_segments),
            title_duplicate_dropped_count=title_duplicate_dropped_count,
        )

    fallback_source = question_text or cleaned or title_text
    fallback = _normalize_segment(fallback_source)
    return RequestSegmentAnalysis(
        segments=[fallback] if fallback else [],
        sentence_splitter=sentence_splitter,
        sentence_count=sentence_count,
        candidate_count=candidate_count,
        dropped_background_count=dropped_background_count,
        dropped_admin_action_count=dropped_admin_action_count,
        shared_predicate_split_count=shared_predicate_split_count,
        fallback_used=bool(fallback),
        truncated=False,
        boundary_used=boundary_used,
        title_segment_count=len(title_segments),
        question_segment_count=len(question_segments),
        title_duplicate_dropped_count=title_duplicate_dropped_count,
    )


def _build_segment_source_inputs(
    text: str,
    *,
    title: str,
    question: str,
    boundary_used: bool,
) -> list[tuple[str, str]]:
    if not boundary_used:
        return [("text", text)] if text else []

    inputs: list[tuple[str, str]] = []
    if title:
        inputs.append(("title", title))
    if question:
        inputs.append(("question", question))
    if not inputs and text:
        inputs.append(("text", text))
    return inputs


def _collect_request_segments(
    text: str,
) -> tuple[list[str], int, int, int, int, int, str]:
    request_segments: list[str] = []
    candidate_count = 0
    dropped_background_count = 0
    dropped_admin_action_count = 0
    shared_predicate_split_count = 0
    sentences, sentence_splitter = _split_sentences_with_source(text)
    for sentence in sentences:
        for segment in _split_semantic_request_units(sentence):
            candidate_count += 1
            segment = _strip_non_request_prefix(segment)
            if _is_low_value_request_segment(segment):
                dropped_background_count += 1
                continue
            if _is_admin_action_without_request(segment):
                dropped_admin_action_count += 1
                continue
            if _is_background_only_segment(segment):
                dropped_background_count += 1
                continue
            shared_predicate_split_count += int(_is_shared_predicate_segment(segment))
            if _has_request_intent(segment):
                request_segments.append(_normalize_segment(segment))

    return (
        request_segments,
        len(sentences),
        candidate_count,
        dropped_background_count,
        dropped_admin_action_count,
        shared_predicate_split_count,
        sentence_splitter,
    )


def _merge_sentence_splitter_names(splitters: list[str]) -> str:
    normalized = [name for name in splitters if name and name != "none"]
    if not normalized:
        return "none"
    unique = list(dict.fromkeys(normalized))
    return unique[0] if len(unique) == 1 else "+".join(unique)


def _drop_title_segments_covered_by_question(
    title_segments: list[str],
    question_segments: list[str],
) -> tuple[list[str], int]:
    if not title_segments or not question_segments:
        return title_segments, 0

    kept: list[str] = []
    dropped = 0
    for title_segment in title_segments:
        if _is_title_segment_covered_by_question(title_segment, question_segments):
            dropped += 1
            continue
        kept.append(title_segment)
    return kept, dropped


def _is_title_segment_covered_by_question(title_segment: str, question_segments: list[str]) -> bool:
    title_content = _content_terms(title_segment) - _GENERIC_QUESTION_CONTENT_TERMS
    if not title_content:
        return False

    for question_segment in question_segments:
        question_content = _content_terms(question_segment) - _GENERIC_QUESTION_CONTENT_TERMS
        if not question_content:
            continue
        common = title_content & question_content
        question_specific_content = question_content - _GENERIC_TITLE_CONTENT_TERMS
        if _GENERIC_INQUIRY_HEADING_RE.match(title_segment) and (
            common or any(len(term) >= 4 for term in question_specific_content)
        ):
            return True
        if len(common) >= 2:
            return True
        if any(len(term) >= 5 for term in common):
            return True
        if common and len(title_content) <= 2:
            return True
    return False


def _split_sentences(text: str) -> list[str]:
    sentences, _ = _split_sentences_with_source(text)
    return sentences


def _split_sentences_with_source(text: str) -> tuple[list[str], str]:
    if _should_use_kss_sentence_splitter():
        kss_sentences = _split_sentences_with_kss(text)
        if kss_sentences:
            return _merge_orphan_numbered_markers(kss_sentences), "kss"

    regex_sentences = [
        _normalize_segment(part)
        for part in _SENTENCE_SPLIT_RE.split(text)
        if part.strip()
    ]
    return _merge_orphan_numbered_markers(regex_sentences), "regex"


def _merge_orphan_numbered_markers(sentences: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(sentences):
        current = _normalize_segment(sentences[index])
        if (
            _BARE_ENUMERATED_MARKER_RE.match(current)
            and index + 1 < len(sentences)
        ):
            next_sentence = _normalize_segment(sentences[index + 1])
            if next_sentence:
                combined = _normalize_segment(f"{current} {next_sentence}")
                if (
                    _INCOMPLETE_ENUMERATED_REQUEST_HEAD_RE.match(combined)
                    and index + 2 < len(sentences)
                ):
                    tail_sentence = _normalize_segment(sentences[index + 2])
                    if _POLITE_REQUEST_TAIL_RE.match(tail_sentence):
                        merged.append(_normalize_segment(f"{combined} {tail_sentence}"))
                        index += 3
                        continue
                merged.append(combined)
                index += 2
                continue
        if (
            _INCOMPLETE_ENUMERATED_REQUEST_HEAD_RE.match(current)
            and index + 1 < len(sentences)
        ):
            next_sentence = _normalize_segment(sentences[index + 1])
            if _POLITE_REQUEST_TAIL_RE.match(next_sentence):
                merged.append(_normalize_segment(f"{current} {next_sentence}"))
                index += 2
                continue
        if current:
            merged.append(current)
        index += 1
    return merged


def _should_use_kss_sentence_splitter() -> bool:
    flag = os.getenv("COMPLEXITY_ANALYZER_USE_KSS", "").strip().lower()
    return flag in {"1", "true", "yes", "on"} or "kss" in sys.modules


def _split_sentences_with_kss(text: str) -> list[str]:
    splitter = _load_kss_sentence_splitter()
    if splitter is None:
        return []
    try:
        raw_sentences = splitter(text, backend="fast", num_workers=1)
    except TypeError:
        raw_sentences = splitter(text)
    except Exception:
        return []

    if isinstance(raw_sentences, str):
        raw_sentences = [raw_sentences]
    return [
        _normalize_segment(part)
        for part in raw_sentences
        if str(part or "").strip()
    ]


def _load_kss_sentence_splitter() -> Callable[..., object] | None:
    global _KSS_SENTENCE_SPLITTER

    if _KSS_SENTENCE_SPLITTER is not _KSS_SPLITTER_UNSET:
        return _KSS_SENTENCE_SPLITTER  # type: ignore[return-value]

    # kss는 한국어 문장 경계만 담당하고, 요청 단위 판단은 의미 기반 규칙에서 수행한다.
    try:
        from kss import split_sentences  # type: ignore
    except Exception:
        _KSS_SENTENCE_SPLITTER = None
        return None
    _KSS_SENTENCE_SPLITTER = split_sentences
    return split_sentences


def _split_semantic_request_units(segment: str) -> list[str]:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return []

    numbered_parts = _split_numbered_request_units(cleaned)
    if numbered_parts:
        return numbered_parts

    shared_predicate_parts = _split_shared_predicate_request_units(cleaned)
    if len(shared_predicate_parts) >= 2:
        return shared_predicate_parts

    compact_list_parts = _split_compact_request_list_units(cleaned)
    if len(compact_list_parts) >= 2:
        return compact_list_parts

    for splitter in _SEMANTIC_SPLIT_PATTERNS:
        parts = [_normalize_segment(part) for part in splitter.split(cleaned) if part.strip()]
        if len(parts) >= 2 and all(_has_request_intent(part) for part in parts):
            split_parts: list[str] = []
            for part in parts:
                split_parts.extend(_split_semantic_request_units(part))
            return split_parts
    return [cleaned]


def _split_numbered_request_units(segment: str) -> list[str]:
    matches = list(_ENUMERATED_ITEM_RE.finditer(segment))
    if len(matches) < 2:
        return []

    parts: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        if start > 0 and segment[start].isspace():
            start += 1
        end = matches[index + 1].start() if index + 1 < len(matches) else len(segment)
        part = _normalize_segment(segment[start:end])
        part = _ENUMERATED_PREFIX_RE.sub("", part)
        part = re.sub(r"(?:및|그리고|또한|아울러)$", "", part).strip()
        if part:
            parts.append(part)

    request_like_parts = [part for part in parts if _has_request_intent(part)]
    if len(request_like_parts) < 2:
        if request_like_parts and _looks_like_numbered_title_segment(segment):
            return request_like_parts
        return []
    return request_like_parts


def _looks_like_numbered_title_segment(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    return len(cleaned) <= 220 and ("민원" in cleaned or " 및 " in cleaned or "및 " in cleaned)


def _split_shared_predicate_request_units(segment: str) -> list[str]:
    match = _SHARED_REQUEST_PREDICATE_RE.match(segment)
    if not match:
        return []

    body = _normalize_segment(match.group("body"))
    predicate = _normalize_segment(match.group("predicate"))
    suffix = match.group("suffix") or ""
    parts = [_normalize_segment(part) for part in _SHARED_REQUEST_SPLIT_RE.split(body) if part.strip()]
    if len(parts) < 2:
        return []
    if not all(_can_share_request_predicate(part) for part in parts):
        return []

    return [
        _normalize_segment(f"{part} {predicate}{suffix}")
        for part in parts
    ]


def _split_compact_request_list_units(segment: str) -> list[str]:
    match = _SHARED_REQUEST_PREDICATE_RE.match(segment)
    if not match:
        return []

    body = _normalize_segment(match.group("body"))
    predicate = _normalize_segment(match.group("predicate"))
    suffix = match.group("suffix") or ""
    if _DIRECTION_PAIR_RE.search(body):
        return []
    if len(body) > 90 or any(token in body for token in _BACKGROUND_GUARD_TOKENS):
        return []
    if any(char in body for char in ("(", ")", "（", "）")):
        return []

    parts = [_normalize_segment(part) for part in _COMPACT_REQUEST_LIST_SPLIT_RE.split(body) if part.strip()]
    if not 2 <= len(parts) <= MAX_REQUEST_SEGMENTS:
        return []
    if any(len(part) > 24 for part in parts):
        return []
    if any(_LIST_CONTEXT_FRAGMENT_RE.search(part) for part in parts[:-1]):
        return []
    if any(_has_explicit_request_signal(part) or len(part) < 3 for part in parts):
        return []

    return [
        _normalize_segment(f"{part} {predicate}{suffix}")
        for part in parts
    ]


def _can_share_request_predicate(part: str) -> bool:
    cleaned = _normalize_segment(part)
    if _has_explicit_request_signal(cleaned):
        return False
    return any(token in cleaned for token in _REQUEST_ACTION_TOKENS) and any(
        token in cleaned for token in _REQUEST_OBJECT_TOKENS
    )


def _has_request_intent(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return False

    if _is_admin_action_without_request(cleaned):
        return False
    if _is_generic_polite_closing_segment(cleaned):
        return False
    if _KOREAN_REQUEST_INTENT_RE.search(cleaned):
        return True
    if _KOREAN_NOMINAL_QUESTION_RE.search(cleaned):
        return True
    if _OBJECTED_POLITE_REQUEST_RE.search(cleaned):
        return True

    return any(pattern.search(cleaned) for pattern in _REQUEST_INTENT_PATTERNS)


def _has_explicit_request_signal(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    return any(
        token in cleaned
        for token in (
            "요청",
            "문의",
            "질의",
            "신고",
            "건의",
            "부탁",
            "바랍니다",
            "해주세요",
            "해 주세요",
            "궁금",
            "?",
        )
    )


def _strip_non_request_prefix(segment: str) -> str:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return ""

    cleaned = _TITLE_Q_PREFIX_RE.sub("", cleaned).strip()
    cleaned = _DIALOGUE_SPEAKER_PREFIX_RE.sub("", cleaned).strip()
    cleaned = _ENUMERATED_PREFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"^(?:그리고|또한|아울러)\s+", "", cleaned).strip()

    without_greeting = _TITLE_GREETING_PREFIX_RE.sub("", cleaned).strip()
    if without_greeting != cleaned:
        return without_greeting
    return cleaned


def _is_low_value_request_segment(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned:
        return True
    if _is_generic_polite_closing_segment(cleaned):
        return True
    if _REDACTION_ONLY_RE.match(cleaned):
        return True
    if _OBJECTED_POLITE_REQUEST_RE.search(cleaned):
        return False
    if _ANSWER_NOTICE_ONLY_RE.match(cleaned):
        return True
    if _GENERIC_CURIOSITY_ONLY_RE.match(cleaned):
        return True
    if _LOW_VALUE_CLOSING_SEGMENT_RE.match(cleaned):
        return True
    if _ATTACHMENT_REFERENCE_RE.match(cleaned):
        return True
    if _LOW_VALUE_REFERENCE_SEGMENT_RE.match(cleaned):
        return True
    if _LOW_INFORMATION_REQUEST_RE.match(cleaned):
        return True
    if _GENERIC_REQUEST_ONLY_RE.match(cleaned):
        return True
    if _GENERIC_ACTION_ONLY_RE.match(cleaned):
        return True
    if _FACTUAL_CONTEXT_RE.search(cleaned) and not _REQUEST_END_RE.search(cleaned):
        return True
    if _PAST_FACT_ONLY_RE.search(cleaned) and not _REQUEST_END_RE.search(cleaned):
        return True
    if _CLOSING_ONLY_RE.search(cleaned) and not any(token in cleaned for token in _REQUEST_OBJECT_TOKENS):
        return True
    if _GENERIC_CLOSING_REQUEST_RE.search(cleaned):
        return True
    if _ANSWER_FORM_ONLY_RE.search(cleaned):
        return True
    if re.fullmatch(r"(?:안녕하십니까|안녕하세요|수고가 많으십니다)[.!?。！？]?", cleaned):
        return True
    return False


def _is_generic_polite_closing_segment(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned or len(cleaned) > 48:
        return False
    if not _POLITE_CLOSING_ONLY_RE.match(cleaned):
        return False
    content = _content_terms(cleaned) - _GENERIC_CLOSING_CONTENT_TERMS
    return not content


def _has_concrete_request_content(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    return any(token in cleaned for token in _REQUEST_OBJECT_TOKENS) or len(_content_terms(cleaned)) >= 2


def _is_admin_action_without_request(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if _OBJECTED_POLITE_REQUEST_RE.search(cleaned):
        return False
    return bool(_ADMIN_ACTION_RE.search(cleaned) and not _has_explicit_request_signal(cleaned))


def _is_background_only_segment(segment: str) -> bool:
    cleaned = _normalize_segment(segment)
    if not cleaned or _has_explicit_request_signal(cleaned):
        return False
    return bool(_BACKGROUND_ONLY_RE.search(cleaned) and not any(token in cleaned for token in _REQUEST_ACTION_TOKENS))


def _is_shared_predicate_segment(segment: str) -> bool:
    return bool(_SHARED_REQUEST_PREDICATE_RE.match(_normalize_segment(segment)))


def _dedupe_request_segments(segments: list[str]) -> list[str]:
    normalized = [
        _strip_non_request_prefix(segment)
        for segment in segments
        if _normalize_segment(segment)
    ]
    normalized = [
        segment
        for segment in normalized
        if segment and not _is_low_value_request_segment(segment)
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for segment in normalized:
        key = _segment_key(segment)
        if key in seen:
            continue
        seen.add(key)
        unique.append(segment)

    unique = _merge_repeated_request_segments(unique)
    unique = _drop_summary_request_segments(unique)

    deduped: list[str] = []
    keys = [_segment_key(segment) for segment in unique]
    for index, segment in enumerate(unique):
        key = keys[index]
        if any(
            index != other_index and key in other_key and len(key) < len(other_key)
            for other_index, other_key in enumerate(keys)
        ):
            continue
        deduped.append(segment)
    return deduped


def _merge_repeated_request_segments(segments: list[str]) -> list[str]:
    merged: list[str] = []
    for segment in segments:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if _is_repeated_request_segment(segment, existing)
            ),
            None,
        )
        if duplicate_index is None:
            merged.append(segment)
            continue
        if _segment_quality_score(segment) > _segment_quality_score(merged[duplicate_index]):
            merged[duplicate_index] = segment
    return merged


def _drop_summary_request_segments(segments: list[str]) -> list[str]:
    if len(segments) < 2:
        return segments
    return [
        segment
        for index, segment in enumerate(segments)
        if not _is_summary_request_segment(segment, segments, index)
        and not _is_generic_inquiry_intro_segment(segment, segments, index)
    ]


def _drop_broad_intro_for_segment_limit(segments: list[str]) -> list[str]:
    if len(segments) <= MAX_REQUEST_SEGMENTS:
        return segments
    if not segments or not _is_broad_intro_before_specific_questions(segments[0], segments[1:]):
        return segments
    return segments[1:]


def _is_broad_intro_before_specific_questions(segment: str, following_segments: list[str]) -> bool:
    cleaned = _normalize_segment(segment)
    if not _BROAD_INTRO_REQUEST_RE.search(cleaned):
        return False
    if len(following_segments) < MAX_REQUEST_SEGMENTS:
        return False

    specific_question_count = sum(
        1
        for following in following_segments
        if _QUESTION_LIKE_SEGMENT_RE.search(following)
        or _KOREAN_NOMINAL_QUESTION_RE.search(following)
        or _OBJECTED_POLITE_REQUEST_RE.search(following)
    )
    return specific_question_count >= 3


def _is_summary_request_segment(segment: str, segments: list[str], index: int) -> bool:
    cleaned = _normalize_segment(segment)
    if len(cleaned) > 70 or not _has_explicit_request_signal(cleaned):
        return False
    if _QUESTION_LIKE_SEGMENT_RE.search(cleaned):
        return False

    content = _content_terms(cleaned)
    if not content:
        return False
    actions = _action_terms(cleaned)

    for other in segments:
        if other == cleaned or len(other) <= len(cleaned) + 10:
            continue
        common_content = content & _content_terms(other)
        if len(common_content) >= 2 and actions and actions & _action_terms(other):
            return True
    return False


def _is_generic_inquiry_intro_segment(segment: str, segments: list[str], index: int) -> bool:
    cleaned = _normalize_segment(segment)
    if not (
        _GENERIC_INQUIRY_INTRO_RE.match(cleaned)
        or _GENERIC_INQUIRY_HEADING_RE.match(cleaned)
    ):
        return False
    if "?" in cleaned or len(cleaned) > 100:
        return False
    content = _content_terms(cleaned) - {"관련", "문의", "질의", "사항", "내용"}
    if not content:
        return True
    for other_index, other in enumerate(segments):
        if other_index == index:
            continue
        other_content = _content_terms(other)
        if content & other_content:
            return True
    return False


def _is_repeated_request_segment(left: str, right: str) -> bool:
    left_actions = _action_terms(left)
    right_actions = _action_terms(right)
    if not left_actions or not right_actions or not (left_actions & right_actions):
        return False

    left_content = _content_terms(left)
    right_content = _content_terms(right)
    common_content = left_content & right_content
    if not common_content:
        return False

    union = left_content | right_content
    if common_content & _REPEATED_SINGLE_ISSUE_TERMS and "요청" in (left_actions & right_actions):
        return True

    similarity = len(common_content) / max(1, len(union))
    return similarity >= 0.45


def _segment_quality_score(segment: str) -> float:
    cleaned = _normalize_segment(segment)
    score = min(2.0, len(cleaned) / 60)
    score += len(_action_terms(cleaned)) * 0.3
    score += min(4, len(_content_terms(cleaned))) * 0.2
    if _CLOSING_ONLY_RE.search(cleaned):
        score -= 1.0
    return score


def _action_terms(segment: str) -> set[str]:
    cleaned = _normalize_segment(segment)
    return {token for token in _ACTION_SIGNATURE_TOKENS if token in cleaned}


def _content_terms(segment: str) -> set[str]:
    cleaned = _normalize_segment(segment)
    terms: set[str] = set()
    for word in re.findall(r"[가-힣A-Za-z0-9]+", cleaned):
        word = re.sub(
            r"(?:으로|에게|에서|부터|까지|하고|하며|이며|입니다|합니다|드립니다|"
            r"입니까|인가요|인지요|인지|인가|되나요|됩니까|하나요|나요|까요|"
            r"이란|란|"
            r"해주세요|해주십시오|해주시기|해주시길|해주시|해|할|하는|한|을|를|이|가|은|는|의|에|와|과|도|만)$",
            "",
            word,
        )
        if len(word) < 2 or word in _SIGNATURE_STOPWORDS or set(word) <= {"▲", "△", "○", "□"}:
            continue
        if word in _ACTION_SIGNATURE_TOKENS:
            continue
        terms.add(word)
    return terms


def _normalize_segment(segment: str) -> str:
    return " ".join(str(segment or "").split())


def _segment_key(segment: str) -> str:
    return re.sub(r"[\s.!?。！？,;:/]+", "", segment)


def _detect_cross_sentence_dependency(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    return any(token in cleaned for token in ("또한", "한편", "다만", "그리고"))


def _build_length_bucket(text_length: int) -> Literal["short", "medium", "long"]:
    if text_length < 40:
        return "short"
    if text_length < 120:
        return "medium"
    return "long"


def _count_intents(text: str) -> int:
    segments = _build_request_segments(text)
    return len(segments) if segments else 0


def _build_score(
    *,
    text_length: int,
    intent_count: int,
    constraint_count: int,
    entity_diversity: int,
    policy_reference_count: int,
) -> float:
    score = (
        0.10
        + min(0.25, text_length / 400.0)
        + min(0.20, max(0, intent_count - 1) * 0.08)
        + min(0.20, constraint_count * 0.07)
        + min(0.15, entity_diversity * 0.05)
        + min(0.20, policy_reference_count * 0.10)
    )
    return max(0.0, min(1.0, round(score, 3)))


def _score_to_level(score: float) -> ComplexityLevel:
    if score >= COMPLEXITY_LEVEL_HIGH_THRESHOLD:
        return "high"
    if score >= COMPLEXITY_LEVEL_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


_DEFAULT_ANALYZER = ComplexityAnalyzer()
