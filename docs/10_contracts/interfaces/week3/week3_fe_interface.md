# Week 3 FE 인터페이스 문서

문서 버전: v1.0-week3-draft  
작성일: 2026-03-27  
책임: FE  
협업: BE2, BE3

---

## 1) 책임 범위

Week 3에서 FE는 **검색 UI 연결** 및 **벤치마크 결과 시각화**를 담당한다.

### 1.1 주요 작업
1. 검색 UI(쿼리 입력/필터/결과 카드) 연결
2. `/search` API 통합
3. 벤치마크 결과 시각화 대시보드 추가
4. UX 및 오류 처리 개선

---

## 2) 검색 UI 컴포넌트

### 2.1 쿼리 입력창 (`components/SearchQueryInput.py`)

```python
# Streamlit UI
import streamlit as st

st.title("✍️ 민원 검색")

# 검색 쿼리 입력
query = st.text_input(
    "검색할 민원을 입력하세요",
    placeholder="예: 포트홀 신고 절차"
)

# 검색 버튼
if st.button("🔍 검색", key="search_btn"):
    if query.strip():
        # BE2로 검색 요청
        search_result = search_service.search(query)
        st.session_state.search_results = search_result
    else:
        st.warning("검색어를 입력해주세요.")
```

### 2.2 필터 UI (`components/SearchFilters.py`)

```python
import streamlit as st

st.subheader("필터")

# 2개 컬럼 레이아웃
col1, col2 = st.columns(2)

with col1:
    region = st.selectbox(
        "지역",
        options=["전체", "서울시", "경기도", "인천시"],
        key="filter_region"
    )

with col2:
    category = st.selectbox(
        "카테고리",
        options=["전체", "도로안전", "건설공사", "상수도", "가로등"],
        key="filter_category"
    )

# 기타 필터
with st.expander("날짜 필터"):
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("시작일")
    with col2:
        date_to = st.date_input("종료일")

# 필터 객체 반환
filters_dict = {
    "region": region if region != "전체" else None,
    "category": category if category != "전체" else None,
    "date_from": date_from.isoformat() if date_from else None,
    "date_to": date_to.isoformat() if date_to else None
}

return {k: v for k, v in filters_dict.items() if v}  # None 제거
```

### 2.3 검색 결과 카드 (`components/SearchResultCard.py`)

```python
import streamlit as st

def display_search_result(rank: int, result: dict):
    """
    검색 결과 개별 카드 표시.
    """
    with st.container(border=True):
        # 순위 + 유사도 점수
        col1, col2 = st.columns([1, 4])
        with col1:
            st.metric("순위", f"#{rank}")
        with col2:
            score_pct = result["similarity_score"] * 100
            st.metric("유사도", f"{score_pct:.0f}%")
        
        # 4요소 표시
        st.markdown("**📋 민원 내용**")
        cols = st.columns(2)
        with cols[0]:
            st.write("**상황(Observation)**")
            st.write(result["content"]["observation"][:100] + "...")
        with cols[1]:
            st.write("**결과(Result)**")
            st.write(result["content"]["result"][:100] + "...")
        
        cols = st.columns(2)
        with cols[0]:
            st.write("**요청(Request)**")
            st.write(result["content"]["request"][:100] + "...")
        with cols[1]:
            st.write("**배경(Context)**")
            st.write(result["content"]["context"][:100] + "...")
        
        # 메타데이터
        st.markdown("---")
        st.caption(
            f"📍 {result['metadata']['region']} | "
            f"🏷️ {result['metadata']['category']} | "
            f"📅 {result['metadata']['created_at'][:10]}"
        )
```

### 2.4 검색 결과 목록 (`pages/Search.py`)

```python
import streamlit as st
from ui.services.search_service import SearchService

st.set_page_config(page_title="검색", layout="wide")

st.title("🔍 유사 민원 검색")

# 검색 영역
search_tab, history_tab = st.tabs(["검색", "검색 이력"])

with search_tab:
    # 필터 입력
    filters = st.sidebar.form("search_filters")
    with filters:
        query = st.text_input("검색 쿼리")
        region = st.selectbox("지역", ["전체", "서울시", "경기도", "인천시"])
        category = st.selectbox("카테고리", ["전체", "도로안전", "건설공사", "상수도", "가로등"])
        top_k = st.slider("결과 개수", 1, 20, 5)
        
        submitted = st.form_submit_button("🔍 검색")
    
    if submitted and query:
        # 검색 실행
        search_service = SearchService()
        result = search_service.search(
            query=query,
            top_k=top_k,
            filters={
                "region": region if region != "전체" else None,
                "category": category if category != "전체" else None
            }
        )
        
        # 결과 표시
        if result.get("success"):
            st.success(f"✅ {result['data']['total_found']}건 중 상위 {len(result['data']['results'])}건 검색")
            st.caption(f"조회 시간: {result['data']['elapsed_ms']}ms")
            
            for idx, r in enumerate(result['data']['results'], 1):
                display_search_result(idx, r)
        else:
            st.error(f"❌ 검색 오류: {result['error']['message']}")

with history_tab:
    st.write("검색 이력이 여기에 표시됩니다.")
```

---

## 3) 검색 서비스 (`ui/services/search_service.py`)

```python
import requests
from typing import Dict, Any

class SearchService:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
    
    def search(self, query: str, top_k: int = 5, filters: Dict = None) -> Dict[str, Any]:
        """
        검색 API 호출.
        """
        endpoint = f"{self.api_url}/search"
        
        payload = {
            "request_id": f"SRCH-{uuid.uuid4()}",
            "query": query,
            "top_k": top_k,
            "filters": filters or {}
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": {
                    "code": "SEARCH_ERROR",
                    "message": str(e)
                }
            }
```

---

## 4) 벤치마크 결과 시각화 (`pages/ModelBenchmark.py`)

### 4.1 벤치마크 대시보드

```python
import streamlit as st
import pandas as pd
import plotly.express as px
import json

st.set_page_config(page_title="모델 벤치마크", layout="wide")

st.title("🤖 LLM 모델 벤치마크 결과")

# 리포트 로드
@st.cache_data
def load_benchmark_report():
    with open("logs/evaluation/week3/model_benchmark_report_final.json") as f:
        return json.load(f)

report = load_benchmark_report()

# 요약 통계
st.subheader("📊 벤치마크 요약")
col1, col2, col3 = st.columns(3)

models = report["models"]
with col1:
    fastest = min(models, key=lambda x: x["metrics"]["avg_response_time_ms"])
    st.metric(
        "⚡ 가장 빠른 모델",
        fastest["model_name"],
        f"{fastest['metrics']['avg_response_time_ms']}ms"
    )

with col2:
    most_stable = max(models, key=lambda x: x["metrics"]["json_parse_success_rate"])
    st.metric(
        "✅ 가장 안정적인 모델",
        most_stable["model_name"],
        f"{most_stable['metrics']['json_parse_success_rate']*100:.0f}%"
    )

with col3:
    total_tests = sum(m["metrics"]["total_tests"] for m in models)
    total_success = sum(m["metrics"]["successful_tests"] for m in models)
    st.metric(
        "📈 총 성공률",
        f"{total_success}/{total_tests}",
        f"{total_success/total_tests*100:.0f}%"
    )

# 상세 비교 테이블
st.subheader("📋 모델별 상세 지표")

df_data = []
for m in models:
    metrics = m["metrics"]
    df_data.append({
        "모델": m["model_name"],
        "평균응답(ms)": metrics["avg_response_time_ms"],
        "P95응답(ms)": metrics["p95_response_time_ms"],
        "파싱성공율(%)": f"{metrics['json_parse_success_rate']*100:.0f}",
        "성공/총": f"{metrics['successful_tests']}/{metrics['total_tests']}"
    })

df = pd.DataFrame(df_data)
st.dataframe(df, use_container_width=True)

# 응답시간 비교 차트
st.subheader("⏱️ 응답 시간 비교")
fig_time = px.bar(
    df,
    x="모델",
    y="평균응답(ms)",
    title="모델별 평균 응답 시간",
    color="평균응답(ms)"
)
st.plotly_chart(fig_time, use_container_width=True)

# 안정성 비교 차트
st.subheader("🛡️ 파싱 성공률 비교")
fig_stability = px.bar(
    df,
    x="모델",
    y="파싱성공율(%)",
    title="모델별 JSON 파싱 성공률",
    color="파싱성공율(%)"
)
st.plotly_chart(fig_stability, use_container_width=True)

# 추천사항
st.subheader("💡 권장사항")
recommendation = report["comparison"]["recommendation"]
st.info(recommendation)
```

---

## 5) 오류 처리 개선

### 5.1 API 오류 시뮬레이션

```python
# 검색 실패 처리
if result.get("success") == False:
    error_code = result["error"]["code"]
    error_message = result["error"]["message"]
    is_retryable = result["error"]["retryable"]
    
    if error_code == "SEARCH_TIMEOUT":
        st.warning("⏱️ 검색이 너무 오래 걸렸습니다. 다시 시도해주세요.")
    elif error_code == "COLLECTION_NOT_FOUND":
        st.error("❌ 검색 인덱스를 찾을 수 없습니다. 관리자에 문의하세요.")
    elif error_code == "FILTER_INVALID":
        st.warning(f"⚠️ 필터 형식 또는 값이 올바르지 않습니다. 필터를 수정해주세요. ({error_message})")
    else:
        st.error(f"❌ 검색 오류: {error_message}")
    
    if is_retryable:
        if st.button("🔄 다시 시도"):
            st.rerun()
```

---

## 6) Week 3 FE 체크리스트

- [ ] 검색 쿼리 입력 UI 구현
- [ ] 필터 UI (지역/카테고리/기간) 구현
- [ ] 검색 결과 카드 디자인 완료
- [ ] `/search` API 통합 테스트
- [ ] 벤치마크 대시보드 페이지 구현
- [ ] 오류 처리 및 재시도 로직 테스트
- [ ] UI/UX 리뷰 및 개선
