## 배경
AdaptiveRouter의 분기를 길이 기반이 아닌 complexity 기반으로 전환하여 라우팅 정확도와 설명 가능성을 높인다.

## 작업 범위
- complexity_analyzer 신규 구현
- 라우팅 시그니처 변경: route(topic_type, complexity_level, complexity_score)
- 전략 키/전략 매핑 변경: route_key={topic_type}/{complexity_level}
- complexity 수준별 retrieval 파라미터 적용
- trace/관측 로깅 강화(route_key, strategy_id, complexity_level, complexity_score, router_latency, applied_params)

## DoD
- 동일 입력에 대해 동일 complexity_level/route_key/strategy_id 결정
- route_key 포맷이 /search와 /qa에서 일관 유지
- /search routing_trace에 complexity_level, complexity_score 포함
- length_bucket/is_multi 미사용 상태에서도 route_reason이 UI에서 이해 가능

## 참조
- docs/50_issues/week5/task_03_be2_adaptive_router.md
- docs/60_specs/data_schema_spec.md
- docs/60_specs/api_interface_spec.md
- docs/60_specs/ui_workbench_spec.md
