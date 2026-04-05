"""공용 민원 제목 생성 유틸리티."""

from __future__ import annotations

from typing import Any


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

    category_text = str(category or "민원").strip() or "민원"
    if not title_source:
        title_source = f"{category_text} 관련 민원"

    title = " ".join(title_source.split())
    if len(title) <= max_length:
        return title
    return title[:max_length].rstrip() + "..."
