import time

import streamlit as st

st.set_page_config(page_title="GovAI - Frontend Integrated", layout="wide", initial_sidebar_state="expanded")

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

    /* Streamlit 기본 페이지 네비(Home/init) 숨김 */
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

    section[data-testid="stSidebar"] button[kind="secondary"]:focus,
    section[data-testid="stSidebar"] button[kind="primary"]:focus {
        box-shadow: none;
        outline: none;
    }

    /* 우측 상단 Deploy/메뉴 숨김 */
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

    .toolbar {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 10px 14px;
        margin-bottom: 14px;
    }

    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 12px;
        padding: 18px;
    }

    .kpi-label {
        color: var(--text-muted);
        font-size: 0.9rem;
    }

    .kpi-value-good {
        color: #10b981;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .kpi-value-warn {
        color: #f59e0b;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .badge {
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 8px;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 700;
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

    .cit {
        background: #fef08a;
        padding: 2px 6px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .status-loading {
        background: #dbeafe;
        color: #1e40af;
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-success {
        background: #d1fae5;
        color: #065f46;
        border: 1px solid #a7f3d0;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-error {
        background: #fee2e2;
        color: #991b1b;
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-empty {
        background: #fef3c7;
        color: #92400e;
        border: 1px solid #fde68a;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

</style>
""",
    unsafe_allow_html=True,
)


SCENARIOS = {
    "road": {
        "label": "1. 도로안전 (포트홀)",
        "raw": "어제 비 오고 나서 중앙로 사거리 횡단보도 앞에 구멍이 크게 파였어요. 오토바이 지나가다 넘어질 뻔했습니다. 빨리 메워주세요.",
        "search": "포트홀, 도로 파손, 이륜차 사고",
        "chat": "이 사례를 바탕으로 도로보수팀 긴급 작업 지시서를 작성해줘.",
        "entities": [
            ("LOCATION: 중앙로 사거리", "#dbeafe", "#1e40af"),
            ("HAZARD: 구멍(포트홀)", "#fee2e2", "#991b1b"),
            ("TIME: 어제 우천 후", "#fef3c7", "#92400e"),
        ],
        "struct": {
            "관찰": "횡단보도 앞 노면 파손(포트홀) 발생",
            "결과": "이륜차(오토바이) 통행 시 전도 등 안전사고 발생 위험 고조",
            "요청": "추가 사고 예방을 위한 신속한 노면 보수 및 평탄화 작업",
            "맥락": "우천 직후 아스팔트 지반 약화로 인한 파손 추정",
        },
        "docs": [
            {
                "id": "DOC-25-102",
                "score": "0.94",
                "title": "중앙로 10m 인근 포트홀 임시 복구 완료건",
                "snippet": "...우천 후 배수 불량으로 발생한 포트홀에 대해 긴급 아스팔트 타설 완료...",
            },
            {
                "id": "DOC-25-088",
                "score": "0.89",
                "title": "이륜차 전도사고 발생 (노면 불량)",
                "snippet": "...야간 주행 중 도로 파인 곳을 발견하지 못하고 배달 오토바이가 전도됨...",
            },
            {
                "id": "DOC-24-912",
                "score": "0.81",
                "title": "장마철 상습 침수 및 지반 약화 구간 안내",
                "snippet": "...해당 교차로는 장마철마다 노면 패임 현상이 잦아 근본적인 재포장 필요...",
            },
        ],
        "chat_response": """
<b>[도로보수팀 긴급 작업 지시서]</b><br><br>
<b>1. 작업 개요</b><br>
- 위치: 중앙로 사거리 횡단보도 앞<br>
- 내용: 우천으로 인한 포트홀 긴급 평탄화 및 복구<br><br>
<b>2. 특이 및 위험 사항</b><br>
- 이륜차 전도 위험이 매우 높으므로 최우선 처리 요망. <span class='cit'>[출처 2]</span><br>
- 과거 우천 후 파손 이력이 있으므로 단순 땜질이 아닌 방수 처리를 병행할 것. <span class='cit'>[출처 1]</span>
""",
    },
    "env": {
        "label": "2. 환경 (무단투기)",
        "raw": "골목길 전봇대 아래에 누가 자꾸 쓰레기를 버리고 도망갑니다. 냄새나서 창문을 못 열겠어요. CCTV 달아주세요.",
        "search": "무단투기, 악취, CCTV 설치",
        "chat": "CCTV 설치 타당성 검토 요청서를 유관 부서용으로 작성해줘.",
        "entities": [
            ("FACILITY: 전봇대 아래", "#e0e7ff", "#3730a3"),
            ("HAZARD: 쓰레기 무단투기", "#fee2e2", "#991b1b"),
        ],
        "struct": {
            "관찰": "골목길 전봇대 주변 상습적인 생활 쓰레기 불법 투기",
            "결과": "악취 및 해충 유입으로 인한 주민 주거 환경 침해",
            "요청": "무단투기자 단속 및 예방을 위한 CCTV 설치",
            "맥락": "야간 사각지대를 이용한 상습적 행위로 추정",
        },
        "docs": [
            {
                "id": "DOC-25-301",
                "score": "0.96",
                "title": "상습 투기지역 이동식 단속 카메라 배치 결과",
                "snippet": "...고정식 CCTV 예산 부족으로 센서형 이동식 카메라를 배치한 결과 투기율 70% 감소...",
            },
            {
                "id": "DOC-25-215",
                "score": "0.85",
                "title": "야간 형광 경고문 부착 및 효과 분석",
                "snippet": "...CCTV 설치 전 임시 조치로 부착한 야간 형광 경고문이 일정 부분 억제 효과를 보임...",
            },
            {
                "id": "DOC-24-882",
                "score": "0.82",
                "title": "전신주 주변 폐기물 수거 지연 민원",
                "snippet": "...전신주 아래 방치된 쓰레기로 인해 여름철 해충 민원이 급증...",
            },
        ],
        "chat_response": """
<b>[방범용 CCTV 설치 타당성 검토 요청서]</b><br><br>
<b>1. 현황 및 문제점</b><br>
전신주 주변 사각지대를 이용한 상습 투기가 반복되고 악취 피해가 심각합니다. <span class='cit'>[출처 3]</span><br><br>
<b>2. 검토 요청 사항</b><br>
- 고정식 예산이 부족하면 센서형 이동식 단속 카메라 우선 배치를 검토 바랍니다. <span class='cit'>[출처 1]</span><br>
- 설치 전 임시 조치로 야간 형광 경고문 선부착을 요청합니다. <span class='cit'>[출처 2]</span>
""",
    },
    "noise": {
        "label": "3. 소음 (층간소음)",
        "raw": "밤 11시만 되면 위층에서 쿵쿵대고 의자 끄는 소리가 납니다. 관리사무소에 말해도 안 고쳐집니다. 미치겠어요.",
        "search": "층간소음, 아파트 분쟁, 야간 소음",
        "chat": "층간소음 분쟁 중재 절차 안내문을 민원인에게 보낼 형식으로 작성해줘.",
        "entities": [
            ("TIME: 밤 11시", "#fef3c7", "#92400e"),
            ("TYPE: 층간소음(발망치)", "#fee2e2", "#991b1b"),
        ],
        "struct": {
            "관찰": "심야 시간대(23시 이후) 상층부 거주자의 지속적인 층간소음 유발",
            "결과": "수면 방해 및 극심한 스트레스로 이웃 간 갈등 심화",
            "요청": "행정적/법적 분쟁 중재 절차 제공",
            "맥락": "공동주택 구조와 거주자 인식 부족이 복합적으로 작용",
        },
        "docs": [
            {
                "id": "DOC-25-412",
                "score": "0.95",
                "title": "환경부 층간소음 이웃사이센터 연계 지원 사례",
                "snippet": "...전문가 방문 상담 및 소음 측정 지원으로 갈등 완화...",
            },
            {
                "id": "DOC-25-188",
                "score": "0.91",
                "title": "공동주택 층간소음 관리규약 준수 권고",
                "snippet": "...야간(22시~06시) 가구 이동과 충격 소음 금지 권고...",
            },
            {
                "id": "DOC-24-765",
                "score": "0.79",
                "title": "층간소음 분쟁조정위원회 회부 절차 안내",
                "snippet": "...합의 결렬 시 관할 지자체 조정위원회 신청 가능...",
            },
        ],
        "chat_response": """
<b>[층간소음 분쟁 중재 절차 안내]</b><br><br>
심야 층간소음으로 인한 불편에 공감하며 아래의 공적 절차를 안내드립니다.<br><br>
<b>1. 층간소음 이웃사이센터 신청</b><br>
전문가 현장 방문 상담 및 소음 측정 지원이 가능합니다. <span class='cit'>[출처 1]</span><br><br>
<b>2. 분쟁조정위원회 회부</b><br>
센터 지원으로 해결되지 않으면 관할 지자체 조정위원회에 공식 신청할 수 있습니다. <span class='cit'>[출처 3]</span>
""",
    },
}


def reset_outputs() -> None:
    st.session_state.struct_done = False
    st.session_state.search_done = False
    st.session_state.chat_history = []


def push_status(kind: str, message: str) -> None:
    st.session_state.status_kind = kind
    st.session_state.status_message = message


if "view" not in st.session_state:
    st.session_state.view = "📊 관리자 대시보드"
if "scenario" not in st.session_state:
    st.session_state.scenario = "road"
if "struct_done" not in st.session_state:
    st.session_state.struct_done = False
if "search_done" not in st.session_state:
    st.session_state.search_done = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "status_kind" not in st.session_state:
    st.session_state.status_kind = ""
if "status_message" not in st.session_state:
    st.session_state.status_message = ""


with st.sidebar:
    st.markdown("### GovAI System")
    menu_items = ["📊 관리자 대시보드", "📝 데이터 적재", "💬 워크스페이스"]
    for menu in menu_items:
        if st.button(
            f"{menu}",
            key=f"menu_{menu}",
            use_container_width=True,
            type="primary" if st.session_state.view == menu else "secondary",
        ):
            if st.session_state.view != menu:
                st.session_state.view = menu
                st.rerun()

curr_data = SCENARIOS[st.session_state.scenario]

toolbar_left, toolbar_right = st.columns([2.4, 1.6])
with toolbar_left:
    selected = st.selectbox(
        "데모 시나리오",
        options=list(SCENARIOS.keys()),
        format_func=lambda key: SCENARIOS[key]["label"],
        index=list(SCENARIOS.keys()).index(st.session_state.scenario),
    )
with toolbar_right:
    b1, b2 = st.columns(2)
    if b1.button("Error UI", use_container_width=True):
        push_status("error", "OOM 발생: VRAM 용량 초과")
    if b2.button("Empty UI", use_container_width=True):
        push_status("empty", "해당 조건의 검색 결과가 없습니다.")

if selected != st.session_state.scenario:
    st.session_state.scenario = selected
    reset_outputs()
    st.rerun()

status_placeholder = st.empty()

curr_data = SCENARIOS[st.session_state.scenario]

if st.session_state.view == "📊 관리자 대시보드":
    st.markdown("## 시스템 실시간 KPI (최소 요건)")
    c1, c2, c3 = st.columns(3)
    c1.markdown(
        '<div class="kpi-card"><div class="kpi-label">구조화 F1 Score</div><div class="kpi-value-good">0.84</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        '<div class="kpi-card"><div class="kpi-label">검색 정확도 Recall@5</div><div class="kpi-value-good">0.88</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        '<div class="kpi-card"><div class="kpi-label">평균 응답 지연 (초)</div><div class="kpi-value-warn">6.8s</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="card"><p style="color:#64748b; text-align:center; margin:0;">(통계 차트 영역 - 추후 연동)</p></div>', unsafe_allow_html=True)

elif st.session_state.view == "📝 데이터 적재":
    st.markdown("## 신규 민원 데이터 적재 및 구조화")
    raw_text = st.text_area("원본 텍스트 입력", value=curr_data["raw"], height=120)
    if st.button("구조화 분석 및 DB 적재 실행", type="primary", use_container_width=True):
        st.markdown('<div class="status-loading">AI가 텍스트를 분석하여 4요소 및 엔티티를 추출 중입니다...</div>', unsafe_allow_html=True)
        time.sleep(1.5)
        st.session_state.struct_done = True
        push_status("success", "DB 적재 성공 및 구조화 완료")
        st.rerun()

    if st.session_state.struct_done:
        st.markdown("### 분석 완료 (DB 적재 성공)")
        badge_html = ""
        for text, bg, fg in curr_data["entities"]:
            badge_html += f'<span class="badge" style="background:{bg}; color:{fg};">{text}</span>'
        st.markdown(f"<div>{badge_html}</div>", unsafe_allow_html=True)

        s = curr_data["struct"]
        st.markdown(
            f"""
<div class="card" style="line-height:1.8;">
    <div><b style="display:inline-block; width:60px; color:#2563eb;">관찰</b>{s['관찰']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">결과</b>{s['결과']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">요청</b>{s['요청']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">맥락</b><span style="color:#64748b;">{s['맥락']}</span></div>
</div>
""",
            unsafe_allow_html=True,
        )

else:
    st.markdown("## 민원 해결 워크스페이스")
    left, right = st.columns([1, 1.2])

    with left:
        st.markdown("### 유사 민원 검색")
        st.text_input("검색어 입력", value=curr_data["search"], key="search_query")
        if st.button("유사 민원 검색", use_container_width=True):
            st.markdown('<div class="status-loading">벡터 DB에서 BGE-m3 임베딩으로 유사 민원을 검색 중입니다...</div>', unsafe_allow_html=True)
            time.sleep(1.2)
            st.session_state.search_done = True
            push_status("success", f'검색 완료 (총 {len(curr_data["docs"])}건)')
            st.rerun()

        if st.session_state.search_done:
            for idx, doc in enumerate(curr_data["docs"], start=1):
                st.markdown(
                    f"""
<div class="search-card">
    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
        <span style="font-weight:700; color:#0f172a;">[출처 {idx}] {doc['title']}</span>
        <span style="font-size:0.8rem; background:#d1fae5; color:#065f46; padding:2px 6px; border-radius:4px; font-weight:700;">유사도: {doc['score']}</span>
    </div>
    <div style="font-size:0.86rem; color:#475569;">{doc['snippet']}</div>
    <div style="font-size:0.75rem; color:#94a3b8; text-align:right; margin-top:8px;">ID: {doc['id']}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

    with right:
        st.markdown("### AI 어시스턴트")

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"], unsafe_allow_html=True)

        prompt = st.chat_input(placeholder=f"지시사항 입력... 예시) {curr_data['chat']}")
        if prompt:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
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

if st.session_state.status_message:
    status_placeholder.markdown(
        f'<div class="status-{st.session_state.status_kind}">{st.session_state.status_message}</div>',
        unsafe_allow_html=True,
    )
    time.sleep(2.0)
    status_placeholder.empty()
    st.session_state.status_kind = ""
    st.session_state.status_message = ""
