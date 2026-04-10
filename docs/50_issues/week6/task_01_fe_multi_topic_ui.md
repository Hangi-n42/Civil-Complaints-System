### [W6-FE-01] [FE] Week 6 핵심 태스크: 단일/복합 요청 UI 분기 및 라우팅 배지 고정

- **Assignee**: FE - 도훈
- **목표**: `/qa` 응답의 `structured_output.request_segments`를 기준으로 단일/복합 요청 렌더링을 분기하고, Workbench 전 화면에서 `topic`/`strategy` 정보를 일관 표시한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`

- **작업 상세 내용 (Technical Spec)**:
  1. 요청 유형 렌더링 분기 구현
     - 기준: `structured_output.request_segments.length`
     - 단일 요청: 단일 요약/액션 아이템 카드 렌더
     - 복합 요청: segment 단위 탭/아코디언 렌더
  2. 우측 AI 패널 데이터 바인딩 고정
     - 필수 표시:
       - `topic_type` badge
       - `complexity_level` badge
       - `strategy_id` badge
       - `route_key`
  3. Search -> QA 상태 연결 강화
     - `/search`의 `routing_hint`, `strategy_id`, `route_key`를 상태 저장 후 `/qa` 호출에 재사용
     - 화면 재진입/민원 전환 시 상태 초기화 규칙 명시
  4. 응답 스키마 기반 타입 정합
     - TypeScript 타입을 `RoutingTrace`, `RoutingHint`, `StructuredOutput` 계약과 일치
     - `request_segments` 미존재/빈 배열 대응 fallback UI 추가
  5. 상태 UX 통일(Week6 범위)
     - `loading`, `success`, `error`, `empty` 상태를 segment 분기 UI까지 동일 정책 적용

- **완료 기준 (DoD)**:
  - 단일/복합 질의 모두에서 `request_segments` 기준 UI 분기가 정상 동작한다.
  - 우측 패널에서 `topic_type`, `complexity_level`, `strategy_id`, `route_key`가 항상 확인된다.
  - `/search` 단계의 `routing_hint`가 `/qa` 요청으로 누락 없이 전달된다.
  - 응답 일부 누락 상황에서도 화면이 중단되지 않고 fallback UI가 표시된다.
