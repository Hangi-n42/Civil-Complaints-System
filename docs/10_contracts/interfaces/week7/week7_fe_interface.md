# Week 7 FE 인터페이스 문서

문서 버전: v1.0-week7-draft  
작성일: 2026-05-01  
책임: FE  
협업: BE1, BE2, BE3

---

## 1) 책임 범위

Week 7에서 FE는 3단 Workbench를 단일 페이지에서 고정하고, 중앙 목록과 우측 AI 패널을 동시에 제어하는 상태 계약을 구현한다.

주요 작업:
1. 좌/중/우 3단 Workbench 레이아웃 고정
2. 상태 UX 통일
3. 답변 초안 편집 UI 제공

---

## 2) 입력 계약

### 2.1 중앙 목록 입력
- `ComplaintWorkbenchItem[]`

### 2.2 우측 패널 입력
- `SimilarComplaintPanelItem[]`
- `DraftAnswerPayload`
- `routing_trace`

### 2.3 공통 표시 키
- `strategy_id`
- `route_key`
- `topic_type`
- `complexity_level`
- `status`

---

## 3) 레이아웃 계약

### 3.1 좌측 패널
- 네비게이션
- 워크벤치 진입 상태
- 관리자 대시보드 진입 링크

### 3.2 중앙 패널
- 민원 목록
- 상태 태그
- 분류/복잡도 요약

### 3.3 우측 패널
- 요약
- 유사 민원
- 답변 초안 편집
- citation
- limitations

---

## 4) 상태 계약

상태 4종:
- `loading`
- `success`
- `error`
- `empty`

상태별 규칙:
- loading: skeleton 또는 spinner 표시
- success: 패널별 데이터 렌더
- error: 패널별 오류 메시지와 재시도 버튼 표시
- empty: empty copy와 빈 상태 레이아웃 유지

---

## 5) 편집 계약

### 5.1 editable fields
- `answer`
- `structured_output.summary`
- `structured_output.action_items`

### 5.2 read-only fields
- `citations`
- `routing_trace`
- `route_key`
- `strategy_id`

### 5.3 interaction rules
- 편집 후 저장 전에는 원본/수정본 분리 표시
- citation은 선택 강조만 허용
- limitations는 배지/목록 형태로 유지

---

## 6) FE -> BE 계약

### 6.1 선택 민원 전송
- `complaint_id`
- `route_key`
- `strategy_id`
- `routing_hint`

### 6.2 편집 반영 저장 요청
- `answer`
- `structured_output`
- `edited_at`
- `operator_id`

---

## 7) 오류 계약

Week 7 FE 에러 코드:
- `WORKBENCH_LAYOUT_ERROR`
- `PANEL_DATA_MISSING`
- `EDIT_STATE_CONFLICT`
- `ROUTING_CONTEXT_LOST`

---

## 8) 핸드오프

BE1로 전달:
- 중앙 목록에 노출되는 summary 필드 요구사항

BE2로 전달:
- 유사 민원 카드에 필요한 표시 필드

BE3로 전달:
- 편집 가능한 answer/citation/limitations 화면 요구사항

완료 체크:
- 좌/중/우 패널이 단일 라우팅 상태를 공유한다
- 편집 UI가 패널 렌더를 깨지 않는다
