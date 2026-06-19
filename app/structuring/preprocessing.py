"""전처리 데이터(processed_consulting_data.json) → BE1 구조화 입력 어댑터.

원천 consulting_content = "제목 + Q(민원인) + A(상담사)".
`civil_text()`와 `to_structuring_record()`는 구조화 안정성을 위해 민원인 원문만 사용한다.
검색 재색인 성능을 위해 답변 포함 본문이 필요할 때는 `civil_text_with_answer()`를 별도로 사용한다.

입력 레코드(전처리 산출) 주요 키:
  source_id, source, consulting_date, consulting_category,
  title, client_question, consultant_answer, ...
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


_MARKER_RE = re.compile(
    r"(?m)^[ \t\"'“”‘’「『]*"
    r"(?P<label>제목|Q|질문|문의|A|답변)"
    r"[ \t]*[:：.]"
    r"[ \t]*"
)
_SPEAKER_RE = re.compile(
    r"(?m)^[ \t\"'“”‘’「『]*"
    r"(?P<label>고객|민원인|내담자|문의자|질문자|사용자|상담원|상담사|상담자|담당자|직원|공무원)"
    r"[ \t]*[:：]"
    r"[ \t]*"
)
_QUESTION_LABELS = {"Q", "질문", "문의"}
_ANSWER_LABELS = {"A", "답변"}
_CUSTOMER_SPEAKERS = {"고객", "민원인", "내담자", "문의자", "질문자", "사용자"}
_AGENT_SPEAKERS = {"상담원", "상담사", "상담자", "담당자", "직원", "공무원"}
_PLACEHOLDER_TITLES = {"", "제목없음", "처리실패", "파싱실패"}
_HTML_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_content(text: Any) -> str:
    """원천 데이터의 줄바꿈/공백 인코딩 흔들림을 정리한다."""
    if text is None:
        return ""

    cleaned = str(text)
    cleaned = cleaned.replace("_x000D_\n", "\n")
    cleaned = cleaned.replace("_x000D_", "\n")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("\ufeff", "").replace("\u00a0", " ")
    return cleaned.strip()


def _normalize_text(text: Any) -> str:
    """구조화 입력에 들어갈 수 있도록 과도한 공백만 정규화한다."""
    normalized = _clean_content(text)
    if not normalized:
        return ""

    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"[ \t]*\n[ \t]*", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip(" \t\n\"'“”‘’「『」』")


def _clean_policy_qna_text(text: Any) -> str:
    """정책 Q&A API 본문의 HTML 엔티티와 줄바꿈 태그를 일반 텍스트로 정리한다."""
    unescaped = html.unescape(str(text or ""))
    unescaped = _HTML_BR_RE.sub("\n", unescaped)
    unescaped = _HTML_TAG_RE.sub(" ", unescaped)
    return _normalize_text(unescaped)


def _policy_qna_category(data: Dict[str, Any]) -> str:
    """정책 Q&A 원천에서 보수적으로 카테고리 역할을 할 부서명을 고른다."""
    subj_list = data.get("subjList")
    if isinstance(subj_list, list) and subj_list:
        names = [
            _clean_policy_qna_text(item.get("subjName") or item.get("name") or item.get("subjNm"))
            for item in subj_list
            if isinstance(item, dict)
        ]
        joined = " > ".join(name for name in names if name)
        if joined:
            return joined
    return _clean_policy_qna_text(data.get("deptName") or data.get("dutySctnNm"))


def _unwrap_policy_qna_record(raw_record: Dict[str, Any]) -> Dict[str, Any]:
    """resultData 래퍼형 정책 Q&A 원천을 기존 전처리 필드로 변환한다."""
    data = raw_record.get("resultData") if isinstance(raw_record.get("resultData"), dict) else raw_record
    if not isinstance(data, dict) or not any(key in data for key in ("qnaTitl", "qstnCntnCl", "ansCntnCl")):
        return raw_record

    title = _clean_policy_qna_text(data.get("qnaTitl"))
    question = _clean_policy_qna_text(data.get("qstnCntnCl"))
    answer = _clean_policy_qna_text(data.get("ansCntnCl"))
    source_id = _clean_policy_qna_text(data.get("faqNo") or raw_record.get("source_id"))
    source = _clean_policy_qna_text(data.get("ancName") or data.get("deptName") or raw_record.get("source"))

    return {
        **raw_record,
        "source_id": source_id,
        "source": source,
        "consulting_date": data.get("regDate") or raw_record.get("consulting_date"),
        "consulting_category": _policy_qna_category(data),
        "title": title,
        "client_question": question,
        "consultant_answer": answer,
        "consulting_turns": "2" if answer else "1",
        "original_length": len(question),
    }


def _split_labeled_sections(text: str, marker_re: re.Pattern[str]) -> List[Tuple[str, str]]:
    """마커 위치를 기준으로 본문을 잘라 label/body 목록을 만든다."""
    matches = list(marker_re.finditer(text))
    sections: List[Tuple[str, str]] = []

    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        label = match.group("label").strip()
        body = _normalize_text(text[start:end])
        sections.append((label, body))

    return sections


def _make_title_from_question(question: str) -> str:
    """대화형 데이터처럼 제목이 없는 경우 첫 민원인 발화로 짧은 제목을 만든다."""
    first_line = _normalize_text(question).split("\n", 1)[0]
    if len(first_line) <= 80:
        return first_line
    return first_line[:80].rstrip()


def _parse_marker_content(content: str) -> Dict[str, str]:
    """제목/Q/A 또는 제목/Q/답변 형식을 분리한다."""
    sections = _split_labeled_sections(content, _MARKER_RE)
    if not sections:
        return {}

    title_parts: List[str] = []
    question_parts: List[str] = []
    answer_parts: List[str] = []
    active_part = ""

    for label, body in sections:
        if label == "제목" and not active_part:
            title_parts.append(body)
            continue

        if label in _QUESTION_LABELS and active_part != "answer":
            question_parts.append(body)
            active_part = "question"
        elif label in _ANSWER_LABELS:
            answer_parts.append(body)
            active_part = "answer"
        elif active_part == "question":
            question_parts.append(f"{label}: {body}")
        elif active_part == "answer":
            answer_parts.append(f"{label}: {body}")
        else:
            title_parts.append(body)

    title = _normalize_text("\n".join(title_parts))
    question = _normalize_text("\n".join(question_parts))
    answer = _normalize_text("\n".join(answer_parts))

    return {
        "title": title,
        "client_question": question,
        "consultant_answer": answer,
    }


def _parse_dialogue_content(content: str) -> Dict[str, str]:
    """고객/상담원 대화 형식에서 민원인 발화와 답변 발화를 분리한다."""
    sections = _split_labeled_sections(content, _SPEAKER_RE)
    if not sections:
        return {}

    question_parts: List[str] = []
    answer_parts: List[str] = []

    for label, body in sections:
        if label in _CUSTOMER_SPEAKERS:
            question_parts.append(body)
        elif label in _AGENT_SPEAKERS:
            answer_parts.append(body)

    question = _normalize_text("\n".join(question_parts))
    answer = _normalize_text("\n".join(answer_parts))

    return {
        "title": _make_title_from_question(question),
        "client_question": question,
        "consultant_answer": answer,
    }


def parse_consulting_content(content: Any, source: str = "") -> Dict[str, str]:
    """raw consulting_content를 제목/민원인 질문/상담사 답변으로 분리한다.

    대부분 지역은 제목/Q/A 마커를 사용하고, 국립아시아문화전당은
    고객/상담원 화자 라벨을 사용한다. 파싱 결과는 민원인 질문과 상담사 답변을
    별도 필드에 보존하고, 구조화/검색 입력은 정책상 두 본문을 함께 사용한다.
    """
    cleaned = _clean_content(content)
    if not cleaned:
        return {"title": "", "client_question": "", "consultant_answer": ""}

    marker_parsed = _parse_marker_content(cleaned)
    if marker_parsed and (
        marker_parsed.get("client_question") or marker_parsed.get("consultant_answer")
    ):
        return marker_parsed

    dialogue_parsed = _parse_dialogue_content(cleaned)
    if dialogue_parsed and dialogue_parsed.get("client_question"):
        return dialogue_parsed

    # 알 수 없는 단일 본문 형식은 답변을 섞었다고 단정할 근거가 없어 원문을 질문으로 둔다.
    return {"title": "", "client_question": _normalize_text(cleaned), "consultant_answer": ""}


def format_consulting_date(date_value: Any) -> str:
    """YYYYMMDD 형식의 원천 날짜를 YYYY-MM-DD로 정규화한다."""
    date_text = str(date_value or "").strip()
    if len(date_text) == 8 and date_text.isdigit():
        return f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
    return date_text


def normalize_category(category: Any) -> str:
    """빈 카테고리를 미분류로 통일한다."""
    normalized = str(category or "").strip()
    return normalized or "미분류"


def process_raw_record(raw_record: Dict[str, Any]) -> Dict[str, Any]:
    """원천 레코드(raw_data) 1건을 processed 레코드 형태로 변환한다."""
    normalized_raw = _unwrap_policy_qna_record(raw_record)
    parsed = {
        "title": _normalize_text(normalized_raw.get("title")),
        "client_question": _normalize_text(normalized_raw.get("client_question")),
        "consultant_answer": _normalize_text(normalized_raw.get("consultant_answer")),
    }
    if normalized_raw.get("consulting_content") and not parsed["client_question"]:
        parsed = parse_consulting_content(
            normalized_raw.get("consulting_content"),
            source=str(normalized_raw.get("source") or ""),
        )

    return {
        "source_id": str(normalized_raw.get("source_id") or "").strip(),
        "source": str(normalized_raw.get("source") or "").strip(),
        "consulting_date": format_consulting_date(normalized_raw.get("consulting_date")),
        "consulting_category": normalize_category(normalized_raw.get("consulting_category")),
        "title": parsed["title"],
        "client_question": parsed["client_question"],
        "consultant_answer": parsed["consultant_answer"],
        "consulting_turns": normalized_raw.get("consulting_turns"),
        "original_length": normalized_raw.get("original_length", normalized_raw.get("consulting_length")),
        "parsing_success": bool(parsed["client_question"] or parsed["title"]),
    }


def _prepared_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """processed/raw 어느 쪽이 들어와도 civil_text가 읽을 수 있는 필드를 만든다."""
    prepared = _unwrap_policy_qna_record(dict(rec))
    if prepared.get("consulting_content") and not str(prepared.get("client_question") or "").strip():
        parsed = parse_consulting_content(
            prepared.get("consulting_content"),
            source=str(prepared.get("source") or ""),
        )
        for key, value in parsed.items():
            prepared.setdefault(key, value)
            if not str(prepared.get(key) or "").strip():
                prepared[key] = value
    return prepared


def _clean_title(title: Any) -> str:
    normalized = _normalize_text(title)
    return "" if normalized in _PLACEHOLDER_TITLES else normalized


def civil_text(rec: Dict[str, Any]) -> str:
    """민원인 원문 전용 본문 = title + client_question (상담사 답변 제외).

    title 을 포함하는 이유: Q 가 비었거나("…내용이 title 에"), Q 가 제목을
    참조("제목 내용처럼")하는 케이스에서 title 이 본문 신호를 보강한다.
    """
    prepared = _prepared_record(rec)
    title = _clean_title(prepared.get("title"))
    q = _normalize_text(prepared.get("client_question"))
    if title and q:
        # Q 가 이미 title 로 시작하면 중복 방지
        return q if q.startswith(title) else f"{title}\n{q}"
    return (q or title).strip()


def civil_text_with_answer(rec: Dict[str, Any]) -> str:
    """검색 색인용 본문 = 민원인 원문 + 상담사 답변.

    BE2 재색인 검증에서 상담사 답변을 제외하면 검색 본문이 빈약해져
    검색 지표가 하락했다. 구조화/담당부서/긴급도 등 민원 의도 분석에는
    `civil_text()`를 사용하고, BE2 검색 인덱싱 본문에만 이 함수를 사용한다.
    """
    prepared = _prepared_record(rec)
    base = civil_text(prepared)
    answer = _normalize_text(prepared.get("consultant_answer"))
    if base and answer:
        return f"{base}\n{answer}"
    return (base or answer).strip()


def to_structuring_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """전처리 레코드 → StructuringService.structure() 입력 dict."""
    prepared = _prepared_record(rec)
    source = str(prepared.get("source") or prepared.get("region") or "").strip()
    category = normalize_category(prepared.get("consulting_category") or prepared.get("category"))
    original_length = prepared.get("original_length", prepared.get("consulting_length"))

    return {
        "case_id": str(prepared.get("source_id") or prepared.get("case_id") or "").strip(),
        "text": civil_text(prepared),
        "category": category,
        "region": source,
        "created_at": format_consulting_date(prepared.get("consulting_date") or prepared.get("created_at")),
        "source": source,
        "metadata": {
            "consulting_turns": prepared.get("consulting_turns"),
            "original_length": original_length,
            "parsing_success": prepared.get("parsing_success"),
        },
    }


def load_processed(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "data", "items"):
            records = data.get(key)
            if isinstance(records, list):
                return records
    return []


def load_civil_index(path: str) -> Dict[str, Dict[str, str]]:
    """source_id → {text(민원인 원문), category} 인덱스 (긴급도 데이터셋 조인용)."""
    idx: Dict[str, Dict[str, str]] = {}
    for rec in load_processed(path):
        sid = str(rec.get("source_id") or "").strip()
        if sid:
            idx[sid] = {"text": civil_text(rec),
                        "category": str(rec.get("consulting_category") or "").strip()}
    return idx
