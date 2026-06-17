"""QA 응답 citation/validation 공통 유틸."""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List


_CITE_TOKEN_PATTERN = re.compile(r"\[\[출처\s*(\d+)\]\]")
_DEBUG_METADATA_PATTERN = re.compile(
    r"\s*\(?\s*(?:chunk_id=)?CASE-\d+__chunk-\d+(?:\s+case_id=CASE?-\d+|\s+case_id=\d+)?(?:\s+score=[0-9.]+)?\s*\)?",
    flags=re.IGNORECASE,
)
_CIVIL_REPLY_PREFIX_1 = "1. 귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다."
_CIVIL_REPLY_PREFIX_2 = (
    "2. 귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다. "
    "접수된 민원 취지와 관련 근거를 함께 고려하여 처리 방향을 검토하는 사안입니다."
)
_CIVIL_REPLY_PREFIX_3 = "3. 검토 의견은 다음과 같습니다."
_CIVIL_REPLY_CLOSING = (
    "4. 답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면 세부 검토 결과와 "
    "후속 절차를 친절히 안내해 드리겠습니다. 감사합니다. 끝."
)
_QUALITY_STOPWORDS = {
    "귀하",
    "민원",
    "신청",
    "요청",
    "관련",
    "검토",
    "조치",
    "답변",
    "사항",
    "필요",
    "가능",
    "담당부서",
    "안내",
    "현재",
    "해당",
    "통해",
    "위해",
    "경우",
}
_COMMITMENT_PATTERN = re.compile(
    r"(?:설치|철거|제거|이동|신설|건설|매입|확대|개방|허가|지정|도입|"
    r"예산\s*확보|계획\s*수립|방역|단속)"
    r"[^.\n]{0,35}(?:하겠습니다|할\s*예정입니다|할\s*계획입니다|진행합니다|실시합니다)"
)
_UNVERIFIED_FACT_PATTERN = re.compile(
    r"(?:확인하였습니다|보고되었습니다|이미\s*예정|진행\s*중입니다|완료되었습니다|예상\s*완료일)"
)
_CONSTRAINT_PATTERN = re.compile(
    r"(?:처리|설치|이동|개방|사용|허가|지정|지원).{0,20}(?:불가|곤란|어렵)"
    r"|사유지|소유자\s*(?:소관|책임|관리)|관리사무소\s*(?:소관|관리)"
    r"|관할\s*(?:외|아님)|권한이?\s*없|도로\s*폭\s*부족"
)
_CONCRETE_PRECEDENT_CUE = re.compile(
    r"현재|특정\s*날짜|공사|예정|완료|진행\s*중|해당\s*지역|인근|코로나|재개|"
    r"\d{4}[.년]|월|일|운영\s*중"
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strip_structured_artifact_tail(text: str) -> str:
    rendered = str(text or "")
    markers = (
        r"\bstructured_output(?:\.[A-Za-z_]+)?\b",
        r"확인\s*및\s*협의\s*조치\s*:",
    )
    for pattern in markers:
        match = re.search(pattern, rendered, flags=re.IGNORECASE)
        if match and match.start() > 0:
            rendered = rendered[: match.start()]
            break
    return rendered.strip()


def sanitize_answer_text(answer: str) -> str:
    """사용자 답변에 노출되면 안 되는 retrieval 메타데이터를 제거한다."""
    rendered = str(answer or "").strip()
    if not rendered:
        return ""

    rendered = rendered.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    rendered = _DEBUG_METADATA_PATTERN.sub("", rendered)
    rendered = re.split(
        r"(?:\*\*)?(?:structured_output|limitations)(?:\*\*)?\s*:",
        rendered,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    rendered = re.sub(r"\(\s*chunk_id=[^)]+\)", "", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"\[\[\s*\"[^\"]{0,500}\"\s*\]\]", "", rendered)
    rendered = re.sub(r"(?m)^\s*\[\[\".*?\"\]\]\s*$", "", rendered)
    rendered = re.sub(r"(?m)^\s*#{1,6}\s*", "", rendered)
    rendered = rendered.replace("**", "")
    rendered = re.sub(
        r"(?i)(?:액션\s*아이템|action\s*items?|조치\s*제안|섹션)\s*\d*\s*[:：]?\s*",
        "",
        rendered,
    )
    rendered = re.sub(r"\[REDACTED:[A-Z_]+\]", "비식별 처리된 정보", rendered)
    rendered = re.sub(r"\[REDACTED:[^\]\n]*$", "", rendered)
    rendered = re.sub(r"</?(?:strong|b|ul|ol|li|p|br)\b[^>]*>", " ", rendered, flags=re.IGNORECASE)
    rendered = re.sub(r"<[^>]+>", " ", rendered)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    rendered = _strip_structured_artifact_tail(rendered)
    return rendered.strip()


def _strip_citation_tokens(text: str) -> str:
    rendered = _CITE_TOKEN_PATTERN.sub("", text or "")
    rendered = re.sub(r"\[출처\s*\d+\]", "", rendered)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    return rendered.strip()


def _strip_standard_reply_shell(text: str) -> str:
    rendered = text or ""
    patterns = [
        re.escape(_CIVIL_REPLY_PREFIX_1),
        re.escape(_CIVIL_REPLY_PREFIX_2),
        re.escape(_CIVIL_REPLY_PREFIX_3),
        re.escape(_CIVIL_REPLY_CLOSING),
        r"1\.\s*귀하께서\s*신청하신\s*민원에\s*대한\s*검토\s*결과를\s*다음과\s*같이\s*답변드립니다\.",
        r"2\.\s*귀하의\s*민원\s*내용은.*?처리\s*방향을\s*검토하는\s*사안입니다\.",
        r"3\.\s*검토\s*의견은\s*다음과\s*같습니다\.?",
        r"4\.\s*답변\s*내용에\s*대한\s*추가\s*설명이\s*필요한\s*경우.*?감사합니다\.\s*끝\.?",
        r"4\.\s*추가\s*설명이\s*필요한\s*경우.*?감사합니다\.\s*끝\.?",
    ]
    for pattern in patterns:
        rendered = re.sub(pattern, "", rendered, flags=re.DOTALL)
    rendered = re.sub(r"(?m)^\s*[가-하]\.\s*", "", rendered)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    return rendered.strip(" \n;")


def _normalize_review_body(text: str) -> str:
    """Remove embedded reply endings/numbering and soften unsupported promises."""
    rendered = text or ""
    rendered = re.sub(
        r"(?:감사합니다[.!]?\s*)?끝[.!]?",
        "",
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(r"(?m)^\s*[1-4][.．)]\s*", "", rendered)
    rendered = re.sub(r"(?m)^\s*[-•]\s*", "", rendered)

    action_pattern = re.compile(
        r"(?P<action>설치|철거|제거|이동|신설|건설|매입|보수|정비|폐쇄|단속|"
        r"시정|개선|확대|개방|허가|지정|도입|확보|수립)"
        r"(?:을|를)?\s*(?:즉시\s*)?"
        r"(?:실시|시행|추진|완료|진행|조치)?"
        r"(?:하겠습니다|할\s*예정입니다|할\s*계획입니다)"
    )
    rendered = action_pattern.sub(
        lambda match: f"{match.group('action')} 가능 여부를 검토하겠습니다",
        rendered,
    )
    rendered = re.sub(
        r"(?P<action>개발|활용|확대|설치|건설|매입|도입|구축|마련|실시)"
        r"(?:하여|해)?\s*(?:즉시\s*)?(?:활용|진행|시행)?합니다",
        lambda match: (
            f"{match.group('action')} 가능 여부를 검토하겠습니다"
        ),
        rendered,
    )
    rendered = re.sub(
        r"(?P<action>제거|철거|설치|이동|보수|정비|방역)"
        r"(?:\s*작업|\s*조치)?(?:을|를)?\s*(?:우선적으로|즉시)?\s*"
        r"(?:진행|실시)할\s*예정입니다",
        lambda match: (
            f"{match.group('action')} 필요성과 처리 권한을 현장 확인 후 판단하겠습니다"
        ),
        rendered,
    )
    rendered = re.sub(
        r"(?:설계\s*및\s*건설\s*)?계획을\s*수립할\s*예정입니다",
        "관련 계획의 수립 가능 여부를 검토하겠습니다",
        rendered,
    )
    rendered = re.sub(
        r"즉시\s*조치로는\s*[^.!?\n]{1,100}(?:진행하고자|실시하고자)\s*합니다",
        "우선 현장 여건과 소관 권한을 확인하겠습니다",
        rendered,
    )
    rendered = re.sub(
        r"즉시\s*조치로는\s*다음과\s*같은\s*방안을\s*제안드립니다\s*:",
        "우선 다음 사항을 중심으로 검토할 필요가 있습니다.",
        rendered,
    )
    rendered = re.sub(
        r"추가적인\s*조치로는\s*:",
        "추가로 다음 사항을 확인할 필요가 있습니다.",
        rendered,
    )
    rendered = re.sub(
        r"검토해\s*주시기\s*바랍니다",
        "검토할 필요가 있습니다",
        rendered,
    )
    rendered = re.sub(
        r"진행해\s*주시기\s*바랍니다",
        "진행 가능 여부를 검토하겠습니다",
        rendered,
    )
    rendered = re.sub(
        r"(?:조치를\s*)?취해\s*주시기\s*바랍니다",
        "필요한 조치 여부를 검토하겠습니다",
        rendered,
    )
    rendered = re.sub(
        r"(?P<claim>[^.\n]{2,180})음을\s*확인하였습니다",
        lambda match: f"{match.group('claim')}는지는 현장 확인이 필요합니다",
        rendered,
    )
    rendered = re.sub(
        r"(?P<claim>[^.\n]{2,180}?)(?:이|가)\s*보고되었습니다",
        lambda match: f"{match.group('claim').strip()} 여부는 현장 확인이 필요합니다",
        rendered,
    )
    rendered = re.sub(
        r"(?:다음과\s*같은\s*)?방안을\s*제안드립니다\s*:",
        "처리 방향은 다음 사항을 중심으로 검토할 필요가 있습니다.",
        rendered,
    )
    rendered = re.sub(
        r"권장드립니다",
        "검토할 필요가 있습니다",
        rendered,
    )
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"(?m)^\s*\d+(?:\.\d+)?[.．)]\s*", "", rendered)
    rendered = re.sub(r"(?m)^\s*[-•]\s*", "", rendered)
    rendered = re.sub(r"(?m)^\s*\d+[.．)]\s*$", "", rendered)
    rendered = re.sub(r"(?<!\d)(?<!제)\b[1-9][.．)]\s+(?=[가-힣A-Za-z])", "", rendered)
    rendered = re.sub(
        r"(?P<object>[가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,3})(?:을|를)\s+"
        r"(?P<modifier>추가로\s+)?(?P<action>설치|건설|신설|이동|확대)\s+가능\s+여부",
        lambda match: (
            f"{match.group('object')}의 "
            f"{'추가 ' if match.group('modifier') else ''}"
            f"{match.group('action')} 가능 여부"
        ),
        rendered,
    )
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    rendered = re.sub(r"\s+([.?!])", r"\1", rendered)
    return rendered.strip(" \n;")


def _soften_risky_sentences(text: str) -> str:
    """Replace unsupported operational claims with evidence-safe review language."""
    rendered = str(text or "").strip()
    if not rendered:
        return ""

    action_terms = (
        "설치",
        "철거",
        "제거",
        "이동",
        "신설",
        "건설",
        "매입",
        "확대",
        "개방",
        "허가",
        "지정",
        "도입",
        "구축",
        "예산 확보",
        "계획 수립",
        "방역",
        "단속",
        "보수",
        "정비",
        "청소 일정",
        "거리 확보",
    )
    commitment_cue = re.compile(
        r"하겠습니다|할\s*예정입니다|할\s*계획입니다|실시하여|진행하여|"
        r"진행합니다|실시합니다|즉시\s*활용합니다|강화하겠습니다|마련하겠습니다|높입니다|"
        r"최소화합니다|적극\s*반영"
    )
    safe_cue = re.compile(
        r"가능\s*여부|필요성|현장\s*확인\s*후|담당부서\s*확인|"
        r"검토할\s*필요|방안을\s*검토|관련\s*기준"
    )

    pieces = re.findall(r"[^.!?。！？\n]+(?:[.!?。！？]+|$)", rendered)
    normalized: List[str] = []
    normalized_keys: set[str] = set()
    generic_safety_added = False
    unverified_status_added = False
    for piece in pieces:
        sentence = piece.strip()
        if not sentence:
            continue
        if _CONSTRAINT_PATTERN.search(sentence):
            key = re.sub(r"\s+", "", sentence)
            if key not in normalized_keys:
                normalized.append(sentence)
                normalized_keys.add(key)
            continue
        if _UNVERIFIED_FACT_PATTERN.search(sentence):
            if not unverified_status_added:
                normalized.append(
                    "해당 조치의 현재 진행 여부와 일정은 담당부서 확인이 필요합니다."
                )
                unverified_status_added = True
            continue
        if re.search(r"사용.{0,16}협의해\s*보겠습니다", sentence):
            replacement = (
                "시설 사용 가능 여부는 운영 기준과 안전·보안 여건을 확인한 뒤 안내드리겠습니다."
            )
            if replacement not in normalized_keys:
                normalized.append(replacement)
                normalized_keys.add(replacement)
            continue
        if re.search(r"거리(?:를)?\s*확보[^.!?]{0,30}하겠습니다", sentence):
            replacement = (
                "흡연구역과 보행통로의 이격 필요성은 현장 여건과 관련 기준을 확인한 뒤 "
                "검토하겠습니다."
            )
            if replacement not in normalized_keys:
                normalized.append(replacement)
                normalized_keys.add(replacement)
            continue

        action_hits = [term for term in action_terms if term in sentence]
        action = action_hits[0] if action_hits else ""
        if len(action_hits) >= 2 and (
            commitment_cue.search(sentence)
            or (safe_cue.search(sentence) and re.search(r"하여|하거나|하고", sentence))
        ):
            if not generic_safety_added:
                normalized.append(
                    "요청하신 조치는 현장 여건, 소관 권한, 관련 계획 및 예산을 확인한 뒤 "
                    "추진 가능 여부를 검토하겠습니다."
                )
                generic_safety_added = True
            continue
        if action and commitment_cue.search(sentence) and not safe_cue.search(sentence):
            replacement = (
                f"{action} 요청은 현장 여건, 소관 권한 및 관련 기준을 확인한 뒤 "
                "처리 가능 여부를 검토하겠습니다."
            )
            key = re.sub(r"\s+", "", replacement)
            if key not in normalized_keys:
                normalized.append(replacement)
                normalized_keys.add(key)
            continue
        key = re.sub(r"\s+", "", sentence)
        if key not in normalized_keys:
            normalized.append(sentence)
            normalized_keys.add(key)

    return " ".join(normalized).strip() or rendered


def _stringify_structured_answer(value: Any) -> str:
    parts: List[str] = []
    if isinstance(value, list):
        for item in value:
            text = _stringify_structured_answer(item)
            if text:
                parts.append(text)
    elif isinstance(value, dict):
        section = str(value.get("section") or value.get("title") or "").strip()
        content = str(value.get("content") or value.get("text") or value.get("answer") or "").strip()
        if section and content:
            parts.append(f"{section}: {content}")
        elif content:
            parts.append(content)
        action_items = value.get("action_items")
        if isinstance(action_items, list):
            actions = [str(item).strip() for item in action_items if str(item).strip()]
            if actions:
                parts.append("필요한 후속 조치는 " + ", ".join(actions) + "입니다.")
    return " ".join(parts).strip()


def _normalize_structured_answer_text(text: str) -> str:
    rendered = (text or "").strip()
    if not rendered or rendered[0] not in "[{":
        return rendered
    try:
        parsed = ast.literal_eval(rendered)
    except (SyntaxError, ValueError):
        return rendered
    normalized = _stringify_structured_answer(parsed)
    return normalized or rendered


def _remove_generic_bridge_phrases(text: str) -> str:
    rendered = text or ""
    patterns = [
        r"\s*위\s*내용을\s*바탕으로\s*담당부서에서는\s*현장\s*여건,\s*관련\s*기준,\s*유사\s*처리\s*사례를\s*확인한\s*뒤\s*필요한\s*조치\s*가능\s*여부를\s*판단할\s*수\s*있습니다\.?",
        r"\s*담당부서에서는\s*접수\s*내용,\s*현장\s*여건,\s*관련\s*기준과\s*유사\s*처리\s*사례를\s*종합적으로\s*확인한\s*뒤\s*필요한\s*조치\s*가능\s*여부를\s*검토할\s*수\s*있습니다\.?",
        r"\s*다만\s*구체적인\s*조치\s*범위와\s*일정은\s*현장\s*확인\s*및\s*관계\s*부서\s*검토\s*결과에\s*따라\s*달라질\s*수\s*있습니다\.?",
    ]
    for pattern in patterns:
        rendered = re.sub(pattern, "", rendered)
    rendered = re.sub(r"\s+([.?!])", r"\1", rendered)
    rendered = re.sub(r"\n{3,}", "\n\n", rendered)
    rendered = re.sub(r"[ \t]{2,}", " ", rendered)
    return rendered.strip()


def _has_complete_sentence_end(text: str) -> bool:
    rendered = (text or "").strip()
    if not rendered:
        return False
    if rendered.endswith((".", "!", "?", "。", "！", "？")):
        return True
    return bool(
        re.search(
            r"(습니다|드립니다|됩니다|합니다|바랍니다|있습니다|없습니다|입니다|니다)\s*$",
            rendered,
        )
    )


def _trim_incomplete_trailing_sentence(text: str, citations: List[Dict[str, Any]]) -> str:
    """모델 출력이 길이 제한으로 끊긴 경우 마지막 미완성 조각을 제거한다."""
    rendered = (text or "").strip()
    if not rendered or _has_complete_sentence_end(rendered):
        return rendered

    end_positions = [
        match.end()
        for match in re.finditer(
            r"(?:[.!?。！？]|(?:습니다|드립니다|됩니다|합니다|바랍니다|있습니다|없습니다|입니다|니다)(?:[.!?])?)(?=\s|$)",
            rendered,
        )
    ]
    if end_positions:
        candidate = rendered[: end_positions[-1]].strip()
        if candidate and _has_complete_sentence_end(candidate):
            return candidate

    return _fallback_review_body(citations)


def _meaningful_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]{2,}", str(text or ""))
        if token not in _QUALITY_STOPWORDS and not token.isdigit()
    }


def normalize_structured_output(
    value: Any,
    *,
    request_segments: List[str] | None = None,
) -> Dict[str, Any]:
    """Normalize UI metadata without exposing unsupported deadlines or promises."""
    structured = value if isinstance(value, dict) else {}
    summary = sanitize_answer_text(str(structured.get("summary") or ""))
    summary = re.sub(
        r"(?i)^\s*(?:요약|summary)\s*[:：]\s*",
        "",
        summary,
    ).strip()

    raw_actions = structured.get("action_items")
    if not isinstance(raw_actions, list):
        raw_actions = []

    action_terms = (
        "설치",
        "철거",
        "제거",
        "이동",
        "신설",
        "건설",
        "매입",
        "보수",
        "정비",
        "방역",
        "단속",
        "개방",
        "허가",
        "지정",
        "수립",
    )
    safe_terms = ("확인", "검토", "협의", "안내", "판단", "점검")
    actions: List[str] = []
    for item in raw_actions:
        action = sanitize_answer_text(str(item or ""))
        action = re.sub(
            r"\(\s*(?:즉시|긴급|우선|당일|\d+\s*(?:일|시간|주)\s*이내)\s*\)",
            "",
            action,
        )
        action = re.sub(
            r"(?<![가-힣A-Za-z0-9])(?:즉시|긴급히|\d+\s*(?:일|시간|주)\s*이내)\s*",
            "",
            action,
        )
        action = re.sub(r"\s+", " ", action).strip(" .:：-")
        if not action:
            continue

        if any(term in action for term in action_terms) and not any(
            term in action for term in safe_terms
        ):
            action = f"{action} 필요성 및 소관 권한 검토"

        if action not in actions:
            actions.append(action)

    canonical_segments = [
        sanitize_answer_text(str(item or "")).strip()
        for item in (request_segments or [])
        if sanitize_answer_text(str(item or "")).strip()
    ]
    if not canonical_segments:
        raw_segments = structured.get("request_segments")
        if isinstance(raw_segments, list):
            canonical_segments = [
                sanitize_answer_text(str(item or "")).strip()
                for item in raw_segments
                if sanitize_answer_text(str(item or "")).strip()
            ]

    return {
        "summary": summary,
        "action_items": actions,
        "request_segments": canonical_segments,
    }


def _remove_precedent_fact_leakage(
    text: str,
    *,
    complaint: str = "",
    context: List[Dict[str, Any]] | None = None,
) -> str:
    """Drop concrete precedent-only sentences that are unrelated to the complaint."""
    rendered = str(text or "").strip()
    if not rendered or not complaint or not context:
        return rendered

    complaint_terms = _meaningful_terms(complaint)
    context_terms: set[str] = set()
    for item in context:
        if isinstance(item, dict):
            context_terms.update(_meaningful_terms(item.get("snippet")))
    context_only = context_terms - complaint_terms
    if not context_only:
        return rendered

    pieces = re.split(r"(?<=[.!?。！？])\s+|\n+", rendered)
    kept: List[str] = []
    for piece in pieces:
        sentence = piece.strip()
        if not sentence:
            continue
        terms = _meaningful_terms(sentence)
        precedent_hits = terms & context_only
        complaint_hits = terms & complaint_terms
        if (
            _CONCRETE_PRECEDENT_CUE.search(sentence)
            and len(precedent_hits) >= 2
            and len(complaint_hits) <= 1
        ):
            continue
        kept.append(sentence)
    return " ".join(kept).strip() or rendered


_KO_CONTEXT_CONSTRAINT_RE = re.compile(
    r"불가|어렵|곤란|사유지|소유자|관리주체|관리사무소|소관|권한|관할|개인\s*소유"
)
_KO_OVERACTIVE_ACTION_RE = re.compile(
    r"설치|철거|제거|이동|재배치|신설|건설|매입|보수|정비|개방|허용|지정|마련|확보|실시|개최"
)
_KO_OVERACTIVE_TONE_RE = re.compile(
    r"제안|검토해\s*보겠습니다|검토해볼\s*수\s*있습니다|가능|기여|도움|방안|허용|재배치"
)
_KO_UNSUPPORTED_PROPOSAL_RE = re.compile(
    r"제안드립|권장드립|허용하는\s*방안|설치하는\s*방안|재배치(?:를)?\s*제안|"
    r"계획을\s*수립하고\s*있|확충을\s*위한\s*계획|주민\s*설명회|의견을\s*수렴하겠|"
    r"최적\s*위치\s*선정|쾌적한\s*환경을\s*제공|기여할\s*것"
)
_KO_SAFE_REVIEW_CUE_RE = re.compile(
    r"현장\s*여건|소관\s*권한|관련\s*기준|처리\s*가능\s*여부|검토하겠습니다|확인한\s*뒤"
)


def _remove_unsupported_proposals(text: str) -> str:
    rendered = str(text or "").strip()
    if not rendered:
        return ""

    kept: List[str] = []
    removed = False
    for sentence in re.split(r"(?<=[.!?。])\s+|\n+", rendered):
        cleaned = sentence.strip(" \t;")
        if not cleaned:
            continue
        if _KO_UNSUPPORTED_PROPOSAL_RE.search(cleaned) and not _KO_SAFE_REVIEW_CUE_RE.search(cleaned):
            removed = True
            continue
        kept.append(cleaned)

    if removed and not any(_KO_SAFE_REVIEW_CUE_RE.search(item) for item in kept):
        kept.append("요청 사항은 현장 여건, 소관 권한 및 관련 기준을 확인한 뒤 처리 가능 여부를 검토하겠습니다.")
    return " ".join(kept).strip() or rendered


def _context_constraint_sentence(context: List[Dict[str, Any]] | None) -> str:
    for item in context or []:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "")
        for sentence in re.split(r"(?<=[.!?。])\s+|\n+", snippet):
            cleaned = sentence.strip()
            if cleaned and _KO_CONTEXT_CONSTRAINT_RE.search(cleaned):
                return cleaned[:180]
    return ""


def _apply_context_constraint_guard(
    text: str,
    context: List[Dict[str, Any]] | None = None,
) -> str:
    rendered = str(text or "").strip()
    constraint = _context_constraint_sentence(context)
    if not rendered or not constraint:
        return rendered

    kept: List[str] = []
    removed = False
    for sentence in re.split(r"(?<=[.!?。])\s+|\n+", rendered):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        if (
            _KO_OVERACTIVE_ACTION_RE.search(cleaned)
            and _KO_OVERACTIVE_TONE_RE.search(cleaned)
            and not _KO_CONTEXT_CONSTRAINT_RE.search(cleaned)
        ):
            removed = True
            continue
        kept.append(cleaned)

    if removed:
        kept.append(
            f"검색 근거상 {constraint} 이 사안은 해당 제약과 소관 권한을 우선 확인한 뒤 처리 가능 여부를 판단하겠습니다."
        )
    return " ".join(kept).strip() or rendered


def _fallback_review_body(citations: List[Dict[str, Any]]) -> str:
    if citations:
        return (
            "검색된 유사 사례는 처리 방향을 검토하기 위한 참고자료이며 현재 민원의 사실관계나 조치 결정을 "
            "직접 확정하지는 않습니다. 담당부서에서 현장 여건, 소관 권한, 관련 기준을 확인한 뒤 "
            "처리 가능 여부와 후속 절차를 안내드리겠습니다."
        )
    return (
        "접수 내용과 관련 자료를 우선 확인하고, 담당부서 검토를 거쳐 처리 가능 여부와 후속 안내 사항을 "
        "정리해 안내드리겠습니다."
    )


def format_civil_reply_answer(
    answer: str,
    citations: List[Dict[str, Any]],
    *,
    complaint: str = "",
    context: List[Dict[str, Any]] | None = None,
) -> str:
    """민원 회신문 answer를 출처 토큰 없는 고정 1~4항 구조로 정규화한다."""
    rendered = sanitize_answer_text(answer)
    rendered = _strip_citation_tokens(rendered)
    rendered = _normalize_structured_answer_text(rendered)
    rendered = _remove_generic_bridge_phrases(rendered)
    body = _strip_standard_reply_shell(rendered)
    body = _normalize_review_body(body)
    body = _soften_risky_sentences(body)
    body = _remove_unsupported_proposals(body)
    body = _remove_precedent_fact_leakage(
        body,
        complaint=complaint,
        context=context,
    )
    body = _apply_context_constraint_guard(body, context=context)
    if not body:
        body = _fallback_review_body(citations)
    body = _trim_incomplete_trailing_sentence(body, citations)

    reply = (
        f"{_CIVIL_REPLY_PREFIX_1}\n\n"
        f"{_CIVIL_REPLY_PREFIX_2}\n\n"
        f"{_CIVIL_REPLY_PREFIX_3} {body}\n\n"
        f"{_CIVIL_REPLY_CLOSING}"
    )
    return reply.strip()


def normalize_citations(raw_citations: List[Dict[str, Any]], context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """context와 정합한 citation만 ref_id를 부여해 정규화한다."""
    context_by_chunk = {
        str(item.get("chunk_id", "")): item
        for item in context
        if str(item.get("chunk_id", ""))
    }

    source = raw_citations if raw_citations else context[:3]
    normalized: List[Dict[str, Any]] = []

    for item in source:
        if not isinstance(item, dict):
            continue

        raw_chunk_id = str(item.get("chunk_id") or "")
        ctx = context_by_chunk.get(raw_chunk_id, {})

        chunk_id = raw_chunk_id or str(ctx.get("chunk_id") or "")
        if not chunk_id:
            continue

        if chunk_id not in context_by_chunk:
            continue

        ctx = context_by_chunk[chunk_id]
        case_id = str(item.get("case_id") or ctx.get("case_id") or "")
        context_case_id = str(ctx.get("case_id") or "")
        if not case_id or (context_case_id and case_id != context_case_id):
            continue

        doc_id = str(item.get("doc_id") or ctx.get("doc_id") or "").strip() or None
        snippet = str(item.get("snippet") or ctx.get("snippet") or "").strip()

        if not snippet or not chunk_id:
            continue

        citation: Dict[str, Any] = {
            "ref_id": len(normalized) + 1,
            "chunk_id": chunk_id,
            "case_id": case_id,
            "snippet": snippet,
            "relevance_score": _safe_float(item.get("relevance_score", item.get("score", 0.0))),
            "source": str(item.get("source") or "retrieval"),
        }
        if doc_id:
            citation["doc_id"] = doc_id

        normalized.append(citation)

    # 모델이 citations를 반환했더라도(=raw_citations 존재) 전부 무효로 필터링되면
    # 컨텍스트 기반 fallback을 사용해 최소 1개 citation을 확보한다.
    if raw_citations and not normalized and context:
        return normalize_citations([], context)

    return normalized


def ensure_citation_tokens(
    answer: str,
    citations: List[Dict[str, Any]],
    *,
    complaint: str = "",
    context: List[Dict[str, Any]] | None = None,
) -> str:
    """호환용 이름. answer의 출처 토큰을 제거하고 회신문 형식을 정규화한다."""
    rendered = sanitize_answer_text(answer)
    if not rendered:
        if citations:
            rendered = _fallback_review_body(citations)
        else:
            rendered = (
                "현재 확인 가능한 자료가 충분하지 않아 담당부서 확인 및 추가 검토가 필요합니다. "
                "민원 취지, 발생 장소, 관련 자료가 확인되면 현장 여건과 행정 처리 기준을 종합적으로 검토하겠습니다."
            )
    return format_civil_reply_answer(
        rendered,
        citations,
        complaint=complaint,
        context=context,
    )


def _answer_quality_warnings(
    answer: str,
    *,
    complaint: str = "",
    context: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    rendered = str(answer or "")
    if "\\n" in rendered or re.search(
        r"(?i)액션\s*아이템|action\s*item|섹션\s*\d+|\[REDACTED:[^\]]*$",
        rendered,
    ):
        warnings.append(
            {
                "code": "ANSWER_OUTPUT_ARTIFACT",
                "message": "answer에 내부 라벨, 이스케이프 또는 잘린 비식별 문자열이 남아 있습니다.",
            }
        )
    commitment_matches = [
        match.group(0)
        for match in _COMMITMENT_PATTERN.finditer(rendered)
        if not re.search(
            r"가능\s*여부|필요성|현장\s*확인|소관\s*권한|관련\s*기준|방안을\s*검토|계획을\s*검토",
            match.group(0),
        )
    ]
    if commitment_matches:
        warnings.append(
            {
                "code": "UNSUPPORTED_COMMITMENT_RISK",
                "message": "근거 확인이 필요한 행정 조치를 확정적으로 약속하는 표현이 있습니다.",
            }
        )
    if _UNVERIFIED_FACT_PATTERN.search(rendered):
        warnings.append(
            {
                "code": "UNVERIFIED_FACT_RISK",
                "message": "현재 민원에서 확인되지 않은 사실을 확정적으로 표현했을 가능성이 있습니다.",
            }
        )

    if complaint:
        complaint_terms = _meaningful_terms(complaint)
        answer_terms = _meaningful_terms(_strip_standard_reply_shell(rendered))
        if len(complaint_terms) >= 3:
            overlap = len(complaint_terms & answer_terms)
            if overlap < 2:
                warnings.append(
                    {
                        "code": "ANSWER_REQUEST_MISMATCH",
                        "message": "생성 답변이 현재 민원의 핵심 용어를 충분히 다루지 않습니다.",
                    }
                )
        if context:
            context_terms: set[str] = set()
            context_texts: List[str] = []
            for item in context:
                if isinstance(item, dict):
                    snippet = str(item.get("snippet") or "")
                    context_texts.append(snippet)
                    context_terms.update(_meaningful_terms(snippet))
            if (
                commitment_matches
                and _CONSTRAINT_PATTERN.search(" ".join(context_texts))
                and not _CONSTRAINT_PATTERN.search(rendered)
            ):
                warnings.append(
                    {
                        "code": "CONTEXT_CONSTRAINT_CONFLICT",
                        "message": "검색 근거의 처리 불가·소관 제약과 충돌할 수 있는 확정 조치 표현이 있습니다.",
                    }
                )
            context_only = context_terms - complaint_terms
            leaked_sentences = []
            for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", rendered):
                sentence_terms = _meaningful_terms(sentence)
                if (
                    _CONCRETE_PRECEDENT_CUE.search(sentence)
                    and len(sentence_terms & context_only) >= 2
                    and len(sentence_terms & complaint_terms) <= 1
                ):
                    leaked_sentences.append(sentence)
            if leaked_sentences:
                warnings.append(
                    {
                        "code": "PRECEDENT_FACT_LEAKAGE_RISK",
                        "message": "유사 사례의 세부 사실이 현재 민원 답변에 혼입되었을 가능성이 있습니다.",
                    }
                )
    return warnings


def build_validation_result(
    answer: str,
    citations: List[Dict[str, Any]],
    limitations: str,
    context: List[Dict[str, Any]],
    complaint: str = "",
) -> Dict[str, Any]:
    """QA 응답 검증 결과(is_valid/errors/warnings)를 생성한다."""
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    warnings.extend(
        _answer_quality_warnings(
            answer,
            complaint=complaint,
            context=context,
        )
    )

    if "폴백" in limitations:
        warnings.append(
            {
                "code": "FALLBACK_RESPONSE",
                "message": "모델 파싱 불안정으로 폴백 답변이 제공되었습니다.",
            }
        )

    if not citations:
        warnings.append(
            {
                "code": "EMPTY_CITATIONS",
                "message": "근거 citation이 비어 있습니다.",
            }
        )

    if not limitations.strip():
        errors.append(
            {
                "code": "LIMITATIONS_REQUIRED",
                "message": "limitations는 빈 문자열일 수 없습니다.",
            }
        )

    if not citations:
        errors.append(
            {
                "code": "CITATIONS_REQUIRED",
                "message": "성공 응답에는 최소 1개 이상의 citation이 필요합니다.",
            }
        )

    ref_ids = [int(item.get("ref_id", 0)) for item in citations]
    if len(ref_ids) != len(set(ref_ids)):
        errors.append(
            {
                "code": "DUPLICATE_REF_ID",
                "message": "citations.ref_id는 응답 내에서 유일해야 합니다.",
            }
        )

    if _CITE_TOKEN_PATTERN.search(answer or "") or re.search(r"\[출처\s*\d+\]", answer or ""):
        errors.append(
            {
                "code": "CITATION_TOKEN_IN_ANSWER",
                "message": "answer 본문에는 출처 토큰을 포함하지 않고 citations 필드로만 근거를 제공해야 합니다.",
            }
        )

    context_by_chunk = {
        str(item.get("chunk_id", "")): str(item.get("case_id", ""))
        for item in context
        if str(item.get("chunk_id", ""))
    }

    for citation in citations:
        chunk_id = str(citation.get("chunk_id") or "")
        case_id = str(citation.get("case_id") or "")
        snippet = str(citation.get("snippet") or "").strip()

        if not snippet:
            errors.append(
                {
                    "code": "EMPTY_SNIPPET",
                    "message": "citation.snippet은 빈 문자열일 수 없습니다.",
                }
            )

        if chunk_id not in context_by_chunk:
            errors.append(
                {
                    "code": "CHUNK_NOT_IN_CONTEXT",
                    "message": f"chunk_id '{chunk_id}'가 검색 결과에 존재하지 않습니다.",
                }
            )
            continue

        if case_id != context_by_chunk[chunk_id]:
            errors.append(
                {
                    "code": "CASE_ID_MISMATCH",
                    "message": f"chunk_id '{chunk_id}'의 case_id가 검색 결과와 일치하지 않습니다.",
                }
            )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
