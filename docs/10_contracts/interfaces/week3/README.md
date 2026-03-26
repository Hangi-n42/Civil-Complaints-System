# Week 3 인터페이스 인덱스

기준일: 2026-03-27  
범위: Indexing / Search / LLM Benchmark

---

## 📌 Week 3 핵심 변경사항

### 입출력 변화
- **입력**: Week 2의 `StructuredCivilCase` 객체 (변경 없음)
- **출력**: 인덱싱 후 `SearchResult` 및 벤치마크 `ModelEvaluationReport` 추가
- **핵심**: Index/Search E2E는 Week 2 contract를 상속, 새로운 필터링/모델 평가 계약 추가

### 데이터 흐름
```
StructuredCivilCase (BE1 output)
        ↓
   IndexRequest (BE2 input)
        ↓
   [ChromaDB Indexing]
        ↓
   SearchRequest (FE/BE3 input)
        ↓
   [Retrieval Engine]
        ↓
   SearchResult (FE output)
        ↓
   [LLM Benchmark Test]
        ↓
   ModelEvaluationReport (BE1/BE2/BE3 output)
```

---

## 📄 Week 3 인터페이스 문서

| 문서 | 담당 | 목적 |
|-----|------|------|
| [week3_common_interface.md](week3_common_interface.md) | 팀 전체 | IndexRequest, SearchRequest, SearchResult 공통 규약 |
| [week3_be1_interface.md](week3_be1_interface.md) | BE1 | 벤치마크 평가셋/질문셋 준비, 모델 테스트 입출력 |
| [week3_be2_interface.md](week3_be2_interface.md) | BE2 | 인덱싱 전략, 필터 매핑, 검색 메타스키마 |
| [week3_be3_interface.md](week3_be3_interface.md) | BE3 | `POST /index`, `POST /search` 안정화, 모델별 QA 성능 측정 |
| [week3_fe_interface.md](week3_fe_interface.md) | FE | 검색 UI(쿼리입력/필터/결과표시), 벤치마크 결과 시각화 |

---

## 🔄 상속 규칙

- **Common**: Week 2 규칙 상속 (snake_case, UTF-8, ISO-8601 KST)
- **BE1**: Week 2 StructuredCivilCase 정의 사용 (변경 없음)
- **BE2**: 검색 응답 형식 신규 정의 (citations, confidence 추가)
- **BE3**: `/index`, `/search` 에러/재시도 전략 Week 2 상속
- **FE**: Week 2 UI 상태 표시 규칙 상속 + 검색/필터 UI 신규 추가

---

## ✅ Week 3 체크 포인트

| 항목 | 완료 조건 | 상태 |
|-----|---------|------|
| 공통 계약 동결 | 모든 인터페이스 문서 리뷰 완료 | ⏳ 진행중 |
| 인덱싱 E2E | ChromaDB 샘플 500건 이상 인덱싱 | ⏳ 진행중 |
| 검색 기본 동작 | 자유문 쿼리 통해 Top-K 반환 | ⏳ 진행중 |
| 메타필터 안정 | 지역/카테고리/기간 필터 2종 이상 동작 | ⏳ 진행중 |
| 모델 벤치마크 | 5종 모델 QA 생성 성능 측정 완료 | ⏳ 진행중 |
| 1차 리포트 | 모델별 비교표 및 분석 완료 | ⏳ 진행중 |
