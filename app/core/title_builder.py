"""공용 민원 제목 생성 유틸리티."""

from __future__ import annotations

import re
from typing import Any

# 상담 원문 첫 줄의 화자 라벨("고객:")이 제목 앞에 섞여 들어오는 것을 제거.
# 공백·콜론 변형 호환: "고객:", "고객 :", "고객:  ".
_LEADING_SPEAKER_RE = re.compile(r"^\s*고객\s*:\s*")


def _strip_speaker_label(text: str) -> str:
    return _LEADING_SPEAKER_RE.sub("", text, count=1)


def build_case_title(
    *,
    explicit_title: Any = "",
    observation: Any = "",
    request: Any = "",
    chunk_text: Any = "",
    raw_text: Any = "",
    category: Any = "민원",
    max_length: int = 60,
) -> str:
    """민원 목록에 노출할 제목을 일관 규칙으로 생성한다."""
    title_source = str(explicit_title or "").strip()
    if not title_source:
        title_source = str(observation or "").strip()
    if not title_source:
        title_source = str(request or "").strip()
    if not title_source:
        title_source = str(chunk_text or "").strip()
    if not title_source:
        title_source = str(raw_text or "").strip()

    # 화자 라벨("고객:") 제거 후 빈 title 자동 보정.
    title_source = _strip_speaker_label(title_source).strip()
    category_text = str(category or "민원").strip() or "민원"
    if not title_source:
        title_source = f"{category_text} 관련 민원"

    title = " ".join(title_source.split())
    if len(title) <= max_length:
        return title
    return title[:max_length].rstrip() + "..."
