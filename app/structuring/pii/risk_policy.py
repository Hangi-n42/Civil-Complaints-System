from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PiiStatus(str, Enum):
    PASSED = "PASSED"
    REVIEW = "REVIEW"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class PiiPipelineDecision:
    status: PiiStatus
    sanitized_text: str | None
    needs_review: bool
    reasons: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    engine_summary: dict[str, Any] = field(default_factory=dict)


_SCHOOL_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}(?:초등학교|중학교|고등학교|초|중|고)")
_GRADE_CLASS_RE = re.compile(r"(?:[1-6]\s*학년|[1-9]\s*반|[1-6]-[1-9])")
_NAME_HINT_RE = re.compile(r"(?:이름|학생|아동|자녀|우리\s*아이)\s*[:：]?\s*[가-힣]{2,4}")
_NAME_SCHOOL_RE = re.compile(r"[가-힣]{2,4}\s+[가-힣A-Za-z0-9]{2,}(?:초등학교|중학교|고등학교)")


def detect_review_risks(text: str | None) -> list[str]:
    source = "" if text is None else str(text)
    if (
        _SCHOOL_RE.search(source)
        and _GRADE_CLASS_RE.search(source)
        and (_NAME_HINT_RE.search(source) or _NAME_SCHOOL_RE.search(source))
    ):
        return ["NAME_SCHOOL_GRADE_CLASS_COMBINATION"]
    return []


def finding_to_dict(label: str, reason: str, start: int, end: int) -> dict[str, Any]:
    return {
        "label": label,
        "reason": reason,
        "start": int(start),
        "end": int(end),
    }


def passed(text: str, *, engine_summary: dict[str, Any] | None = None) -> PiiPipelineDecision:
    return PiiPipelineDecision(
        status=PiiStatus.PASSED,
        sanitized_text=text,
        needs_review=False,
        engine_summary=engine_summary or {},
    )


def review(reasons: list[str]) -> PiiPipelineDecision:
    return PiiPipelineDecision(
        status=PiiStatus.REVIEW,
        sanitized_text=None,
        needs_review=True,
        reasons=reasons,
    )


def quarantined(
    reasons: list[str],
    *,
    findings: list[dict[str, Any]] | None = None,
    engine_summary: dict[str, Any] | None = None,
) -> PiiPipelineDecision:
    return PiiPipelineDecision(
        status=PiiStatus.QUARANTINED,
        sanitized_text=None,
        needs_review=True,
        reasons=reasons,
        findings=findings or [],
        engine_summary=engine_summary or {},
    )
