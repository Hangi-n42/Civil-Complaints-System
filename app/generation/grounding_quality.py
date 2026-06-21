"""Shared grounding quality guards for generation and benchmark paths."""

from __future__ import annotations

import re
from statistics import fmean
from typing import Any


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|\n+")

_STOPWORDS = {
    "민원",
    "요청",
    "사항",
    "내용",
    "관련",
    "검토",
    "조치",
    "확인",
    "안내",
    "처리",
    "가능",
    "필요",
    "경우",
    "대한",
    "귀하",
    "해당",
    "담당",
    "부서",
    "결과",
    "다음",
    "같이",
    "답변",
    "드립니다",
}

_QUERY_SIGNAL_KEYS = (
    "core_objects",
    "facilities",
    "locations",
    "actions",
    "issues",
    "hazards",
    "organizations",
)

_COMMITMENT_RE = re.compile(
    r"(설치|철거|제거|보수|개방|이동|신설|건설|매입|예산\s*확보|단속|과태료|고발|폐쇄|"
    r"운영|배치|지정|교체|정비|방역|수리).{0,24}"
    r"(하겠습니다|하였습|했습니다|완료|예정|확정|추진하겠습니다|실시하겠습니다|계획입니다)"
)
_CONFIRMED_FACT_RE = re.compile(
    r"(확인하였습니다|확인됐습니다|보고되었습니다|이미\s*예정|완료되었습니다|조치되었습니다)"
)
_SAFE_CUE_RE = re.compile(
    r"(검토|가능\s*여부|현장|소관|권한|관련\s*기준|확인\s*후|필요|협의|판단|안내|예정인지)"
)


def meaningful_terms(text: Any) -> set[str]:
    """Return compact Korean/ASCII tokens useful for overlap diagnostics."""

    terms: set[str] = set()
    for match in _TOKEN_RE.finditer(str(text or "")):
        token = match.group(0).strip().lower()
        if len(token) < 2 or token.isdigit() or token in _STOPWORDS:
            continue
        terms.add(token)
    return terms


def context_text(item: dict[str, Any]) -> str:
    parts = []
    for key in (
        "snippet",
        "content",
        "text",
        "consultant_answer",
        "summary_request",
        "summary_answer",
        "title",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _query_terms(
    *,
    query: str,
    request_segments: list[str] | None = None,
    query_signals: dict[str, Any] | None = None,
) -> set[str]:
    terms = meaningful_terms(query)
    for segment in request_segments or []:
        terms.update(meaningful_terms(segment))
    signals = query_signals if isinstance(query_signals, dict) else {}
    for key in _QUERY_SIGNAL_KEYS:
        value = signals.get(key)
        if isinstance(value, list):
            for item in value:
                terms.update(meaningful_terms(item))
        elif value:
            terms.update(meaningful_terms(value))
    return terms


def semantic_context_score(
    context_item: dict[str, Any],
    *,
    query: str,
    request_segments: list[str] | None = None,
    query_signals: dict[str, Any] | None = None,
) -> float:
    """Cheap 0..1 lexical-semantic match score for retrieval guardrails."""

    q_terms = _query_terms(
        query=query,
        request_segments=request_segments,
        query_signals=query_signals,
    )
    if not q_terms:
        return 0.0

    c_terms = meaningful_terms(context_text(context_item))
    if not c_terms:
        return 0.0

    hits = q_terms & c_terms
    base = len(hits) / max(1, min(len(q_terms), 18))
    segment_bonus = 0.0
    for segment in request_segments or []:
        segment_terms = meaningful_terms(segment)
        if segment_terms and (segment_terms & c_terms):
            segment_bonus += 0.04

    return round(min(1.0, base + min(segment_bonus, 0.16)), 4)


def rerank_contexts_by_semantic_match(
    contexts: list[dict[str, Any]],
    *,
    query: str,
    request_segments: list[str] | None = None,
    query_signals: dict[str, Any] | None = None,
    min_score: float = 0.04,
    keep_min: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Annotate/rerank contexts and drop clearly off-topic tail items."""

    annotated: list[dict[str, Any]] = []
    for index, item in enumerate(contexts or []):
        if not isinstance(item, dict):
            continue
        score = semantic_context_score(
            item,
            query=query,
            request_segments=request_segments,
            query_signals=query_signals,
        )
        enriched = dict(item)
        enriched["semantic_match_score"] = score
        enriched["_semantic_original_rank"] = index
        annotated.append(enriched)

    annotated.sort(
        key=lambda row: (
            float(row.get("semantic_match_score", 0.0)),
            float(row.get("score", row.get("relevance_score", 0.0)) or 0.0),
        ),
        reverse=True,
    )

    filtered = [
        item
        for item in annotated
        if float(item.get("semantic_match_score", 0.0)) >= float(min_score)
    ]
    if len(filtered) < keep_min:
        filtered = annotated[:keep_min]

    scores = [float(item.get("semantic_match_score", 0.0)) for item in annotated]
    diagnostics = {
        "applied": True,
        "input_count": len(contexts or []),
        "output_count": len(filtered),
        "min_score": round(min(scores), 4) if scores else 0.0,
        "max_score": round(max(scores), 4) if scores else 0.0,
        "avg_score": round(fmean(scores), 4) if scores else 0.0,
        "threshold": float(min_score),
    }
    for item in filtered:
        item.pop("_semantic_original_rank", None)
    return filtered, diagnostics


def detect_unsupported_commitments(answer: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for sentence in _SENTENCE_SPLIT_RE.split(str(answer or "")):
        text = sentence.strip()
        if not text:
            continue
        risky = _COMMITMENT_RE.search(text) or _CONFIRMED_FACT_RE.search(text)
        if risky and not _SAFE_CUE_RE.search(text):
            flags.append({"code": "unsupported_commitment", "text": text[:220]})
    return flags


def sanitize_unsupported_commitments(answer: str) -> str:
    """Soften unsupported administrative promises while preserving reply shape."""

    rendered = str(answer or "").strip()
    if not rendered:
        return rendered

    pieces: list[str] = []
    changed = False
    for sentence in _SENTENCE_SPLIT_RE.split(rendered):
        text = sentence.strip()
        if not text:
            continue
        risky = _COMMITMENT_RE.search(text) or _CONFIRMED_FACT_RE.search(text)
        if risky and not _SAFE_CUE_RE.search(text):
            changed = True
            if _CONFIRMED_FACT_RE.search(text):
                pieces.append("해당 사항은 현장 확인 및 소관 부서 검토가 필요한 사항입니다.")
            else:
                pieces.append("해당 요청은 현장 여건, 소관 권한 및 관련 기준을 확인한 뒤 처리 가능 여부를 검토하겠습니다.")
            continue
        pieces.append(text)

    return " ".join(pieces).strip() if changed else rendered


def citation_semantic_support_rate(
    *,
    answer: str,
    citations: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
) -> float:
    if not citations or not contexts:
        return 0.0

    answer_terms = meaningful_terms(answer)
    if not answer_terms:
        return 0.0

    context_by_chunk = {
        str(item.get("chunk_id") or ""): item for item in contexts if isinstance(item, dict)
    }
    scores: list[float] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        cited_text = str(citation.get("snippet") or "")
        chunk_id = str(citation.get("chunk_id") or "")
        if chunk_id in context_by_chunk:
            cited_text += "\n" + context_text(context_by_chunk[chunk_id])
        cited_terms = meaningful_terms(cited_text)
        if not cited_terms:
            scores.append(0.0)
            continue
        overlap = answer_terms & cited_terms
        scores.append(min(1.0, len(overlap) / max(1, min(len(answer_terms), 25))))

    return round(fmean(scores), 4) if scores else 0.0


def segment_coverage_rate(answer: str, request_segments: list[str] | None) -> float:
    segments = [str(item).strip() for item in request_segments or [] if str(item).strip()]
    if not segments:
        return 1.0

    answer_terms = meaningful_terms(answer)
    if not answer_terms:
        return 0.0

    covered = 0
    for segment in segments:
        terms = meaningful_terms(segment)
        if not terms or terms & answer_terms:
            covered += 1
    return round(covered / max(1, len(segments)), 4)


def build_generation_quality_signals(
    *,
    answer: str,
    citations: list[dict[str, Any]],
    contexts: list[dict[str, Any]],
    request_segments: list[str] | None = None,
) -> dict[str, Any]:
    unsupported = detect_unsupported_commitments(answer)
    citation_support = citation_semantic_support_rate(
        answer=answer,
        citations=citations,
        contexts=contexts,
    )
    segment_coverage = segment_coverage_rate(answer, request_segments)
    return {
        "unsupported_commitment_count": len(unsupported),
        "unsupported_commitments": unsupported,
        "citation_semantic_support_rate": citation_support,
        "segment_coverage_rate": segment_coverage,
        "hallucination_flag": bool(unsupported) or citation_support < 0.08,
    }
