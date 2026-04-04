# Week 4 인터페이스 인덱스

기준일: 2026-04-05  
범위: 단일 RAG baseline 확정, `/qa` 안정화, citation 정합성

---

## Week 4 핵심 변경사항

### 입출력 변화
- 입력: Week 3의 `SearchResult`를 generation 컨텍스트로 상속
- 출력: `QAResponse` 계약을 Gate A 측정 가능 형식으로 고정
- 핵심: answer + citations + limitations + latency를 한 응답 계약으로 통일

### 데이터 흐름
```
StructuredCivilCase (W2)
        ↓
IndexRequest / SearchRequest (W3)
        ↓
SearchResult (W3)
        ↓
QARequest (W4)
        ↓
[Single RAG Generation]
        ↓
QAResponse (W4)
        ↓
GateAReport (W4)
```

---

## Week 4 인터페이스 문서

| 문서 | 담당 | 목적 |
| --- | --- | --- |
| [week4_common_interface.md](week4_common_interface.md) | 팀 전체 | QARequest/QAResponse, Citation, Gate A 측정 공통 규약 |
| [week4_be1_interface.md](week4_be1_interface.md) | BE1 | baseline 평가셋/지표 운영, KPI 산출 계약 |
| [week4_be2_interface.md](week4_be2_interface.md) | BE2 | SearchResult -> QA 컨텍스트 매핑 계약 |
| [week4_be3_interface.md](week4_be3_interface.md) | BE3 | `/qa` 파싱/재시도/검증, citation 정합성 계약 |
| [week4_fe_interface.md](week4_fe_interface.md) | FE | QA 화면 필드/상태 UX 및 에러 표준 |

---

## 상속 규칙

- Common: Week 3 공통 규약(snake_case, UTF-8, ISO-8601 KST) 상속
- BE1: Week 3 평가셋 운영 계약 상속 + Gate A 지표 확정
- BE2: Week 3 검색 계약 상속 + generation 입력 컨텍스트 규격 추가
- BE3: Week 3 에러/로깅 규칙 상속 + `/qa` 파싱 안정화 계약 추가
- FE: Week 3 검색 UI 규칙 상속 + QA 화면 상태 계약 추가

---

## Week 4 체크 포인트

| 항목 | 완료 조건 | 상태 |
| --- | --- | --- |
| 공통 계약 동결 | Week 4 인터페이스 문서 리뷰 완료 | ⏳ 진행중 |
| QA 응답 안정화 | 파싱 성공률 목표치 달성 | ⏳ 진행중 |
| citation 정합성 | chunk_id/case_id/snippet 매핑 일치 | ⏳ 진행중 |
| Gate A 측정 | Recall@5, 4요소 F1, citation 정합성, latency 산출 | ⏳ 진행중 |
