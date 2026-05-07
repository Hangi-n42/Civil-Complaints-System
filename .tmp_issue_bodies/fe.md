## 배경
/search에서 전달되는 routing_trace를 사용자에게 설명 가능하게 노출하고, Next.js 3단 Workbench 레이아웃을 즉시 동작 가능한 형태로 구축한다.

## 작업 범위
- web/app/workbench/page.tsx 3단 레이아웃(좌/중/우) 구성
- ComplaintListItem에 complexity_level, complexity_score, strategy_id 렌더링
- /search 응답 상태 정의(routingTrace, routingHint, strategyId, routeKey, retrievedDocs)
- /qa 요청 시 routing_hint 필수 전달(타입가드/런타임 체크)
- 상태 UX 4종(loading/success/error/empty)
- 우측 패널 라우팅 설명 영역(route_key, route_reason, complexity_trace)

## DoD
- 민원 선택 시 complexity_level/complexity_score/strategy_id 확인 가능
- /search의 routing_hint가 /qa 요청으로 그대로 전달
- 3단 레이아웃 단일 페이지 동시 렌더
- 검색→QA 전환 중 상태 UX 4종 일관 동작

## 참조
- docs/50_issues/week5/task_01_fe_length_routing_ui.md
- docs/60_specs/api_interface_spec.md
- docs/60_specs/ui_workbench_spec.md
- docs/60_specs/data_schema_spec.md
