"""
Streamlit 앱 진입점

온디바이스 AI 기반 민원 처리 시스템의 사용자 인터페이스
"""

import streamlit as st
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import api_logger
from app.core.config import settings


def init_session_state():
    """세션 상태 초기화"""
    if "documents" not in st.session_state:
        st.session_state.documents = []
    if "search_results" not in st.session_state:
        st.session_state.search_results = []
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []


def main():
    """메인 함수"""
    # 페이지 설정
    st.set_page_config(
        page_title=settings.API_TITLE,
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 스타일
    st.markdown(
        """
    <style>
    .main {
        padding: 2rem;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # 세션 상태 초기화
    init_session_state()

    # 헤더
    st.title("⚖️ 온디바이스 AI 기반 민원 처리 시스템")
    st.markdown(
        "보안과 프라이버시를 중심으로 한 민원 데이터 심층 분석 및 검색 시스템"
    )

    st.divider()

    # 사이드바 설정
    with st.sidebar:
        st.header("🔧 설정")
        st.info("시스템 정보", icon="ℹ️")
        st.write(f"**모델**: {settings.OLLAMA_MODEL}")
        st.write(f"**임베딩**: {settings.EMBEDDING_MODEL}")
        st.write(f"**벡터DB**: ChromaDB")

        st.divider()

        # 네비게이션
        selected_tab = st.radio(
            "작업 선택",
            [
                "📤 문서 업로드",
                "🔍 검색",
                "💬 챗봇",
            ],
        )

    # 탭별 콘텐츠
    if selected_tab == "📤 문서 업로드":
        render_upload_tab()
    elif selected_tab == "🔍 검색":
        render_search_tab()
    elif selected_tab == "💬 챗봇":
        render_chat_tab()


def render_upload_tab():
    """문서 업로드 탭"""
    st.header("📤 문서 업로드 및 구조화")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 파일 업로드")
        uploaded_files = st.file_uploader(
            "CSV 또는 JSON 파일을 선택하세요",
            type=["csv", "json"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)}개 파일 선택됨")
            for file in uploaded_files:
                st.write(f"- {file.name}")

            if st.button("📨 업로드 및 구조화 시작", use_container_width=True):
                st.info("구조화 진행 중... (실제 로직은 Priority 2에서 구현)")
                # TODO: 실제 업로드 및 구조화 로직 구현
                st.success("✅ 구조화 완료!")

    with col2:
        st.markdown("### 진행 상황")
        st.progress(0.5)
        st.markdown("**상태**: 처리 중...\n\n**처리된 건수**: 0 / 10")


def render_search_tab():
    """검색 탭"""
    st.header("🔍 민원 데이터 검색")

    query = st.text_input(
        "검색 쿼리를 입력하세요",
        placeholder="예: 주택 관련 민원",
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        st.empty()
    with col2:
        search_btn = st.button("🔎 검색", use_container_width=True)

    if search_btn and query:
        st.info("검색 진행 중... (실제 로직은 Priority 3에서 구현)")
        # TODO: 실제 검색 로직 구현

        st.markdown("### 검색 결과")
        st.info(
            "아직 문서가 인덱싱되지 않았습니다. 📤 탭에서 문서를 업로드하세요."
        )

    elif search_btn:
        st.warning("⚠️ 검색 쿼리를 입력해주세요")


def render_chat_tab():
    """챗봇 탭"""
    st.header("💬 AI 챗봇 (RAG 기반 QA)")

    # 대화 히스토리 표시
    st.markdown("### 대화 히스토리")
    for i, msg in enumerate(st.session_state.chat_history):
        if msg["role"] == "user":
            st.chat_message("user").write(msg["content"])
        else:
            st.chat_message("assistant").write(msg["content"])

    # 입력 폼
    st.markdown("---")
    user_input = st.chat_input("질문을 입력하세요...")

    if user_input:
        # 사용자 메시지 표시
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

        # AI 응답 생성
        st.info("응답 생성 중... (실제 로직은 Priority 3에서 구현)")
        # TODO: 실제 QA 로직 구현

        response = "안녕하세요! 어떤 민원에 대해 궁금하신가요? (현재는 더미 응답입니다)"
        st.session_state.chat_history.append(
            {"role": "assistant", "content": response}
        )
        st.chat_message("assistant").write(response)


if __name__ == "__main__":
    main()
