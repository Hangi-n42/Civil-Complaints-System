"""Strict 0-10 LLM-Rubric proxy for generated civil-affairs replies.

The evaluator keeps the paper-inspired Q0-Q8 dimensions, but calibrates style,
length, density, and task completion against real ``consultant_answer`` records
from ``data/processed/processed_consulting_data.json``.

It is still a deterministic proxy, not the learned calibration network from the
paper. When a generated case_id matches a processed source_id, the paired real
reply is additionally used as a content/style reference.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_PATH = PROJECT_ROOT / "data" / "processed" / "processed_consulting_data.json"
SCORE_MIN = 0.0
SCORE_MAX = 10.0
DEFAULT_EVALUATION_SCOPE = "generated_body"

RUBRIC_DESCRIPTIONS: Dict[str, str] = {
    "Q0": "종합 만족도: 실제 민원 회신과 비교했을 때 전반적으로 만족할 가능성",
    "Q1": "회신 품질: 실제 공공기관 회신에 가까운 자연스러운 어조와 형식",
    "Q2": "근거 충분성: 검색 근거와 실제 회신 기준으로 처리 방향을 설명하는 정도",
    "Q3": "인용 포함: 모델이 구조화 citations를 충분히 생성한 정도",
    "Q4": "인용 정확성: 모델 원출력 citations가 검색 컨텍스트와 정확히 매칭되는 정도",
    "Q5": "최적 출처성: 유효 근거를 우선 사용하고 실제 회신 핵심과 정렬된 정도",
    "Q6": "중복 없음: 반복, 템플릿 남용, 구조 문자열, 디버그 정보가 없는 정도",
    "Q7": "길이·밀도: 실제 consultant_answer 분포에 가까운 길이와 문장 밀도",
    "Q8": "업무 완결성: 민원 요지, 구체 검토, 조치·제약, 후속 안내가 완결된 정도",
}

WEIGHTS: Dict[str, float] = {
    "Q1": 0.14,
    "Q2": 0.14,
    "Q3": 0.10,
    "Q4": 0.14,
    "Q5": 0.08,
    "Q6": 0.12,
    "Q7": 0.10,
    "Q8": 0.18,
}

_GENERIC_PHRASES = (
    "위 내용을 바탕으로 담당부서에서는 현장 여건, 관련 기준, 유사 처리 사례를 확인한 뒤",
    "필요한 조치 가능 여부를 판단할 수 있습니다",
    "접수 내용과 관련 자료를 확인한 뒤",
    "현장 여건, 행정 처리 기준, 조치 가능 범위를 종합적으로 검토하겠습니다",
    "확인 결과에 따라 필요한 안내 또는 후속 조치가 이루어질 수 있습니다",
    "구체적인 처리 가능 여부와 조치 일정은 담당부서의 현장 확인과 관계 기준 검토 후",
)

_COMMON_REPLY_PHRASES = (
    "귀하께서 신청하신 민원에 대한 검토 결과를 다음과 같이 답변드립니다",
    "귀하의 민원 내용은 제기하신 불편 사항에 대한 검토 및 조치 요청으로 이해됩니다",
    "접수된 민원 취지와 관련 근거를 함께 고려하여 처리 방향을 검토하는 사안입니다",
    "검토 의견은 다음과 같습니다",
    "답변 내용에 대한 추가 설명이 필요한 경우 담당부서로 문의해 주시면",
    "세부 검토 결과와 후속 절차를 친절히 안내해 드리겠습니다",
    "감사합니다",
    "끝",
)

_SPECIFICITY_PATTERNS: Dict[str, re.Pattern[str]] = {
    "date_or_schedule": re.compile(
        r"\d{4}\s*년|\d{1,2}\s*월|\d{1,2}\s*일|'\d{2}\.?\s*\d{1,2}|"
        r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}|상반기|하반기|분기|연내|예정"
    ),
    "law_or_policy": re.compile(r"「[^」]+」|[가-힣A-Za-z]+법\s*제?\d+조|법률|조례|시행령|규정|지침|고시"),
    "department": re.compile(r"주무관|담당자|담당부서|[가-힣A-Za-z]{2,}(?:과|팀|센터|공단|사업소)"),
    "constraint": re.compile(r"어렵|불가|양해|검토\s*중|추후|순차|현장\s*확인|관계\s*부서|사정에\s*따라|예산"),
    "measure": re.compile(r"\d+(?:\.\d+)?\s*(?:억|만|천|원|km|㎞|m|㎡|건|회|개|명|%)"),
    "action": re.compile(r"조치|통보|점검|확인|검토|시정|보수|설치|철거|협의|추진|안내|개선"),
}

_STOP_TERMS = {
    "귀하", "께서", "민원", "내용", "검토", "답변", "관련", "대한", "다음과", "같이",
    "신청하신", "문의하신", "문의", "결과", "사항", "필요한", "경우", "담당부서",
    "안내", "드립니다", "있습니다", "합니다", "해당", "요청", "처리", "확인", "추가",
    "설명", "후속", "바랍니다", "주시기", "감사합니다", "따라", "관계", "운영",
}

_REFERENCE_CONSTRAINT_RE = re.compile(
    r"불가|어렵|곤란|사유지|개인\s*소유|관리사무소|소유자|관리주체|"
    r"폭이?\s*좁|확폭|예정된?\s*공사|공사\s*예정|관할\s*(?:사항이\s*)?아니|소관이\s*아니"
)
_STRONG_COMMITMENT_RE = re.compile(
    r"(?:즉시|신속히|우선적으로)?\s*"
    r"(?:설치|철거|제거|이동|신설|건설|매입|보수|정비|폐쇄|단속|시정|"
    r"개선|확대|개방|허가|지정|도입|구축|확보|수립|방역)"
    r"(?:을|를|에)?\s*(?:실시|시행|추진|완료|진행|조치)?"
    r"(?:하겠습니다|할\s*예정입니다|할\s*계획입니다)|"
    r"(?:설치|철거|제거|이동|신설|건설|매입|보수|정비|폐쇄|단속|시정|"
    r"개선|확대|개방|허가|지정|도입|구축|확보|수립|방역)\s*예정입니다|"
    r"예산을?\s*확보하겠습니다|공청회를?\s*실시하겠습니다|"
    r"주차\s*공간으로\s*개발하여\s*즉시\s*활용합니다"
)
_PRIVATE_AUTHORITY_RE = re.compile(r"사유지|개인\s*소유|관리사무소|소유자|관리주체")
_AGENCY_ACTION_RE = re.compile(
    r"(?:시|군|구|담당부서|우리\s*기관|해당\s*부서).{0,50}"
    r"(?:설치|철거|제거|이동|신설|건설|보수|정비|폐쇄|단속|시정|개선|"
    r"확대|개방|허가|지정|도입).{0,20}"
    r"(?:하겠습니다|할\s*예정입니다|할\s*계획입니다)"
)
_POSITIVE_DISPOSITION_RE = re.compile(
    r"(?:허용|승인|개방|이동|추가\s*지정|우선적으로\s*제거|"
    r"주말\s*사용\s*협의|사용.{0,12}협의|즉시\s*활용|신규\s*시설\s*건설|"
    r"지원\s*방안을\s*마련)"
)
_UNVERIFIED_ASSERTION_RE = re.compile(
    r"확인하였습니다|보고되었습니다|이미\s*예정|진행\s*중입니다|완료되었습니다"
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_cases(path: Path | None) -> Dict[str, Dict[str, Any]]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        raise ValueError("cases file must be a JSON list")
    cases: Dict[str, Dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        case_id = str(
            item.get("case_id")
            or item.get("source_id")
            or item.get("complaint_id")
            or ""
        ).strip()
        if case_id:
            cases[case_id] = item
    return cases


def _read_reference_answers(
    path: Path,
    *,
    evaluation_scope: str = DEFAULT_EVALUATION_SCOPE,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, list):
        raise ValueError("reference data must be a JSON list")

    references: Dict[str, str] = {}
    answers: List[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "").strip()
        answer = str(item.get("consultant_answer") or "").strip()
        if not answer:
            continue
        answers.append(answer)
        if source_id:
            references[source_id] = answer
    return references, build_reference_profile(
        answers,
        source_path=path,
        evaluation_scope=evaluation_scope,
    )


def _clip_score(value: float) -> float:
    return round(max(SCORE_MIN, min(SCORE_MAX, float(value))), 1)


def _average(values: Iterable[float]) -> float:
    vals = list(values)
    return statistics.fmean(vals) if vals else 0.0


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text or "")
    return len([part for part in parts if part.strip()])


def _paragraph_count(text: str) -> int:
    return len([part for part in re.split(r"\n\s*\n", text or "") if part.strip()])


def extract_generated_body(text: str) -> str:
    """고정된 1·2·4문단을 제외하고 모델이 작성한 3문단 본문만 반환한다."""
    rendered = str(text or "").strip()
    if not rendered:
        return ""
    start_match = re.search(
        r"(?:^|\n|\s)3[.．)]\s*검토\s*의견은\s*다음과\s*같습니다[.。]?\s*",
        rendered,
    )
    if not start_match:
        return rendered
    body = rendered[start_match.end():]
    end_match = re.search(
        r"(?:^|\n|\s)4[.．)]\s*답변\s*내용에\s*대한\s*추가\s*설명이\s*필요한\s*경우",
        body,
    )
    if end_match:
        body = body[:end_match.start()]
    return body.strip()


def extract_reference_body(text: str) -> str:
    """실제 consultant_answer에서 인사·문의 안내를 덜어낸 실질 본문을 반환한다."""
    rendered = extract_generated_body(text)
    if not rendered:
        return ""
    rendered = re.sub(
        r"(?:기타|추가|그\s*밖에)?\s*(?:문의|궁금하신)\s*(?:사항|점).*?$",
        "",
        rendered,
        flags=re.DOTALL,
    )
    rendered = re.sub(
        r"(?:귀하의\s*가정|항상\s*귀하).*?(?:기원합니다|바랍니다)[.。]?",
        " ",
        rendered,
    )
    for phrase in _COMMON_REPLY_PHRASES:
        rendered = rendered.replace(phrase, " ")
    rendered = re.sub(r"(?m)^\s*(?:\d+|[가나다라마바사아자차카타파하])[.．)]\s*", "", rendered)
    return re.sub(r"\s+", " ", rendered).strip(" .。")


def _reply_shell_diagnostics(text: str) -> Dict[str, Any]:
    rendered = str(text or "")
    sections = {
        str(index): bool(re.search(rf"(?m)^\s*{index}[.．)]\s*", rendered))
        for index in range(1, 5)
    }
    closing_count = rendered.count("감사합니다. 끝.")
    return {
        "sections": sections,
        "all_sections_present": all(sections.values()),
        "closing_count": closing_count,
        "single_closing": closing_count == 1,
        "generated_body_extracted": extract_generated_body(rendered) != rendered.strip(),
    }


def _specificity_signals(text: str) -> List[str]:
    return [name for name, pattern in _SPECIFICITY_PATTERNS.items() if pattern.search(text or "")]


def _feature_flags(text: str) -> Dict[str, bool]:
    rendered = text or ""
    return {
        "numbered": bool(re.search(r"(?m)^\s*1[.．)]", rendered)),
        "polite": bool(re.search(r"귀하|민원인|질의", rendered)),
        "closing": bool(re.search(r"감사합니다|바랍니다|기원합니다|끝\.", rendered)),
        "contact": bool(re.search(r"문의|연락|담당자|주무관|담당부서|\d{2,4}-\d{3,4}-\d{4}", rendered)),
        "law_or_policy": bool(_SPECIFICITY_PATTERNS["law_or_policy"].search(rendered)),
        "date_or_schedule": bool(_SPECIFICITY_PATTERNS["date_or_schedule"].search(rendered)),
        "department": bool(_SPECIFICITY_PATTERNS["department"].search(rendered)),
        "constraint": bool(_SPECIFICITY_PATTERNS["constraint"].search(rendered)),
        "action": bool(_SPECIFICITY_PATTERNS["action"].search(rendered)),
    }


def build_reference_profile(
    answers: Sequence[str],
    source_path: Path | None = None,
    *,
    evaluation_scope: str = DEFAULT_EVALUATION_SCOPE,
) -> Dict[str, Any]:
    valid_full = [str(answer).strip() for answer in answers if str(answer).strip()]
    valid = (
        [extract_reference_body(answer) for answer in valid_full]
        if evaluation_scope == "generated_body"
        else valid_full
    )
    valid = [answer for answer in valid if answer]
    lengths = [len(answer) for answer in valid]
    sentences = [_sentence_count(answer) for answer in valid]
    paragraphs = [_paragraph_count(answer) for answer in valid]
    flags = [_feature_flags(answer) for answer in valid]

    def stats(values: Sequence[float]) -> Dict[str, float]:
        return {
            "p05": round(_quantile(values, 0.05), 2),
            "p10": round(_quantile(values, 0.10), 2),
            "p25": round(_quantile(values, 0.25), 2),
            "median": round(_quantile(values, 0.50), 2),
            "p75": round(_quantile(values, 0.75), 2),
            "p90": round(_quantile(values, 0.90), 2),
            "p95": round(_quantile(values, 0.95), 2),
            "mean": round(_average(values), 2),
        }

    return {
        "source_path": str(source_path) if source_path else None,
        "evaluation_scope": evaluation_scope,
        "valid_answer_count": len(valid),
        "length_chars": stats(lengths),
        "sentence_count": stats(sentences),
        "paragraph_count": stats(paragraphs),
        "feature_rates": {
            key: round(_average(1.0 if row[key] else 0.0 for row in flags), 4)
            for key in flags[0]
        } if flags else {},
    }


def _answer_from_row(row: Dict[str, Any], answer_field: str) -> str:
    for key in (answer_field, "parsed_answer_repaired", "parsed_answer", "parsed_answer_strict", "answer"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _has_debug_noise(text: str) -> bool:
    return bool(
        re.search(
            r"chunk_id=|case_id=|score=|CASE-\d+__chunk-\d+|```|^\s*#{1,6}\s|\*\*",
            text or "",
            flags=re.IGNORECASE | re.MULTILINE,
        )
    )


def _has_structured_artifact(text: str) -> bool:
    return bool(
        re.search(
            r"검토\s*의견은\s*다음과\s*같습니다\.\s*[\[{]|"
            r"['\"](?:paragraphs|limitations|structured_output|action_items)['\"]\s*:",
            text or "",
        )
    )


def _generic_phrase_hits(text: str) -> List[str]:
    return [phrase for phrase in _GENERIC_PHRASES if phrase in (text or "")]


def _repetition_ratio(text: str) -> float:
    sentences = [part.strip() for part in re.split(r"[.!?\n]+", text or "") if len(part.strip()) >= 8]
    if not sentences:
        return 0.0
    counts = Counter(sentences)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / max(len(sentences), 1)


def _normalize_for_alignment(text: str) -> str:
    rendered = text or ""
    for phrase in _COMMON_REPLY_PHRASES:
        rendered = rendered.replace(phrase, " ")
    for term in _STOP_TERMS:
        rendered = rendered.replace(term, " ")
    return re.sub(r"[^가-힣A-Za-z0-9]", "", rendered)


def _char_ngrams(text: str, size: int = 3) -> set[str]:
    normalized = _normalize_for_alignment(text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[index:index + size] for index in range(len(normalized) - size + 1)}


def _reference_alignment(answer: str, reference_answer: str) -> float:
    if not answer or not reference_answer:
        return 0.0
    left = _char_ngrams(answer)
    right = _char_ngrams(reference_answer)
    return len(left & right) / len(left | right) if left | right else 0.0


def _alignment_score(alignment: float) -> float:
    thresholds = (
        (0.30, 10.0),
        (0.22, 9.0),
        (0.16, 8.0),
        (0.11, 7.0),
        (0.08, 6.0),
        (0.055, 5.0),
        (0.035, 4.0),
        (0.02, 3.0),
        (0.0, 2.0),
    )
    if alignment <= 0:
        return 0.0
    for threshold, score in thresholds:
        if alignment >= threshold:
            return score
    return 0.0


def _reference_anchor_coverage(answer: str, reference_answer: str) -> float:
    if not reference_answer:
        return 0.0
    anchors: set[str] = set()
    for match in re.findall(
        r"「[^」]{2,60}」|[가-힣A-Za-z]{2,}(?:법|조례|시행령)\s*제?\d+조|"
        r"\d{4}\s*년|\d{1,2}\s*월|\d{1,2}\s*일|\d+(?:\.\d+)?\s*(?:억|만|천|원|km|㎞|m|㎡|건|회|개|명|%)|"
        r"[가-힣A-Za-z]{2,}(?:과|팀|센터|공단|사업소)",
        reference_answer,
    ):
        cleaned = re.sub(r"\s+", "", match)
        if cleaned:
            anchors.add(cleaned)
    if not anchors:
        return 0.0
    compact_answer = re.sub(r"\s+", "", answer or "")
    matched = sum(anchor in compact_answer for anchor in anchors)
    return matched / len(anchors)


def _semantic_risk_flags(answer: str, reference_answer: str) -> List[str]:
    """Detect decision/authority reversals against the paired real reply."""
    if not answer or not reference_answer:
        return []
    flags: List[str] = []
    reference_has_constraint = bool(_REFERENCE_CONSTRAINT_RE.search(reference_answer))
    answer_has_commitment = bool(_STRONG_COMMITMENT_RE.search(answer))
    if reference_has_constraint and (
        answer_has_commitment or _POSITIVE_DISPOSITION_RE.search(answer)
    ):
        flags.append("disposition_reversal")
    if _PRIVATE_AUTHORITY_RE.search(reference_answer) and (
        _AGENCY_ACTION_RE.search(answer) or answer_has_commitment
    ):
        flags.append("authority_mismatch")
    if answer_has_commitment:
        commitment_terms = {
            term
            for term in (
                "설치", "철거", "제거", "이동", "신설", "건설", "매입",
                "보수", "정비", "폐쇄", "단속", "시정", "개선", "확대",
                "개방", "허가", "지정", "도입", "구축", "예산", "공청회",
            )
            if term in answer
        }
        unsupported = [term for term in commitment_terms if term not in reference_answer]
        if unsupported:
            flags.append("unsupported_commitment")
    if (
        _UNVERIFIED_ASSERTION_RE.search(answer)
        and not _UNVERIFIED_ASSERTION_RE.search(reference_answer)
    ):
        flags.append("unverified_current_fact")
    return flags


def _profile_band_score(value: float, stats: Dict[str, float]) -> float:
    if value <= 0:
        return 0.0
    if stats["p25"] <= value <= stats["p75"]:
        return 10.0
    if stats["p10"] <= value <= stats["p90"]:
        return 8.0
    if stats["p05"] <= value <= stats["p95"]:
        return 6.0
    if value < stats["p05"]:
        return 3.0 if value >= max(120.0, stats["p05"] * 0.5) else 0.0
    return 3.0 if value <= stats["p95"] * 1.5 else 0.0


def _score_q1_naturalness(answer: str, profile: Dict[str, Any]) -> Tuple[float, List[str]]:
    if not answer:
        return 0.0, ["답변이 비어 있음"]
    score = 10.0
    reasons: List[str] = []
    if re.search(r"(?:^|\s)(?:액션\s*아이템|섹션\s*\d+|조치\s*제안)\s*[:：]", answer):
        score -= 2.5
        reasons.append("내부 생성용 라벨이 회신 본문에 노출됨")
    if "\\n" in answer:
        score -= 2.0
        reasons.append("이스케이프 문자열이 실제 줄바꿈으로 정규화되지 않음")
    if "[REDACTED:" in answer:
        score -= 3.0
        reasons.append("잘린 비식별화 토큰이 노출됨")
    if re.search(r"(?:^|\s)\d+[.．)]\s*$", answer):
        score -= 1.5
        reasons.append("의미 없는 번호 조각이 남아 있음")
    if _has_debug_noise(answer):
        score -= 5.0
        reasons.append("검색 메타데이터 또는 Markdown이 노출됨")
    if _has_structured_artifact(answer):
        score -= 4.0
        reasons.append("리스트·딕셔너리 구조 문자열이 본문에 노출됨")
    if "[[출처" in answer or re.search(r"\[출처\s*\d+\]", answer):
        score -= 1.0
        reasons.append("본문에 제거 대상 출처 토큰이 남아 있음")
    generic_hits = _generic_phrase_hits(answer)
    if generic_hits:
        score -= min(4.0, 1.5 * len(generic_hits))
        reasons.append(f"템플릿성 일반 문구 {len(generic_hits)}개 감지")
    if len(answer) < profile["length_chars"]["p05"]:
        score -= 1.5
        reasons.append("실제 회신 본문 하위 5%보다 짧음")
    return _clip_score(score), reasons or ["생성 본문의 문장 품질과 자연스러움이 양호함"]


def _score_q2_source_adequacy(
    row: Dict[str, Any],
    answer: str,
    alignment_score: float,
    semantic_flags: Sequence[str] = (),
) -> Tuple[float, List[str]]:
    strict = float(row.get("citation_match_rate_strict") or 0.0)
    repaired = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
    count = int(row.get("citations_count_repaired") or row.get("citations_count") or 0)
    if count <= 0:
        return 0.0, ["사용 가능한 citations가 없음"]

    specificity = len(_specificity_signals(answer))
    score = strict * 6.5 + min(count, 3) / 3 * 1.0 + min(specificity, 5) / 5 * 1.5
    score += alignment_score * 0.1
    reasons = [
        f"strict_match={strict:.2f}",
        f"repaired_match={repaired:.2f}",
        f"citations={count}",
        f"specificity={specificity}/6",
    ]
    if strict <= 0 and repaired > 0:
        score = min(score + repaired * 2.0, 5.5)
        reasons.append("모델 원출력 근거가 없어 후처리 보완 점수 상한 5.5 적용")
    if semantic_flags:
        score -= 2.0 * len(set(semantic_flags))
        reasons.append(f"reference_semantic_risks={','.join(semantic_flags)}")
    return _clip_score(score), reasons


def _score_q3_citation_coverage(row: Dict[str, Any]) -> Tuple[float, List[str]]:
    repaired_count = int(row.get("citations_count_repaired") or row.get("citations_count") or 0)
    strict_count = int(row.get("citations_count_strict") or 0)
    repaired_rate = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
    if repaired_count <= 0:
        return 0.0, ["citations가 없음"]
    if strict_count > 0:
        score = 5.0 + min(strict_count, 3) / 3 * 2.0 + repaired_rate * 3.0
        return _clip_score(score), [f"strict citations={strict_count}", f"repaired_match={repaired_rate:.2f}"]
    score = min(6.0, 2.0 + min(repaired_count, 3) / 3 * 2.0 + repaired_rate * 2.0)
    return _clip_score(score), ["citations가 후처리로만 확보되어 최고 6점으로 제한됨"]


def _score_q4_citation_accuracy(row: Dict[str, Any]) -> Tuple[float, List[str]]:
    strict_rate = float(row.get("citation_match_rate_strict") or 0.0)
    support_rate = row.get("citation_support_rate_strict")
    repaired_rate = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
    strict_count = int(row.get("citations_count_strict") or 0)
    if strict_count > 0:
        if support_rate is not None:
            support = float(support_rate or 0.0)
            return _clip_score(support * 10.0), [
                f"strict citation_support_rate={support:.2f}"
            ]
        return _clip_score(strict_rate * 7.0), [
            f"legacy identity-only citation_match_rate={strict_rate:.2f}; 7점 상한"
        ]
    if repaired_rate > 0:
        return _clip_score(repaired_rate * 5.0), [
            f"strict citation이 없어 repaired citation_match_rate={repaired_rate:.2f}를 5점 상한으로 반영"
        ]
    return 0.0, ["citation_match_rate=0.00"]


def _score_q5_best_source(
    row: Dict[str, Any],
    alignment_score: float,
    anchor_coverage: float,
    semantic_flags: Sequence[str] = (),
) -> Tuple[float, List[str]]:
    strict_rate = float(row.get("citation_match_rate_strict") or 0.0)
    strict_count = int(row.get("citations_count_strict") or 0)
    if strict_count <= 0:
        repaired = float(row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0)
        return _clip_score(min(4.0, repaired * 3.0 + alignment_score * 0.1)), [
            "strict 출처 선택 정보가 없어 4점 상한 적용"
        ]
    score = strict_rate * 6.0 + min(strict_count, 2) * 0.75
    score += alignment_score * 0.15 + anchor_coverage * 1.0
    score -= 1.5 * len(set(semantic_flags))
    return _clip_score(score), [
        f"strict_match={strict_rate:.2f}",
        f"reference_alignment_score={alignment_score:.1f}",
        f"reference_anchor_coverage={anchor_coverage:.2f}",
        f"reference_semantic_risks={','.join(semantic_flags) or 'none'}",
    ]


def _score_q6_redundancy(answer: str) -> Tuple[float, List[str]]:
    if not answer:
        return 0.0, ["답변이 비어 있음"]
    score = 10.0
    reasons: List[str] = []
    ratio = _repetition_ratio(answer)
    if ratio > 0.30:
        score -= 5.0
        reasons.append(f"반복 문장 비율이 매우 높음({ratio:.2f})")
    elif ratio > 0.15:
        score -= 3.0
        reasons.append(f"반복 문장 비율이 높음({ratio:.2f})")
    elif ratio > 0:
        score -= 1.5
        reasons.append(f"일부 반복 감지({ratio:.2f})")
    if _has_debug_noise(answer):
        score -= 5.0
        reasons.append("디버그/Markdown 노이즈 감지")
    if _has_structured_artifact(answer):
        score -= 4.0
        reasons.append("구조화 데이터 문자열 노출")
    if "\\n" in answer:
        score -= 2.0
        reasons.append("literal 줄바꿈 이스케이프 노출")
    if "[REDACTED:" in answer:
        score -= 3.0
        reasons.append("잘린 비식별화 토큰 노출")
    if re.search(r"(?:^|\s)(?:액션\s*아이템|섹션\s*\d+|조치\s*제안)\s*[:：]", answer):
        score -= 2.0
        reasons.append("내부 생성용 라벨 노출")
    generic_hits = _generic_phrase_hits(answer)
    if generic_hits:
        score -= min(4.0, 1.5 * len(generic_hits))
        reasons.append(f"템플릿성 일반 문구 {len(generic_hits)}개")
    if re.search(r"3\.\s*검토.*?1\.\s*귀하", answer, flags=re.DOTALL):
        score -= 1.5
        reasons.append("본문 안에 번호 체계가 중복됨")
    if "[[출처" in answer or re.search(r"\[출처\s*\d+\]", answer):
        score -= 1.0
        reasons.append("본문에 제거 대상 출처 토큰이 남아 있음")
    return _clip_score(score), reasons or ["반복·템플릿·디버그 노이즈가 없음"]


def _score_q7_conciseness(
    answer: str,
    reference_answer: str,
    profile: Dict[str, Any],
) -> Tuple[float, List[str]]:
    if not answer:
        return 0.0, ["답변이 비어 있음"]
    length_score = _profile_band_score(len(answer), profile["length_chars"])
    sentence_score = _profile_band_score(_sentence_count(answer), profile["sentence_count"])
    reasons = [
        f"length={len(answer)} (reference median={profile['length_chars']['median']})",
        f"sentences={_sentence_count(answer)} (reference median={profile['sentence_count']['median']})",
    ]
    if reference_answer:
        ratio = len(answer) / max(len(reference_answer), 1)
        if 0.70 <= ratio <= 1.40:
            paired_score = 10.0
        elif 0.50 <= ratio <= 2.00:
            paired_score = 8.0
        elif 0.30 <= ratio <= 3.00:
            paired_score = 5.0
        else:
            paired_score = 2.0
        score = 0.45 * length_score + 0.25 * sentence_score + 0.30 * paired_score
        reasons.append(f"paired_length_ratio={ratio:.2f}")
    else:
        score = 0.65 * length_score + 0.35 * sentence_score
    return _clip_score(score), reasons


def _score_q8_efficiency(
    answer: str,
    alignment_score: float,
    anchor_coverage: float,
    has_reference: bool,
    semantic_flags: Sequence[str] = (),
) -> Tuple[float, List[str]]:
    if not answer:
        return 0.0, ["답변이 비어 있음"]
    has_summary = bool(re.search(r"민원\s*내용|질의\s*내용|요청|불편|문제|문의", answer))
    has_review = bool(re.search(r"검토|알려드립니다|확인|판단|불가|가능|소관|책임", answer))
    has_action = bool(_SPECIFICITY_PATTERNS["action"].search(answer))
    has_constraint = bool(_SPECIFICITY_PATTERNS["constraint"].search(answer))
    specificity = len(_specificity_signals(answer))

    score = (
        1.5 * has_summary
        + 2.0 * has_review
        + 1.5 * has_action
        + 1.5 * has_constraint
        + min(specificity, 4) / 4 * 1.5
    )
    if has_reference:
        score += alignment_score * 0.15 + anchor_coverage * 0.5
    else:
        score += min(specificity, 4) / 4 * 2.0
    generic_hits = _generic_phrase_hits(answer)
    score -= min(3.0, len(generic_hits) * 1.0)
    score -= 1.5 * len(set(semantic_flags))
    reasons = [
        f"summary={has_summary}",
        f"review={has_review}",
        f"action={has_action}",
        f"constraint={has_constraint}",
        f"specificity={specificity}/6",
        f"reference_semantic_risks={','.join(semantic_flags) or 'none'}",
    ]
    if has_reference:
        reasons.extend(
            [
                f"reference_alignment_score={alignment_score:.1f}",
                f"reference_anchor_coverage={anchor_coverage:.2f}",
            ]
        )
    return _clip_score(score), reasons


def evaluate_row(
    row: Dict[str, Any],
    case: Dict[str, Any],
    answer_field: str,
    reference_answer: str = "",
    reference_profile: Optional[Dict[str, Any]] = None,
    evaluation_scope: str = DEFAULT_EVALUATION_SCOPE,
) -> Dict[str, Any]:
    profile = reference_profile or build_reference_profile(
        [reference_answer] if reference_answer else ["기준 답변입니다."],
        evaluation_scope=evaluation_scope,
    )
    full_answer = _answer_from_row(row, answer_field)
    answer = (
        extract_generated_body(full_answer)
        if evaluation_scope == "generated_body"
        else full_answer
    )
    reference_body = (
        extract_reference_body(reference_answer)
        if evaluation_scope == "generated_body"
        else reference_answer
    )
    alignment = _reference_alignment(answer, reference_body) if reference_body else 0.0
    alignment_score = _alignment_score(alignment) if reference_answer else 0.0
    anchor_coverage = _reference_anchor_coverage(answer, reference_body) if reference_body else 0.0
    semantic_flags = _semantic_risk_flags(answer, reference_body)

    scores: Dict[str, Tuple[float, List[str]]] = {
        "Q1": _score_q1_naturalness(answer, profile),
        "Q2": _score_q2_source_adequacy(
            row,
            answer,
            alignment_score,
            semantic_flags,
        ),
        "Q3": _score_q3_citation_coverage(row),
        "Q4": _score_q4_citation_accuracy(row),
        "Q5": _score_q5_best_source(
            row,
            alignment_score,
            anchor_coverage,
            semantic_flags,
        ),
        "Q6": _score_q6_redundancy(answer),
        "Q7": _score_q7_conciseness(answer, reference_body, profile),
        "Q8": _score_q8_efficiency(
            answer,
            alignment_score,
            anchor_coverage,
            bool(reference_body),
            semantic_flags,
        ),
    }

    weighted = sum(WEIGHTS[qid] * scores[qid][0] for qid in WEIGHTS)
    caps: List[Tuple[float, str]] = []
    if not answer:
        caps.append((0.0, "empty_answer"))
    if _has_debug_noise(answer):
        caps.append((3.0, "debug_noise"))
    if _has_structured_artifact(answer):
        caps.append((4.0, "structured_artifact"))
    if int(row.get("citations_count_repaired") or row.get("citations_count") or 0) <= 0:
        caps.append((4.0, "no_citations"))
    if int(row.get("citations_count_strict") or 0) <= 0:
        caps.append((6.5, "repaired_only_citations"))
    if len(_generic_phrase_hits(answer)) >= 2:
        caps.append((5.5, "generic_template_overuse"))
    if str(row.get("legal_grounding_status") or "") == "error":
        caps.append((5.0, "legal_grounding_error"))
    if "disposition_reversal" in semantic_flags:
        caps.append((3.5, "disposition_reversal"))
    if "authority_mismatch" in semantic_flags:
        caps.append((4.0, "authority_mismatch"))
    if "unsupported_commitment" in semantic_flags:
        caps.append((5.0, "unsupported_commitment"))
    if "unverified_current_fact" in semantic_flags:
        caps.append((5.5, "unverified_current_fact"))
    if reference_answer and alignment <= 0:
        caps.append((4.5, "zero_reference_alignment"))
    elif reference_answer and alignment < 0.015:
        caps.append((5.0, "very_low_reference_alignment"))
    elif reference_answer and alignment < 0.035:
        caps.append((5.5, "low_reference_alignment"))

    q0 = weighted
    if caps:
        q0 = min(q0, min(cap for cap, _ in caps))
    q0 = _clip_score(q0)

    rubric = {
        "Q0": {
            "score": q0,
            "label": RUBRIC_DESCRIPTIONS["Q0"],
            "reasons": [f"weighted_proxy={weighted:.2f}"]
            + [f"cap={cap:.1f}:{reason}" for cap, reason in caps],
        }
    }
    for qid in (f"Q{index}" for index in range(1, 9)):
        score, reasons = scores[qid]
        rubric[qid] = {
            "score": _clip_score(score),
            "label": RUBRIC_DESCRIPTIONS[qid],
            "reasons": reasons,
        }

    return {
        "case_id": str(row.get("case_id") or ""),
        "model_id": row.get("model_id"),
        "model_name": row.get("model_name"),
        "source": case.get("source"),
        "category": case.get("category") or case.get("consulting_category"),
        "answer_len": len(answer),
        "full_answer_len": len(full_answer),
        "evaluation_scope": evaluation_scope,
        "reference_available": bool(reference_answer),
        "reference_answer_len": len(reference_body),
        "reference_alignment": round(alignment, 4),
        "reference_alignment_score": alignment_score,
        "reference_anchor_coverage": round(anchor_coverage, 4),
        "semantic_risk_flags": semantic_flags,
        "answer_has_source_tokens": bool(
            "[[출처" in answer or re.search(r"\[출처\s*\d+\]", answer)
        ),
        "reply_shell_diagnostics": _reply_shell_diagnostics(full_answer),
        "citation_match_rate_strict": float(row.get("citation_match_rate_strict") or 0.0),
        "citation_match_rate_repaired": float(
            row.get("citation_match_rate_repaired") or row.get("citation_match_rate") or 0.0
        ),
        "rubric": rubric,
    }


def build_report(
    scores: List[Dict[str, Any]],
    reference_profile: Dict[str, Any],
) -> Dict[str, Any]:
    evaluation_scope = (
        scores[0].get("evaluation_scope") if scores else DEFAULT_EVALUATION_SCOPE
    )
    by_q = {
        qid: round(_average(row["rubric"][qid]["score"] for row in scores), 4)
        for qid in RUBRIC_DESCRIPTIONS
    }
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for row in scores:
        categories.setdefault(str(row.get("category") or "unknown"), []).append(row)

    q0_values = [float(row["rubric"]["Q0"]["score"]) for row in scores]
    bins = {
        "0-1.9": sum(value < 2 for value in q0_values),
        "2.0-3.9": sum(2 <= value < 4 for value in q0_values),
        "4.0-5.9": sum(4 <= value < 6 for value in q0_values),
        "6.0-7.9": sum(6 <= value < 8 for value in q0_values),
        "8.0-10.0": sum(value >= 8 for value in q0_values),
    }

    return {
        "method": (
            "llm_rubric_proxy_civil_replies_v3_generated_body"
            if evaluation_scope == "generated_body"
            else "llm_rubric_proxy_civil_replies_v2_full_reply_compat"
        ),
        "note": (
            "Deterministic 0-10 proxy of LLM-Rubric Q0-Q8. "
            "Text-based dimensions evaluate only the generated substantive body; "
            "the fixed reply shell is reported separately. "
            "no learned calibration network is applied."
        ),
        "evaluation_scope": evaluation_scope,
        "score_scale": {"min": SCORE_MIN, "max": SCORE_MAX, "precision": 0.1},
        "weights": WEIGHTS,
        "count": len(scores),
        "paired_reference_count": sum(bool(row.get("reference_available")) for row in scores),
        "reference_profile": reference_profile,
        "average_scores": by_q,
        "q0_distribution": bins,
        "reply_shell_diagnostics": {
            "all_sections_present_rate": round(
                _average(
                    1.0 if row["reply_shell_diagnostics"]["all_sections_present"] else 0.0
                    for row in scores
                ),
                4,
            ),
            "single_closing_rate": round(
                _average(
                    1.0 if row["reply_shell_diagnostics"]["single_closing"] else 0.0
                    for row in scores
                ),
                4,
            ),
        },
        "category_summary": {
            category: {
                "count": len(rows),
                **{
                    qid: round(
                        _average(row["rubric"][qid]["score"] for row in rows),
                        4,
                    )
                    for qid in RUBRIC_DESCRIPTIONS
                },
            }
            for category, rows in sorted(categories.items())
        },
    }


def write_summary_md(report: Dict[str, Any], output_path: Path) -> None:
    profile = report["reference_profile"]
    lines = [
        "# LLM-Rubric Strict Evaluation Summary",
        "",
        f"- method: `{report['method']}`",
        f"- count: {report['count']}",
        f"- paired references: {report['paired_reference_count']}",
        f"- evaluation scope: `{report['evaluation_scope']}`",
        "- scale: 0.0 (lowest) to 10.0 (highest)",
        "- Q0~Q8 text scoring excludes fixed paragraphs 1, 2, and 4 and evaluates the generated paragraph 3 body.",
        "- Q3~Q4 continue to use structured citation fields; reply shell compliance is reported separately.",
        "",
        "## Reference Calibration",
        "",
        f"- source: `{profile.get('source_path')}`",
        f"- valid consultant answers: {profile.get('valid_answer_count')}",
        (
            "- substantive body length chars: "
            f"p25={profile['length_chars']['p25']}, median={profile['length_chars']['median']}, "
            f"p75={profile['length_chars']['p75']}"
        ),
        (
            "- substantive body sentence count: "
            f"p25={profile['sentence_count']['p25']}, median={profile['sentence_count']['median']}, "
            f"p75={profile['sentence_count']['p75']}"
        ),
        "",
        "## Reply Shell Diagnostics",
        "",
        f"- all sections present rate: {report['reply_shell_diagnostics']['all_sections_present_rate']}",
        f"- single closing rate: {report['reply_shell_diagnostics']['single_closing_rate']}",
        "",
        "## Average Scores",
        "",
        "| question | score / 10 | meaning |",
        "| --- | ---: | --- |",
    ]
    for qid, score in report["average_scores"].items():
        lines.append(f"| {qid} | {score} | {RUBRIC_DESCRIPTIONS[qid]} |")

    lines.extend(
        [
            "",
            "## Q0 Distribution",
            "",
            "| range | count |",
            "| --- | ---: |",
        ]
    )
    for label, count in report["q0_distribution"].items():
        lines.append(f"| {label} | {count} |")

    lines.extend(
        [
            "",
            "## Category Summary",
            "",
            "| category | count | Q0 | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 | Q7 | Q8 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for category, row in report["category_summary"].items():
        score_cells = " | ".join(str(row[f"Q{index}"]) for index in range(9))
        lines.append(f"| {category} | {row['count']} | {score_cells} |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate generated civil-affairs replies with a strict 0-10 LLM-Rubric proxy."
    )
    parser.add_argument("--answers", required=True, help="parsed_answers.jsonl path")
    parser.add_argument("--cases", default=None, help="benchmark cases JSON path")
    parser.add_argument("--output-dir", required=True, help="directory for rubric outputs")
    parser.add_argument("--answer-field", default="parsed_answer_repaired")
    parser.add_argument(
        "--evaluation-scope",
        choices=["generated_body", "full_reply"],
        default=DEFAULT_EVALUATION_SCOPE,
        help="generated_body excludes the fixed reply shell; full_reply keeps legacy behavior",
    )
    parser.add_argument(
        "--reference-data",
        default=str(DEFAULT_REFERENCE_PATH.relative_to(PROJECT_ROOT)),
        help="processed JSON containing source_id and consultant_answer",
    )
    args = parser.parse_args()

    answers_path = (PROJECT_ROOT / args.answers).resolve()
    cases_path = (PROJECT_ROOT / args.cases).resolve() if args.cases else None
    reference_path = (PROJECT_ROOT / args.reference_data).resolve()
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _read_cases(cases_path)
    references, reference_profile = _read_reference_answers(
        reference_path,
        evaluation_scope=args.evaluation_scope,
    )
    rows = _read_jsonl(answers_path)
    scores = []
    for row in rows:
        case_id = str(row.get("case_id") or "")
        scores.append(
            evaluate_row(
                row,
                cases.get(case_id, {}),
                args.answer_field,
                reference_answer=references.get(case_id, ""),
                reference_profile=reference_profile,
                evaluation_scope=args.evaluation_scope,
            )
        )
    report = build_report(scores, reference_profile)

    score_path = output_dir / "rubric_scores.jsonl"
    with score_path.open("w", encoding="utf-8") as handle:
        for row in scores:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report_path = output_dir / "rubric_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = output_dir / "rubric_summary.md"
    write_summary_md(report, summary_path)

    print(f"[DONE] scores: {score_path}")
    print(f"[DONE] report: {report_path}")
    print(f"[DONE] summary: {summary_path}")


if __name__ == "__main__":
    main()
