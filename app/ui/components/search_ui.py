from __future__ import annotations

from typing import Any, Dict, Tuple

import streamlit as st


def _safe_index(options: list[str], value: str, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def render_search_filter(
    default_query: str,
    default_region: str,
    default_category: str,
    region_options: list[str],
    category_options: list[str],
) -> Tuple[str, str, str, bool]:
    """Render workbench search filter UI.

    Returns:
        (query, region, category, is_search_clicked)
    """

    st.markdown("<div class='workbench-toolbar-title'>워크벤치 검색 필터</div>", unsafe_allow_html=True)

    cols = st.columns([2.2, 1, 1, 1.2])
    with cols[0]:
        st.markdown("<div class='queue-filter-label'>검색어</div>", unsafe_allow_html=True)
        query = st.text_input(
            "워크벤치 검색어",
            value=default_query or "",
            key="wb_query",
            label_visibility="collapsed",
        )
    with cols[1]:
        st.markdown("<div class='queue-filter-label'>지역</div>", unsafe_allow_html=True)
        region = st.selectbox(
            "지역",
            region_options,
            index=_safe_index(region_options, default_region, default=0),
            key="wb_region",
            label_visibility="collapsed",
        )
    with cols[2]:
        st.markdown("<div class='queue-filter-label'>카테고리</div>", unsafe_allow_html=True)
        category = st.selectbox(
            "카테고리",
            category_options,
            index=_safe_index(category_options, default_category, default=0),
            key="wb_category",
            label_visibility="collapsed",
        )
    with cols[3]:
        st.markdown("<div class='queue-filter-label'>실행</div>", unsafe_allow_html=True)
        is_search_clicked = st.button("🔍 워크벤치 검색", use_container_width=True)

    return query, region, category, is_search_clicked


def render_search_result_card(idx: int, item: Dict[str, Any]) -> None:
    """Render a single search result as a bordered card."""

    title = item.get("title", "-")
    similarity = float(item.get("score", item.get("similarity_score", 0.0)) or 0.0)
    rank = item.get("rank")
    try:
        rank_int = int(rank) if rank is not None else idx
    except (TypeError, ValueError):
        rank_int = idx
    case_id = item.get("case_id", "-")
    snippet = item.get("snippet", "")

    created_at = item.get("created_at") or (item.get("metadata", {}) or {}).get("created_at")
    category = item.get("category") or (item.get("metadata", {}) or {}).get("category")
    region = item.get("region") or (item.get("metadata", {}) or {}).get("region")
    entity_labels = item.get("entity_labels") or (item.get("metadata", {}) or {}).get("entity_labels") or []
    entity_labels = entity_labels if isinstance(entity_labels, list) else []

    summary = item.get("summary") if isinstance(item.get("summary"), dict) else None
    summary_observation = (summary or {}).get("observation") if summary else None
    summary_request = (summary or {}).get("request") if summary else None

    chunk_id = item.get("chunk_id")

    with st.container(border=True):
        st.markdown(
            f"**{rank_int}. {title}**  \n"
            f"유사도: {similarity:.0%} | {case_id}"
        )

        meta_parts: list[str] = []
        if created_at:
            meta_parts.append(f"생성: {created_at}")
        if category and category != "-":
            meta_parts.append(f"카테고리: {category}")
        if region and region != "-":
            meta_parts.append(f"지역: {region}")
        if chunk_id:
            meta_parts.append(f"청크: {chunk_id}")
        if meta_parts:
            st.caption(" | ".join(meta_parts))

        if entity_labels:
            pills = " ".join([f"<span class='workbench-entity-pill'>{label}</span>" for label in entity_labels[:6]])
            st.markdown(pills, unsafe_allow_html=True)

        if summary_observation:
            st.caption(f"요약(관찰): {summary_observation}")
        if summary_request:
            st.caption(f"요약(요청): {summary_request}")

        if snippet:
            st.caption(snippet)
