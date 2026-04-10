### [W5-FE-01] [FE] Week 5 핵심 태스크: Complexity Routing UI 및 3단 Workbench 스캐폴딩

- **Assignee**: FE - 도훈
- **목표**: 검색 단계에서 전달되는 `routing_trace`를 화면에서 설명 가능하게 표시하고, Next.js 3단 워크벤치 기본 레이아웃을 즉시 동작 가능한 형태로 구축한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`
  - `docs/60_specs/data_schema_spec.md`

- **작업 상세 내용 (Technical Spec)**:
  1. Next.js App Router 기준 `web/app/workbench/page.tsx` 생성/정렬
     - 좌: `NavigationSidebar`
     - 중: `ComplaintList`
     - 우: `AIAssistantPanel`
  2. `web/components/case-list/ComplaintListItem` 카드에 아래 필드 렌더링
     - `routing_trace.complexity_level`
     - `routing_trace.complexity_score`
     - `strategy_id`
  3. `/search` 응답 저장 상태 정의
     - `routingTrace`, `routingHint`, `strategyId`, `routeKey`, `retrievedDocs`
  4. `/qa` 호출 시 `routing_hint`를 요청 본문에 반드시 포함
     - 누락 방지용 타입 가드/런타임 체크 추가
  5. 상태 UX 4종 적용
     - `loading`, `success`, `error`, `empty`
  6. 우측 패널에 라우팅 설명 영역 추가
     - `route_key`, `route_reason`, `complexity_trace`를 자연어 문장/근거 패널로 표시

- **완료 기준 (DoD)**:
  - 민원 선택 시 중앙 카드 또는 우측 패널에서 `complexity_level`, `complexity_score`, `strategy_id`가 확인된다.
  - `/search` 결과의 `routing_hint`가 `/qa` 요청으로 그대로 전달된다.
  - 3단 레이아웃(좌/중/우)이 단일 페이지에서 동시에 렌더된다.
  - 검색→QA 전환 중 UI가 중단되지 않고 상태 UX 4종이 일관 동작한다.