# Week 6 FE 인터페이스 문서

문서 버전: v1.0-week6-draft  
작성일: 2026-04-10  
책임: FE  
협업: BE3, BE2

---

## 1) 책임 범위

Week 6에서 FE는 `/qa`의 `structured_output.request_segments`를 기준으로 단일/복합 요청 렌더링을 분기하고, topic/complexity/strategy 정보를 화면 전반에 일관 표시한다.

주요 작업:
1. request_segments 기반 UI 분기
2. topic badge + strategy badge 고정
3. fallback UI로 계약 누락 내성 확보

---

## 2) 입력 계약 (BE3 -> FE)

### 2.1 QAResponse.data 필수 필드
- `strategy_id`
- `route_key`
- `routing_trace`
- `structured_output`
- `answer`
- `citations`
- `limitations`
- `latency_ms`
- `quality_signals`

### 2.2 StructuredOutput 필수 키
- `summary: string`
- `action_items: string[]`
- `request_segments: string[]`

### 2.3 badge 렌더 필수 키
- `routing_trace.topic_type`
- `routing_trace.complexity_level`
- `strategy_id`

---

## 3) 렌더링 분기 계약

### 3.1 단일 요청 렌더 조건
- `request_segments.length <= 1`
- 단일 summary 카드 + action item 리스트 표시

### 3.2 복합 요청 렌더 조건
- `request_segments.length >= 2`
- segment 탭/아코디언 + segment별 요약 블록 표시

### 3.3 fallback 규칙
- `request_segments` 누락 시 빈 배열로 처리
- 빈 배열인 경우 단일 요청 템플릿으로 렌더

---

## 4) Search->QA 상태 전달 계약

필수 상태 키:
- `strategyId`
- `routeKey`
- `routingHint`
- `routingTrace`

검증 규칙:
- `/qa` 요청 시 `routing_hint` 필수
- `routing_hint.route_key === routeKey` 불일치 시 요청 중단 + UI 에러 표시

---

## 5) 상태 UX/에러 계약

상태 4종:
- `loading`: 검색/생성 진행
- `success`: 응답 렌더 완료
- `error`: 검증 실패/서버 실패
- `empty`: 결과 없음

FE 에러 분류:
- `VALIDATION_ERROR`
- `ROUTING_INCONSISTENT`
- `NETWORK_ERROR`
- `RENDER_FALLBACK_APPLIED` (경고)

---

## 6) 핸드오프

BE3로 전달:
- `structured_output` 누락/빈 값 렌더 재현 로그
- segment 분기 UI 스냅샷

BE2로 전달:
- route_key별 사용자 표시 문구 검토 피드백

완료 체크:
- 단일/복합 모두 화면 끊김 없이 렌더
- badge 및 strategy 정보가 동일 위치에서 일관 표시
