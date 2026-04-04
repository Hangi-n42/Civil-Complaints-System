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
        is_search_clicked = st.button("워크벤치 검색", use_container_width=True)

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


def render_similar_cases_table(rows: list[dict[str, Any]], *, return_html: bool = False) -> str | None:
    """워크벤치(스크린샷)용 유사 민원 테이블 렌더러.

    Expected row keys:
      - case_id, date, similarity, status
    """

    def _status_text(status: str) -> str:
        text = (status or "").strip().upper()
        if not text:
            text = "PENDING"
        return text

    def _esc(value: Any) -> str:
        return str(value or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    body_rows: list[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        body_rows.append(
            (
                "<tr>"
                f"<td><b>{_esc(row.get('case_id'))}</b></td>"
                f"<td>{_esc(row.get('date'))}</td>"
                f"<td>{_esc(row.get('similarity'))}</td>"
                f"<td style='font-weight:800;color:#0f172a;'>{_esc(_status_text(str(row.get('status', 'PENDING'))))}</td>"
                "</tr>"
            )
        )

    table_html = (
        "<table class='wb-table'>"
        "<thead><tr><th>CASE ID</th><th>DATE</th><th>SIMILARITY</th><th>STATUS</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )
    if return_html:
        return table_html
    st.markdown(table_html, unsafe_allow_html=True)
    return None


def render_similar_cases_collapsible(rows: list[dict[str, Any]], *, return_html: bool = False) -> str | None:
    """워크벤치(스크린샷)용 유사 민원 '펼침/접힘' 리스트 렌더러.

    Expected row keys:
      - case_id, date, similarity, status
      - complaint (민원), answer (답변)
    """

    def _esc(value: Any) -> str:
        return str(value or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _status_text(status: str) -> str:
        text = (status or "").strip().upper()
        if not text:
            text = "PENDING"
        return text

    items: list[str] = []
    for idx, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            continue
        case_id = _esc(row.get("case_id"))
        date = _esc(row.get("date"))
        similarity = _esc(row.get("similarity"))
        status = _esc(_status_text(str(row.get("status", "PENDING"))))
        complaint = _esc(row.get("complaint"))
        answer = _esc(row.get("answer"))

        dept_tracks = row.get("department_tracks")
        dept_tracks = dept_tracks if isinstance(dept_tracks, list) else []
        dept_units: list[str] = []
        dept_items: list[str] = []
        for t in dept_tracks:
            if not isinstance(t, dict):
                continue
            unit = str(t.get("admin_unit") or "").strip()
            unit = unit if unit else "미지정"
            if unit not in dept_units:
                dept_units.append(unit)
            unit_answer = _esc(t.get("answer"))
            dept_items.append(
                "<div class='wb-similar-dept-item'>"
                f"<div class='wb-similar-dept-name'>{_esc(unit)}</div>"
                f"<div class='wb-similar-dept-answer'>{unit_answer}</div>"
                "</div>"
            )

        dept_badge = ""
        if dept_units:
            dept_badge = f" | {'/'.join([_esc(u) for u in dept_units[:3]])}{'…' if len(dept_units) > 3 else ''}"

        if dept_items:
            answer_html = (
                "<div class='wb-similar-block'>"
                "<div class='wb-similar-label'>부서별 답변</div>"
                f"<div class='wb-similar-dept-list'>{''.join(dept_items)}</div>"
                "</div>"
            )
        else:
            answer_html = (
                "<div class='wb-similar-block'>"
                "<div class='wb-similar-label'>답변</div>"
                f"<div class='wb-similar-text'>{answer}</div>"
                "</div>"
            )

        items.append(
            "".join(
                [
                    "<details class='wb-similar-item'>",
                    "<summary>",
                    "<div class='wb-similar-summary'>",
                    f"<div class='wb-similar-title'>{idx}. {case_id}</div>",
                    f"<div class='wb-similar-meta'>{date} | {similarity} | {status}{dept_badge}</div>",
                    "</div>",
                    "</summary>",
                    "<div class='wb-similar-body'>",
                    "<div class='wb-similar-block'>",
                    "<div class='wb-similar-label'>민원</div>",
                    f"<div class='wb-similar-text'>{complaint}</div>",
                    "</div>",
                    answer_html,
                    "</div>",
                    "</details>",
                ]
            )
        )

    html = f"<div class='wb-similar-list'>{''.join(items) if items else ''}</div>"
    if return_html:
        return html
    st.markdown(html, unsafe_allow_html=True)
    return None
