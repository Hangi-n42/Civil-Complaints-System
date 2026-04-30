### [W7-FE-01] [FE] Week 7 핵심 태스크: 3단 Workbench E2E 통합 및 상태 UX 고정

- **Assignee**: FE - 도훈
- **목표**: Week 5-6에서 고정된 adaptive 계약을 기반으로, 좌/중/우 3단 Workbench를 단일 화면에서 관통시키고 답변 초안 편집까지 가능한 E2E UI 흐름을 완성한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/wbs_8weeks_v2_updated.md`

- **작업 상세 내용 (Technical Spec)**:
  1. 3단 Workbench 레이아웃 구현
     - 좌측: 민원 선택/워크벤치/관리자 대시보드 네비게이션
     - 중앙: 실시간 민원 목록/상태 관리
     - 우측: AI 패널(요약/유사 민원/답변 초안/근거/제약사항)
  2. 중앙-우측 상태 연결 고정
     - 민원 선택 시 중앙 목록의 선택 상태와 우측 패널 컨텍스트를 동기화
     - 라우팅 정보(`strategy_id`, `route_key`, `routing_trace`)를 패널 상단에 유지
  3. 답변 초안 편집 UI 구현
     - `summary`, `action_items`, `citations`, `limitations` 편집/재렌더 흐름 제공
     - 수정 전/후 비교 가능한 편집 영역 구성
  4. 상태 UX 4종 통일
     - `loading`, `success`, `error`, `empty`를 좌/중/우 공통 정책으로 적용
     - API 실패 시 패널별 fallback 메시지와 재시도 버튼 제공
  5. 시연 동선 고정
     - 선택 -> 요약 확인 -> 유사 민원 확인 -> 답변 초안 편집 -> 검토 완료 순서로 UX 고정

- **완료 기준 (DoD)**:
  - 단일 민원 선택 후 좌/중/우 패널이 끊기지 않고 연속 동작한다.
  - 우측 패널에서 답변 초안, citation, limitations가 모두 표시되고 편집 가능하다.
  - 상태 UX 4종이 각 패널에서 동일한 기준으로 동작한다.
  - 시연 동선이 문서화된 순서대로 재현 가능하다.
