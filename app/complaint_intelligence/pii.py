"""Complaint Intelligence Layer의 최소 PII 마스킹."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiMaskResult:
    """마스킹된 텍스트와 감지된 PII 라벨."""

    text: str
    detected_labels: tuple[str, ...]


_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:01[016789]|02|0[3-6][1-5])[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")),
    ("RRN", re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")),
    ("ACCOUNT", re.compile(r"\b\d{2,6}[-\s]\d{2,6}[-\s]\d{2,8}\b")),
    ("VEHICLE", re.compile(r"\b\d{2,3}\s?[가-힣]\s?\d{4}\b")),
    ("ADDRESS", re.compile(r"([가-힣A-Za-z0-9]+(?:로|길)\s?\d+(?:-\d+)?|\d{1,5}\s?번지)")),
    ("ADDRESS_DETAIL", re.compile(r"(?<!\d)\d{1,4}\s?동\s?\d{1,4}\s?호(?!\d)|(?<!\d)\d{1,4}\s?호(?!\d)")),
    # 이름은 오탐 가능성이 높아 대표 성씨와 짧은 존칭 패턴으로만 제한한다.
    ("NAME", re.compile(r"(?<![가-힣])([김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남노하곽성차주우구민류나진지엄채원천방공현함변여추도소석선마길위연명기반탁제모구어은][가-힣]{1,2})(?:\s?(?:님|씨))")),
)


def mask_pii(text: str | None) -> PiiMaskResult:
    """raw 텍스트를 API/로그/임베딩에 넘기기 전 최소 마스킹한다."""

    value = "" if text is None else str(text)
    labels: list[str] = []
    masked = value
    for label, pattern in _PII_PATTERNS:
        if pattern.search(masked):
            labels.append(label)
            masked = pattern.sub(f"[REDACTED:{label}]", masked)
    return PiiMaskResult(text=masked, detected_labels=tuple(dict.fromkeys(labels)))
