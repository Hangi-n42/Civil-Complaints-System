"""request_segments analyzer runtime selector.

규칙 기반 analyzer를 기본값으로 유지하되, 설정이 명시적으로 켜진 경우에만
LLM hybrid wrapper를 호출한다. 외부 API 계약은 바꾸지 않고 호출부의 진입점만
한 곳으로 모으기 위한 얇은 선택 계층이다.
"""

from __future__ import annotations

from app.core.config import settings
from app.retrieval.analyzers.complexity_analyzer import build_analyzer_output


def build_request_segment_analysis(
    text: str,
    topic_type: str = "general",
    *,
    title: str | None = None,
    question: str | None = None,
) -> dict:
    """설정에 따라 rule-only 또는 LLM hybrid request_segments 분석을 실행한다."""
    mode = str(settings.REQUEST_SEGMENT_LLM_MODE or "off").strip().lower()
    if mode not in {"shadow", "assist"}:
        return build_analyzer_output(text=text, topic_type=topic_type, title=title, question=question)

    from app.retrieval.analyzers.request_segment_hybrid import build_analyzer_output_hybrid

    return build_analyzer_output_hybrid(
        text=text,
        topic_type=topic_type,
        title=title,
        question=question,
    )
