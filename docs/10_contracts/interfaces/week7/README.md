# Week 7 인터페이스 인덱스

기준일: 2026-05-01  
범위: FastAPI + Next.js 3단 Workbench E2E 통합

---

## Week 7 핵심 변경사항

### 입출력 변화
- FE는 중앙 목록과 우측 AI 패널을 동시에 구동하는 Workbench 상태 계약을 사용한다.
- BE1은 중앙 목록용 구조화/분류 요약 필드를 제공한다.
- BE2는 우측 패널용 유사 민원 응답을 Workbench 형식으로 고정한다.
- BE3는 답변 초안/근거/제약사항을 편집 가능한 unified schema로 반환한다.

### 데이터 흐름
```
Complaint Select
    ↓
Workbench Summary List (BE1)
    ↓
Similar Complaint Panel (BE2)
    ↓
Editable Draft Answer (BE3)
    ↓
FE 3-way Workbench Render
```

---

## Week 7 인터페이스 문서

| 문서 | 담당 | 목적 |
| --- | --- | --- |
| [week7_fe_interface.md](week7_fe_interface.md) | FE | 3단 Workbench 레이아웃, 상태 UX, 편집 UI 계약 |
| [week7_be1_interface.md](week7_be1_interface.md) | BE1 | 중앙 목록용 구조화/분류 요약 필드 계약 |
| [week7_be2_interface.md](week7_be2_interface.md) | BE2 | 유사 민원 패널 응답 및 retrieval trace 계약 |
| [week7_be3_interface.md](week7_be3_interface.md) | BE3 | 답변 초안/근거/제약사항 편집 가능 스키마 계약 |

---

## 상속 규칙

- Week 5-6에서 확정된 adaptive 필드(`routing_trace`, `routing_hint`, `structured_output`)를 유지한다.
- Week 7에서는 Workbench 화면 통합과 편집 가능성에 초점을 둔다.
- 스키마 변경은 최소화하고, 필요한 경우 하위 호환을 유지한다.

---

## Week 7 체크 포인트

| 항목 | 완료 조건 | 상태 |
| --- | --- | --- |
| 3단 Workbench | 좌/중/우가 동시에 렌더된다 | ⏳ 진행중 |
| 중앙 목록 계약 | summary/list item 필드가 고정된다 | ⏳ 진행중 |
| 유사 민원 패널 | 패널 응답이 FE에서 변환 없이 렌더된다 | ⏳ 진행중 |
| 편집 가능 초안 | answer/citations/limitations가 편집 가능 구조로 제공된다 | ⏳ 진행중 |
