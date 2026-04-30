# Week 7 이슈 인덱스

기준일: 2026-05-01  
범위: FastAPI + Next.js 3단 Workbench E2E 통합

---

## Week 7 핵심 변경사항

### 실행 초점
- FE의 3단 Workbench 화면을 실제 E2E 흐름에 맞춰 고정한다.
- BE1은 중앙 목록에 표시할 구조화/분류 요약 필드를 안정 공급한다.
- BE2는 우측 AI 패널의 유사 민원 응답 형식을 Workbench 표준으로 고정한다.
- BE3는 답변 초안/근거/제약사항을 편집 가능한 응답 스키마로 정규화한다.

### 데이터 흐름
```
Complaint Select
    ↓
Workbench Central List (BE1 summary fields)
    ↓
Similar Complaints / Retrieval Panel (BE2)
    ↓
Draft Answer + Evidence + Constraints (BE3)
    ↓
Editable FE Right Panel
```

---

## Week 7 이슈 문서

| 문서 | 담당 | 목적 |
| --- | --- | --- |
| [task_01_fe_workbench_e2e_ui.md](task_01_fe_workbench_e2e_ui.md) | FE | 3단 Workbench 레이아웃, 상태 UX, 초안 편집 UI |
| [task_02_be1_workbench_summary_fields.md](task_02_be1_workbench_summary_fields.md) | BE1 | 중앙 목록용 구조화/분류 요약 필드 계약 |
| [task_03_be2_similar_complaint_panel.md](task_03_be2_similar_complaint_panel.md) | BE2 | 유사 민원 패널 응답 형식 고정 |
| [task_04_be3_editable_draft_schema.md](task_04_be3_editable_draft_schema.md) | BE3 | 답변 초안/근거/제약 편집 가능 스키마 |

---

## 공통 원칙

- Week5-6에서 고정한 `routing_trace`, `routing_hint`, `structured_output`은 유지한다.
- Week7에서는 화면 통합과 편집 가능성에 초점을 둔다.
- 신규 지표 확장, 벤치마크, 리팩토링 중심 작업은 포함하지 않는다.

---

## Week 7 체크 포인트

| 항목 | 완료 조건 | 상태 |
| --- | --- | --- |
| 3단 Workbench 고정 | 좌/중/우 레이아웃이 단일 페이지에서 동작 | ⏳ 진행중 |
| 중앙 목록 요약 | 구조화/분류 필드가 민원 목록에 표시 | ⏳ 진행중 |
| 유사 민원 패널 | 우측 패널용 유사 민원 응답이 Workbench 포맷과 일치 | ⏳ 진행중 |
| 편집 가능 초안 | 답변/근거/제약사항이 편집 가능한 구조로 제공 | ⏳ 진행중 |
