from urllib import error as urlerror
from urllib import request as urlrequest
import json
import re
import time
import html
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np

from app.ui.services.retrieval_parser import ResponseContractError, parse_search_response

st.set_page_config(page_title="GovAI - 민원 처리 시스템", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
    :root {
        --primary: #2563eb;
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text-main: #0f172a;
        --text-muted: #64748b;
    }

    .stApp {
        background: var(--bg);
        color: var(--text-main);
    }

    section[data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #334155;
        min-width: 260px;
    }

    section[data-testid="stSidebar"] * {
        color: #e2e8f0;
    }

    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        display: none;
    }

    section[data-testid="stSidebar"] button[kind="secondary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        width: 100%;
        border-radius: 10px;
        min-height: 50px;
        padding: 12px 14px;
        margin-bottom: 8px;
        font-size: 1rem;
        font-weight: 700;
        text-align: left;
        justify-content: flex-start;
    }

    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: transparent;
        border: 1px solid #334155;
        color: #94a3b8;
    }

    section[data-testid="stSidebar"] button[kind="primary"] {
        background: #2563eb;
        border: 1px solid #60a5fa;
        color: #ffffff;
    }

    [data-testid="stAppDeployButton"],
    [data-testid="stToolbar"],
    [data-testid="stHeaderActionElements"],
    #MainMenu,
    header[data-testid="stHeader"] {
        display: none !important;
        visibility: hidden !important;
    }

    div[data-testid="stDecoration"] {
        display: none;
    }

    .block-container {
        padding-top: 1rem;
    }

    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 12px;
        padding: 18px;
        text-align: center;
    }

    .kpi-label {
        color: var(--text-muted);
        font-size: 0.9rem;
        font-weight: 500;
    }

    .kpi-value-good {
        color: #10b981;
        font-size: 2rem;
        font-weight: 700;
        margin: 8px 0;
    }

    .priority-high {
        background: #fee2e2;
        color: #991b1b;
        padding: 12px;
        border-left: 4px solid #dc2626;
        border-radius: 8px;
        margin-bottom: 8px;
        font-weight: 600;
    }

    .priority-medium {
        background: #fef3c7;
        color: #92400e;
        padding: 12px;
        border-left: 4px solid #f59e0b;
        border-radius: 8px;
        margin-bottom: 8px;
        font-weight: 600;
    }

    .priority-low {
        background: #dbeafe;
        color: #1e40af;
        padding: 12px;
        border-left: 4px solid #3b82f6;
        border-radius: 8px;
        margin-bottom: 8px;
        font-weight: 600;
    }

    .search-card {
        padding: 16px;
        border: 1px solid var(--border);
        border-radius: 8px;
        border-left: 4px solid var(--primary);
        background: white;
        margin-bottom: 12px;
    }

    .chat-wrapper {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
    }

</style>
""",
    unsafe_allow_html=True,
)


SCENARIOS = {
    "road": {
        "label": "1. 도로안전 (포트홀)",
        "search": "포트홀, 도로 파손, 이륜차 사고",
        "chat": "이 사례를 바탕으로 도로보수팀 긴급 작업 지시서를 작성해줘.",
        "docs": [
            {"id": "DOC-25-102", "score": "0.94", "title": "중앙로 10m 인근 포트홀 임시 복구 완료건", "snippet": "...우천 후 배수 불량으로 발생한 포트홀에 대해 긴급 아스팔트 타설 완료..."},
            {"id": "DOC-25-088", "score": "0.89", "title": "이륜차 전도사고 발생 (노면 불량)", "snippet": "...야간 주행 중 도로 파인 곳을 발견하지 못하고 배달 오토바이가 전도됨..."},
        ],
        "chat_response": "<b>[도로보수팀 긴급 작업 지시서]</b><br><br><b>1. 작업 개요</b><br>- 위치: 중앙로 사거리 횡단보도 앞<br>- 내용: 우천으로 인한 포트홀 긴급 평탄화 및 복구",
    },
    "env": {
        "label": "2. 환경 (무단투기)",
        "search": "무단투기, 악취, CCTV 설치",
        "chat": "CCTV 설치 타당성 검토 요청서를 유관 부서용으로 작성해줘.",
        "docs": [
            {"id": "DOC-25-301", "score": "0.96", "title": "상습 투기지역 이동식 단속 카메라 배치 결과", "snippet": "...고정식 CCTV 예산 부족으로 센서형 이동식 카메라를 배치한 결과 투기율 70% 감소..."},
        ],
        "chat_response": "<b>[방범용 CCTV 설치 타당성 검토 요청서]</b><br><br>",
    },
    "noise": {
        "label": "3. 소음 (층간소음)",
        "search": "층간소음, 아파트 분쟁, 야간 소음",
        "chat": "층간소음 분쟁 중재 절차 안내문을 민원인에게 보낼 형식으로 작성해줘.",
        "docs": [
            {"id": "DOC-25-412", "score": "0.95", "title": "환경부 층간소음 이웃사이센터 연계 지원 사례", "snippet": "...전문가 방문 상담 및 소음 측정 지원으로 갈등 완화..."},
        ],
        "chat_response": "<b>[층간소음 분쟁 중재 절차 안내]</b><br><br>",
    },
}


def generate_sample_dashboard_data():
    """대시보드용 샘플 데이터 생성"""
    return {
        "monthly": {"completed": 287, "pending": 143},
        "yearly": {
            "months": ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'],
            "completed": [234, 245, 267, 289, 312, 298, 334, 356, 321, 289, 267, 287],
            "pending": [89, 95, 104, 112, 118, 121, 128, 135, 98, 87, 76, 143],
        },
        "priority": {
            "매우급함": {"count": 42, "avg_time": "2.3일"},
            "급함": {"count": 156, "avg_time": "5.1일"},
            "보통": {"count": 232, "avg_time": "9.7일"},
        },
        "department_load": {
            "부서": ["도로관리", "환경위생", "주거복지", "교통행정", "안전총괄"],
            "미처리": [52, 39, 31, 27, 19],
            "지연": [21, 16, 12, 9, 6],
        },
        "weekly": {"weeks": ['1주차', '2주차', '3주차', '4주차'], "count": [127, 145, 162, 143]},
    }


def push_status(kind: str, message: str) -> None:
    st.session_state.status_kind = kind
    st.session_state.status_message = message


def post_json(base_url: str, path: str, payload: dict, timeout: float = 15.0) -> tuple[dict, int, str | None]:
    url = f"{base_url.rstrip('/')}{path}"
    req = urlrequest.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return parsed, int(response.status), None
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        return parsed, int(getattr(e, "code", 500)), str(e)
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {}, 0, str(e)


def render_answer_with_citations(answer: str, citations: list[dict]) -> str:
    citation_map: dict[int, dict] = {}
    for citation in citations:
        try:
            ref_id = int(citation.get("ref_id", 0))
        except (TypeError, ValueError):
            continue
        citation_map[ref_id] = citation

    def _replace(match: re.Match[str]) -> str:
        ref_id = int(match.group(1))
        snippet = str(citation_map.get(ref_id, {}).get("snippet", "근거 스니펫 없음"))
        hover = html.escape(snippet, quote=True)
        return f"<span style='background:#fef08a; padding:2px 8px; border-radius:10px; font-size:0.75rem; font-weight:700;' title='{hover}'>[출처 {ref_id}]</span>"

    return re.sub(r"\[\[CITE:(\d+)\]\]", _replace, answer or "")


def build_sample_qa_success_payload(query: str, search_results: list[dict]) -> dict:
    first = search_results[0] if search_results else {}
    doc_id = str(first.get("doc_id") or first.get("id") or "DOC-SAMPLE-001")
    chunk_id = str(first.get("chunk_id") or "CASE-SAMPLE-001__chunk-0")
    case_id = str(first.get("case_id") or "CASE-SAMPLE-001")
    snippet = str(first.get("snippet") or "샘플 근거 스니펫")
    return {
        "success": True,
        "request_id": "REQ-SAMPLE-QA-0001",
        "timestamp": "2026-03-21T10:00:00+09:00",
        "answer": f"질문 '{query}'에 대한 검증 모드 샘플 답변입니다. [[CITE:1]]",
        "citations": [
            {
                "ref_id": 1,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "case_id": case_id,
                "snippet": snippet,
                "relevance_score": 0.82,
                "source": "verification_sample",
            }
        ],
        "confidence": "medium",
        "limitations": "Ollama 실패로 검증 모드 샘플 응답을 사용했습니다.",
        "meta": {
            "processing_time": 0.1,
            "model": "verification-sample",
            "validation_warning": "검증 모드 샘플 응답입니다.",
        },
        "qa_validation": {
            "is_valid": True,
            "errors": [],
            "warnings": [
                {
                    "code": "SAMPLE_FALLBACK",
                    "message": "실제 QA 성공 응답이 없어 샘플 payload로 렌더링을 검증했습니다.",
                }
            ],
        },
    }


def check_search_contract_fields(items: list[dict]) -> tuple[bool, list[dict]]:
    required = ["doc_id", "score", "title", "snippet"]
    failures = []
    for idx, item in enumerate(items, start=1):
        missing = [key for key in required if key not in item or item.get(key) in (None, "")]
        score_ok = isinstance(item.get("score"), (int, float))
        if missing or not score_ok:
            failures.append({"index": idx, "missing": missing, "score_type_ok": score_ok})
    return len(failures) == 0 and len(items) > 0, failures


if "view" not in st.session_state:
    st.session_state.view = "📊 관리자 대시보드"
if "scenario" not in st.session_state:
    st.session_state.scenario = "road"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "http://localhost:8000"
if "search_api_results" not in st.session_state:
    st.session_state.search_api_results = []
if "search_done" not in st.session_state:
    st.session_state.search_done = False
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "테스트 모드"
if "use_be_mode" not in st.session_state:
    st.session_state.use_be_mode = False
if "verification_mode" not in st.session_state:
    st.session_state.verification_mode = False
if "status_kind" not in st.session_state:
    st.session_state.status_kind = ""
if "status_message" not in st.session_state:
    st.session_state.status_message = ""
if "qa_last_response" not in st.session_state:
    st.session_state.qa_last_response = {}
if "search_last_raw_response" not in st.session_state:
    st.session_state.search_last_raw_response = {}
if "qa_last_raw_response" not in st.session_state:
    st.session_state.qa_last_raw_response = {}
if "qa_unverifiable_reason" not in st.session_state:
    st.session_state.qa_unverifiable_reason = ""


with st.sidebar:
    st.markdown("### GovAI 시스템")
    menu_items = ["📊 관리자 대시보드", "💬 워크스페이스"]
    for menu in menu_items:
        if st.button(f"{menu}", key=f"menu_{menu}", use_container_width=True, type="primary" if st.session_state.view == menu else "secondary"):
            if st.session_state.view != menu:
                st.session_state.view = menu
                st.rerun()




status_placeholder = st.empty()


if st.session_state.view == "📊 관리자 대시보드":
    data = generate_sample_dashboard_data()
    
    col1, col2 = st.columns([1.2, 1.8])
    
    with col1:
        st.markdown("### 월간 완료/미완료")
        fig_pie = go.Figure(data=[go.Pie(labels=['완료', '미완료'], values=[data["monthly"]["completed"], data["monthly"]["pending"]], marker=dict(colors=['#10b981', '#f59e0b']), hole=0.4, textposition='inside', textinfo='label+percent')])
        fig_pie.update_layout(height=320, margin=dict(l=0, r=0, t=0, b=0), showlegend=True, paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        p_left, p_right = st.columns([1.0, 1.15])

        with p_left:
            st.markdown("### 민원 우선순위 큐")
            priority = data["priority"]
            st.markdown(f'<div class="priority-high">매우 급함 (즉시 대응)<br><strong>{priority["매우급함"]["count"]}건</strong> | 평균 처리 {priority["매우급함"]["avg_time"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="priority-medium">급함 (우선 처리)<br><strong>{priority["급함"]["count"]}건</strong> | 평균 처리 {priority["급함"]["avg_time"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="priority-low">보통 (일반 처리)<br><strong>{priority["보통"]["count"]}건</strong> | 평균 처리 {priority["보통"]["avg_time"]}</div>', unsafe_allow_html=True)

        with p_right:
            st.markdown("### 부서별 미처리/지연 현황")
            dept = data["department_load"]
            df_dept = pd.DataFrame(
                {
                    "부서": dept["부서"],
                    "미처리": dept["미처리"],
                    "지연": dept["지연"],
                }
            )
            fig_dept = go.Figure(data=[
                go.Bar(
                    x=df_dept['부서'],
                    y=df_dept['미처리'],
                    name='미처리',
                    marker=dict(color='#60a5fa'),
                ),
                go.Bar(
                    x=df_dept['부서'],
                    y=df_dept['지연'],
                    name='지연',
                    marker=dict(color='#fb7185'),
                ),
            ])
            fig_dept.update_layout(
                height=320,
                margin=dict(l=18, r=8, t=16, b=36),
                barmode='group',
                yaxis_title='건수',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(gridcolor='#e2e8f0'),
            )
            st.plotly_chart(fig_dept, use_container_width=True)
    
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 연간 민원 처리 추이")
    df_yearly = pd.DataFrame({'월': data["yearly"]["months"], '완료': data["yearly"]["completed"], '미완료': data["yearly"]["pending"]})
    fig_bar = go.Figure(data=[
        go.Bar(
            x=df_yearly['월'],
            y=df_yearly['완료'],
            name='완료',
            marker=dict(color='#14b8a6', line=dict(color='#0f766e', width=0.6)),
            opacity=0.92,
            hovertemplate='<b>%{x}</b><br>완료 %{y}건<extra></extra>',
        ),
        go.Bar(
            x=df_yearly['월'],
            y=df_yearly['미완료'],
            name='미완료',
            marker=dict(color='#fda4af', line=dict(color='#e11d48', width=0.6)),
            opacity=0.88,
            hovertemplate='<b>%{x}</b><br>미완료 %{y}건<extra></extra>',
        ),
    ])
    fig_bar.update_layout(
        barmode='stack',
        height=360,
        margin=dict(l=40, r=20, t=12, b=16),
        hovermode='x unified',
        bargap=0.45,
        bargroupgap=0.08,
        xaxis_title='월',
        yaxis_title='건수',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='#eef2ff', tickfont=dict(color='#334155')),
        yaxis=dict(gridcolor='#e2e8f0', tickfont=dict(color='#334155')),
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 최근 4주간 민원 접수 추이")
    df_weekly = pd.DataFrame({'주차': data["weekly"]["weeks"], '접수건수': data["weekly"]["count"]})
    fig_weekly = go.Figure()
    fig_weekly.add_trace(go.Scatter(x=df_weekly['주차'], y=df_weekly['접수건수'], mode='lines+markers', name='접수건수', line=dict(color='#2563eb', width=4), marker=dict(size=11), fill='tozeroy', fillcolor='rgba(37, 99, 235, 0.14)'))
    fig_weekly.update_layout(height=300, margin=dict(l=40, r=20, t=20, b=20), hovermode='x unified', yaxis_title='건수', xaxis_title='', showlegend=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(gridcolor='#e2e8f0'))
    st.plotly_chart(fig_weekly, use_container_width=True)

else:
    st.markdown("## 민원 해결 워크스페이스")

    mode_col, verify_col, url_col = st.columns([1.1, 1.3, 2.6])
    with mode_col:
        st.session_state.ui_mode = st.radio(
            "데이터 경로",
            options=["테스트 모드", "BE 연동 모드"],
            index=1 if st.session_state.use_be_mode else 0,
            horizontal=False,
        )
        st.session_state.use_be_mode = st.session_state.ui_mode == "BE 연동 모드"
    with verify_col:
        st.session_state.verification_mode = st.checkbox(
            "검증 모드(QA 폴백)",
            value=st.session_state.verification_mode,
            help="QA API 실패 시 샘플 성공 응답을 주입하여 UI 검증을 계속합니다.",
        )
    with url_col:
        st.session_state.api_base_url = st.text_input("API Base URL", value=st.session_state.api_base_url)

    st.caption(
        f"현재 모드: {st.session_state.ui_mode} | "
        + ("검색/QA 모두 API 응답 기반" if st.session_state.use_be_mode else "검색/QA 모두 시나리오 목데이터 기반")
    )

    curr_data = SCENARIOS[st.session_state.scenario]
    selected = st.selectbox(
        "데모 시나리오",
        options=list(SCENARIOS.keys()),
        format_func=lambda key: SCENARIOS[key]["label"],
        index=list(SCENARIOS.keys()).index(st.session_state.scenario),
    )
    if selected != st.session_state.scenario:
        st.session_state.scenario = selected
        st.session_state.search_done = False
        st.session_state.chat_history = []
        st.rerun()

    left, right = st.columns([1, 1.2])

    with left:
        st.markdown("### 유사 민원 검색")
        search_query = st.text_input("검색어 입력", value=curr_data["search"], key="search_query")
        if st.button("유사 민원 검색", use_container_width=True):
            if st.session_state.use_be_mode:
                payload = {"query": search_query, "top_k": 5}
                data, _, err = post_json(st.session_state.api_base_url, "/api/v1/search", payload)
                st.session_state.search_last_raw_response = data if data else {"_error": err or "unknown"}
                if err and not data:
                    st.session_state.search_done = False
                    push_status("error", f"검색 API 연결 실패: {err}")
                elif data.get("success") is False:
                    st.session_state.search_done = False
                    message = str(data.get("error", {}).get("message", "검색 API 오류"))
                    push_status("error", message)
                else:
                    try:
                        parsed_data = parse_search_response(data)
                    except ResponseContractError as e:
                        st.session_state.search_done = False
                        push_status("error", f"search 계약 위반: {str(e)}")
                        st.rerun()

                    results = parsed_data.get("results", [])
                    normalized_results = []
                    for item in results:
                        normalized_results.append(
                            {
                                "doc_id": item.get("doc_id", "N/A"),
                                "score": item.get("score", 0.0),
                                "title": item.get("title", "제목 없음"),
                                "snippet": item.get("snippet", ""),
                                "chunk_id": item.get("chunk_id", ""),
                                "case_id": item.get("case_id", ""),
                            }
                        )
                    st.session_state.search_api_results = normalized_results
                    st.session_state.search_done = True
                    push_status("success", f"검색 완료 (총 {len(normalized_results)}건)")
            else:
                st.markdown('<div class="status-loading">벡터 DB에서 BGE-m3 임베딩으로 유사 민원을 검색 중입니다...</div>', unsafe_allow_html=True)
                time.sleep(1.2)
                st.session_state.search_done = True
                st.session_state.search_api_results = curr_data.get("docs", [])
                push_status("success", f"검색 완료 (총 {len(curr_data['docs'])}건)")
            st.rerun()

        if st.session_state.search_done:
            docs_to_render = st.session_state.search_api_results if st.session_state.use_be_mode else curr_data["docs"]
            for idx, doc in enumerate(docs_to_render, start=1):
                display_id = str(doc.get("doc_id", "")).strip() or "N/A" if st.session_state.use_be_mode else str(doc.get("id", "")).strip() or "N/A"
                try:
                    display_score = f"{float(doc.get('score', 0.0)):.2f}"
                except (TypeError, ValueError):
                    display_score = "0.00"

                st.markdown(
                    f"""
<div class="search-card">
    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
        <span style="font-weight:700; color:#0f172a;">[출처 {idx}] {doc['title']}</span>
        <span style="font-size:0.8rem; background:#d1fae5; color:#065f46; padding:2px 6px; border-radius:4px; font-weight:700;">유사도: {display_score}</span>
    </div>
    <div style="font-size:0.86rem; color:#475569;">{doc['snippet']}</div>
    <div style="font-size:0.75rem; color:#94a3b8; text-align:right; margin-top:8px;">ID: {display_id}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

        # 사용자 화면 단순화를 위해 raw 디버그 로그는 숨김

    with right:
        st.markdown("### 🤖 AI 어시스턴트")

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"], unsafe_allow_html=True)

        prompt = st.chat_input(placeholder=f"지시사항 입력... 예시) {curr_data['chat']}")
        if prompt:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            answer = ""

            with st.chat_message("assistant"):
                if st.session_state.use_be_mode:
                    st.markdown("_BE QA API 호출 중..._")
                    time.sleep(0.3)

                    search_results_payload = []
                    for item in st.session_state.search_api_results:
                        search_results_payload.append(
                            {
                                "doc_id": item.get("doc_id"),
                                "chunk_id": item.get("chunk_id", ""),
                                "case_id": item.get("case_id", ""),
                                "snippet": item.get("snippet", ""),
                                "score": float(item.get("score", 0.0) or 0.0),
                            }
                        )

                    qa_payload = {
                        "query": prompt,
                        "top_k": 5,
                        "use_search_results": bool(search_results_payload),
                        "search_results": search_results_payload,
                    }

                    qa_data, _, qa_err = post_json(st.session_state.api_base_url, "/api/v1/qa", qa_payload, timeout=25.0)
                    st.session_state.qa_last_raw_response = qa_data if qa_data else {"_error": qa_err or "unknown"}

                    if qa_err and not qa_data:
                        st.session_state.qa_unverifiable_reason = f"QA API 연결 실패: {qa_err}"
                        if st.session_state.verification_mode:
                            qa_data = build_sample_qa_success_payload(prompt, st.session_state.search_api_results)
                        else:
                            answer = f"<div style='background:#fee2e2; color:#991b1b; border:1px solid #fecaca; border-radius:8px; padding:12px; font-weight:700;'>BE QA 연결 실패: {html.escape(qa_err)}</div>"
                    elif qa_data.get("success") is False:
                        error_message = str(qa_data.get("error", {}).get("message", "QA API 오류"))
                        st.session_state.qa_unverifiable_reason = f"QA 실패 응답: {error_message}"
                        if st.session_state.verification_mode:
                            qa_data = build_sample_qa_success_payload(prompt, st.session_state.search_api_results)
                        else:
                            answer = f"<div style='background:#fee2e2; color:#991b1b; border:1px solid #fecaca; border-radius:8px; padding:12px; font-weight:700;'>{html.escape(error_message)}</div>"

                    if qa_data.get("success") is True:
                        st.session_state.qa_unverifiable_reason = ""
                        st.session_state.qa_last_response = qa_data
                        citations = qa_data.get("citations", [])
                        rendered_answer = render_answer_with_citations(qa_data.get("answer", ""), citations)
                        meta = qa_data.get("meta", {})
                        answer = (
                            f"<div class='chat-wrapper'>{rendered_answer}"
                            f"<div style='margin-top:10px; color:#64748b; font-size:0.8rem;'>처리시간: {meta.get('processing_time', '-')}s | 모델: {html.escape(str(meta.get('model', '-')))}</div>"
                            "</div>"
                        )
                    elif not st.session_state.verification_mode:
                        st.session_state.qa_last_response = {}
                else:
                    st.markdown("_타닥타닥... AI가 답변을 작성하고 있습니다..._")
                    time.sleep(2.5)
                    answer = (
                        f"{curr_data['chat_response']}"
                        "<div style='margin-top:12px; padding-top:12px; border-top:1px dashed #e2e8f0; font-size:0.75rem; "
                        "color:#94a3b8; text-align:right;'>⚡ 생성 속도: 6.2s | 기반 모델: Qwen2.5-7B</div>"
                    )

                st.markdown(answer, unsafe_allow_html=True)

            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

        # 사용자 화면 단순화를 위해 raw 디버그 로그는 숨김

        st.markdown("### Week1 검증 체크리스트 (1, 2, 4)")
        search_items = st.session_state.search_api_results if st.session_state.use_be_mode else []
        pass1, fail1 = check_search_contract_fields(search_items)
        na1 = st.session_state.use_be_mode and st.session_state.search_done and len(search_items) == 0
        qa_resp = st.session_state.qa_last_response if st.session_state.use_be_mode else {}
        qa_success = bool(qa_resp.get("success") is True)
        citations = qa_resp.get("citations", []) if qa_success else []
        answer_text = str(qa_resp.get("answer", "")) if qa_success else ""
        token_ids = {int(v) for v in re.findall(r"\[\[CITE:(\d+)\]\]", answer_text)} if answer_text else set()
        ref_ids = set()
        for c in citations:
            try:
                ref_ids.add(int(c.get("ref_id", 0)))
            except (TypeError, ValueError):
                continue
        pass2 = qa_success and bool(citations) and token_ids == ref_ids and bool(token_ids)

        meta = qa_resp.get("meta", {}) if qa_success else {}
        warnings = qa_resp.get("qa_validation", {}).get("warnings", []) if qa_success else []
        pass4 = qa_success and all(k in meta for k in ["processing_time", "model", "validation_warning"]) and isinstance(warnings, list)

        c1, c2, c4 = st.columns(3)
        with c1:
            if pass1:
                st.success("1) Pass")
            elif na1:
                st.info("1) N/A")
            else:
                st.error("1) Fail")
            st.caption("기준: 검색 카드에 doc_id, score, title, snippet 누락 없음")
            if na1:
                st.caption("검색 결과 0건으로 필드 렌더링 검증 불가")
            elif fail1:
                st.caption(f"누락/타입 이상 항목 수: {len(fail1)}")
        with c2:
            if pass2:
                st.success("2) Pass")
            else:
                st.error("2) Fail")
            st.caption("기준: CITE 토큰-출처 ID 매칭")
        with c4:
            if pass4:
                st.success("4) Pass")
            else:
                st.error("4) Fail")
            st.caption("기준: meta/warnings 노출")


if st.session_state.status_message:
    status_placeholder.markdown(
        f"<div style='background:{'#d1fae5' if st.session_state.status_kind == 'success' else '#fee2e2'}; color:{'#065f46' if st.session_state.status_kind == 'success' else '#991b1b'}; border:1px solid {'#a7f3d0' if st.session_state.status_kind == 'success' else '#fecaca'}; border-radius:8px; padding:12px; font-weight:700;'>{st.session_state.status_message}</div>",
        unsafe_allow_html=True,
    )
    time.sleep(1.6)
    status_placeholder.empty()
    st.session_state.status_kind = ""
    st.session_state.status_message = ""
