"""중복 그룹 대표 답변 초안의 사후 안전 점검."""

from __future__ import annotations

import re


_PII_PATTERNS = [
    ("PII_PHONE", re.compile(r"01[016789]-?\d{3,4}-?\d{4}")),
    ("PII_EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PII_DETAILED_ADDRESS", re.compile(r"\d{1,4}\s*(?:동|호|층)\b")),
]

_PROHIBITED_PATTERNS = [
    ("AUTO_SEND_PROMISE", re.compile(r"자동\s*(?:발송|통지)|일괄\s*발송")),
    ("AUTO_MERGE_PROMISE", re.compile(r"자동\s*병합|일괄\s*처리\s*(?:완료|확정)")),
    ("COMPENSATION_PROMISE", re.compile(r"(?:보상|배상)(?:해\s*드리겠습니다|됩니다|하겠습니다|확정)")),
    ("DEADLINE_CHANGE_PROMISE", re.compile(r"처리기한.*(?:연장|변경).*확정")),
]


def build_reply_safety_warnings(answer: str) -> list[str]:
    """PII 실문자와 자동 처리/권리관계 단정 표현을 경고 코드로 반환한다."""

    warnings: list[str] = []
    text = str(answer or "")
    for code, pattern in _PII_PATTERNS:
        if pattern.search(text):
            warnings.append(code)
    for code, pattern in _PROHIBITED_PATTERNS:
        if pattern.search(text):
            warnings.append(code)
    return warnings
