from __future__ import annotations

from typing import Any, Dict, Tuple

import html
import streamlit as st

from app.core.title_builder import build_case_title

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
    *,
    key_prefix: str = "wb",
    button_label: str = "워크벤치 검색",
) -> Tuple[str, str, str, bool]:
    """Render workbench search filter UI.

    Returns:
        (query, region, category, is_search_clicked)
    """

    st.markdown("<div class='workbench-toolbar-title'>워크벤치 검색 필터</div>", unsafe_allow_html=True)

    prefix = (key_prefix or "wb").strip() or "wb"

    cols = st.columns([2.2, 1, 1, 1.2])
    with cols[0]:
        st.markdown("<div class='queue-filter-label'>검색어</div>", unsafe_allow_html=True)
        query = st.text_input(
            "워크벤치 검색어",
            value=default_query or "",
            key=f"{prefix}_query",
            label_visibility="collapsed",
        )
    with cols[1]:
        st.markdown("<div class='queue-filter-label'>지역</div>", unsafe_allow_html=True)
        region = st.selectbox(
            "지역",
            region_options,
            index=_safe_index(region_options, default_region, default=0),
            key=f"{prefix}_region",
            label_visibility="collapsed",
        )
    with cols[2]:
        st.markdown("<div class='queue-filter-label'>카테고리</div>", unsafe_allow_html=True)
        category = st.selectbox(
            "카테고리",
            category_options,
            index=_safe_index(category_options, default_category, default=0),
            key=f"{prefix}_category",
            label_visibility="collapsed",
        )
    with cols[3]:
        st.markdown("<div class='queue-filter-label'>실행</div>", unsafe_allow_html=True)
        is_search_clicked = st.button(button_label, use_container_width=True, key=f"{prefix}_search_btn")

    return query, region, category, is_search_clicked


def render_search_result_card(idx: int, item: Dict[str, Any]) -> None:
    """Render a single search result as a bordered card."""

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

    raw_title = str(item.get("title") or "").strip()
    title = raw_title
    if not title:
        title = build_case_title(
            explicit_title=item.get("title"),
            observation=summary_observation,
            request=summary_request,
            chunk_text=snippet,
            category=category,
        )

    chunk_id = item.get("chunk_id")

    with st.container(border=True):
        st.markdown(
            f"**{title}**  \n"
            f"유사도: {similarity:.0%} | {case_id} | 순위: {rank_int}"
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
                    f"<div class='wb-similar-title'>유사민원 {idx}</div>",
                    f"<div class='wb-similar-meta'>{case_id} | {date} | {similarity} | {status}{dept_badge}</div>",
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


def render_standard_status_banner(
    *,
    state: str | None,
    result_count: int | None = None,
    error_message: str | None = None,
    empty_message: str = "조건에 맞는 결과가 없습니다. 검색어나 필터를 변경해 보세요.",
    idle_message: str = "검색 조건을 입력하고 실행하세요.",
    loading_message: str = "요청을 처리 중입니다...",
    success_message: str | None = None,
    mock_message: str = "Mock 모드(UI_FORCE_MOCK)로 샘플 데이터를 표시합니다.",
) -> None:
    """FE 공통 상태 배너(success/loading/error/empty/idle)를 고정 메시지로 렌더링한다."""

    normalized_state = (state or "").strip().lower()

    if normalized_state in ("loading",):
        st.info(loading_message)
        return

    if normalized_state in ("mock", "mock_mode"):
        st.info(mock_message)
        return

    if normalized_state in ("error", "error_fallback"):
        msg = (error_message or "알 수 없는 오류").strip()
        st.error(f"오류가 발생했습니다: {msg}")
        return

    if normalized_state in ("empty",):
        st.info(empty_message)
        return

    if normalized_state in ("success",):
        if success_message:
            st.success(success_message)
        else:
            cnt = "-" if result_count is None else str(int(result_count))
            st.success(f"총 {cnt}건의 결과를 표시합니다.")
        return

    st.info(idle_message)


def render_citations_block(
    citations: list[dict[str, Any]] | None,
    *,
    title: str = "근거(citations)",
    empty_text: str = "표시할 근거가 없습니다.",
    expanded: bool = True,
) -> None:
    """QA citations를 안정적으로 표시한다."""

    citations = citations if isinstance(citations, list) else []
    header = f"{title} ({len(citations)}개)"

    with st.expander(header, expanded=expanded):
        if not citations:
            st.caption(empty_text)
            return

        for cidx, citation in enumerate(citations, start=1):
            if not isinstance(citation, dict):
                continue

            ref_id = citation.get("ref_id", cidx)
            case_id = citation.get("case_id") or "-"
            chunk_id = citation.get("chunk_id") or "-"
            snippet = citation.get("snippet") or "-"
            source = citation.get("source")
            rel = citation.get("relevance_score")

            tail: list[str] = []
            if source:
                tail.append(str(source))
            if rel is not None:
                try:
                    tail.append(f"score={float(rel):.2f}")
                except (TypeError, ValueError):
                    pass
            tail_text = f" ({' | '.join(tail)})" if tail else ""

            st.markdown(
                "\n".join(
                    [
                        f"• **[출처 {html.escape(str(ref_id))}]** {html.escape(str(case_id))} | {html.escape(str(chunk_id))}{html.escape(tail_text)}",
                        f"  - {html.escape(str(snippet))}",
                    ]
                )
            )


def render_limitations_block(
    limitations: Any,
    *,
    title: str = "제한사항(limitations)",
    empty_text: str = "표시할 제한사항이 없습니다.",
    expanded: bool = True,
) -> None:
    """QA limitations를 안정적으로 표시한다."""

    text = ""
    if isinstance(limitations, str):
        text = limitations.strip()
    elif isinstance(limitations, list):
        parts = [str(x).strip() for x in limitations if str(x).strip()]
        text = "\n".join([f"- {p}" for p in parts])
    elif limitations is not None:
        text = str(limitations).strip()

    with st.expander(title, expanded=expanded):
        if not text:
            st.caption(empty_text)
            return
        st.markdown(text)

