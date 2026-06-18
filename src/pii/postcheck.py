from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiFinding:
    label: str
    reason: str
    start: int
    end: int


@dataclass(frozen=True)
class PostcheckResult:
    passed: bool
    findings: list[PiiFinding]


_HIGH_RISK_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "주민등록번호",
        "주민등록번호 후보가 마스킹 후에도 남아 있음",
        re.compile(r"(?<!\d)\d{6}\s*-?\s*[1-8]\d{6}(?!\d)"),
    ),
    (
        "전화번호",
        "전화번호 후보가 마스킹 후에도 남아 있음",
        re.compile(r"(?<!\d)(?:01[016789]|02|0[3-6]\d)\s*[-.]?\s*\d{3,4}\s*[-.]?\s*\d{4}(?!\d)"),
    ),
    (
        "이메일",
        "이메일 후보가 마스킹 후에도 남아 있음",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "차량번호",
        "차량번호 후보가 마스킹 후에도 남아 있음",
        re.compile(r"(?<!\d)\d{2,3}\s*(?:[가-힣]|\?)\s*\d{4}(?!\d)"),
    ),
    (
        "상세주소",
        "상세주소 후보가 마스킹 후에도 남아 있음",
        re.compile(
            r"(?:[가-힣]{2,}(?:특별시|광역시|특별자치시|특별자치도|도|시)\s*)?"
            r"(?:[가-힣]{1,}(?:구|군)\s*)?"
            r"(?:[가-힣0-9]{2,}(?:대로|로|길))\s*\d+(?:-\d+)?"
            r"(?:\s*(?:\d{1,4}동|\d{1,4}호|\d{1,4}층|[가-힣0-9]+아파트|[가-힣0-9]+빌라))*"
        ),
    ),
    (
        "상세주소",
        "동호수 상세주소 후보가 마스킹 후에도 남아 있음",
        re.compile(r"(?<!\d)\d{1,4}\s*동\s*\d{1,4}\s*호(?!\d)"),
    ),
)

_SUPPLEMENTAL_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?:[가-힣]{2,}(?:특별시|광역시|특별자치시|특별자치도|도|시)\s*)?"
            r"(?:[가-힣]{1,}(?:구|군)\s*)?"
            r"(?:[가-힣0-9]{2,}(?:대로|로|길))\s*\d+(?:-\d+)?"
            r"(?:\s*(?:\d{1,4}동|\d{1,4}호|\d{1,4}층|[가-힣0-9]+아파트|[가-힣0-9]+빌라))*"
        ),
        "[상세주소]",
    ),
    (
        re.compile(r"(?<!\d)\d{1,4}\s*동\s*\d{1,4}\s*호(?!\d)"),
        "[상세주소]",
    ),
    (
        re.compile(r"(?<!\d)\d{2,3}\s*[가-힣]\s*\d{4}(?!\d)"),
        "[차량번호]",
    ),
)


def find_high_risk_pii(text: str | None) -> list[PiiFinding]:
    source = "" if text is None else str(text)
    findings: list[PiiFinding] = []
    for label, reason, pattern in _HIGH_RISK_PATTERNS:
        for match in pattern.finditer(source):
            findings.append(
                PiiFinding(
                    label=label,
                    reason=reason,
                    start=match.start(),
                    end=match.end(),
                )
            )
    return findings


def postcheck_text(text: str | None) -> PostcheckResult:
    findings = find_high_risk_pii(text)
    return PostcheckResult(passed=not findings, findings=findings)


def redact_address_and_vehicle(text: str | None) -> str:
    masked = "" if text is None else str(text)
    for pattern, replacement in _SUPPLEMENTAL_REDACTIONS:
        masked = pattern.sub(replacement, masked)
    return masked
