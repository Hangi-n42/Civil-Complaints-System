### [W5-BE2-03] [BE2] Week 5 핵심 태스크: AdaptiveRouter 1차 구현 (Complexity 기반)

- **Assignee**: BE2 - 민건
- **목표**: `topic_type`은 유지하되, `length_bucket`/`is_multi` 중심 분기 대신 **복잡도 기반 지표**로 라우팅 정확도를 높인다. `AdaptiveRouter`가 `topic_type + complexity_level` 기준으로 검색 전략을 선택하도록 구현한다.
- **참고 Spec**:
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`

- **작업 상세 내용 (Technical Spec)**:
  1. `app/retrieval/analyzers/complexity_analyzer.py` 신규 구현
     - 시그니처: `analyze(text: str, topic_type: str) -> ComplexityAnalysis`
     - 출력 필드:
       - `complexity_score` (0.0~1.0)
       - `complexity_level` (`low | medium | high`)
       - `intent_count`
       - `constraint_count`
       - `entity_diversity`
       - `policy_reference_count`
       - `complexity_trace`
  2. `app/retrieval/router/adaptive_router.py`의 라우팅 시그니처 변경
     - 기존: `route(length_bucket, topic_type, is_multi)`
     - 변경: `route(topic_type: str, complexity_level: str, complexity_score: float) -> RoutingDecision`
  3. 전략 키/전략 매핑 변경
     - `route_key`: `{topic_type}/{complexity_level}`
     - `strategy_id` 예시:
       - `topic_welfare_low_v1`
       - `topic_welfare_medium_v1`
       - `topic_welfare_high_v1`
  4. complexity별 retrieval 파라미터 적용
     - low: `top_k=4`, `snippet_max_chars=400`, `chunk_policy=compact`
     - medium: `top_k=6`, `snippet_max_chars=700`, `chunk_policy=balanced`
     - high: `top_k=9`, `snippet_max_chars=1100`, `chunk_policy=expanded`
  5. trace/관측 로깅 강화
     - 로그 키:
       - `route_key`, `strategy_id`
       - `complexity_level`, `complexity_score`
       - `router_latency`, `applied_params`

- **완료 기준 (DoD)**:
  - 동일 입력 텍스트에 대해 동일 `complexity_level`, `route_key`, `strategy_id`가 결정된다.
  - `route_key={topic_type}/{complexity_level}` 포맷이 `/search`와 `/qa`에서 일관 유지된다.
  - `/search` 응답의 `routing_trace`에 `complexity_level`, `complexity_score`가 포함된다.
  - 기존 `length_bucket`/`is_multi` 미사용 상태에서도 라우팅 설명(`route_reason`)이 UI에서 이해 가능하게 노출된다.

  - **구현 결과**:
    - `ComplexityAnalyzer`와 `AdaptiveRouter`를 신규 모듈로 분리했다.
    - `/search`는 analyzer 결과를 router에 전달해 `route_key`, `strategy_id`, `routing_hint`, `routing_trace`를 생성한다.
    - `/qa`는 동일한 `route_key` 규칙을 공유하고, `routing_trace`가 전달되면 우선 계승한다.
    - `route_reason`은 복잡도와 적용 파라미터를 포함하는 사용자 설명 문장으로 노출된다.
    - 로그에 `route_key`, `strategy_id`, `complexity_level`, `complexity_score`, `router_latency`, `applied_params`를 추가했다.

  - **편차**:
    - `index` 엔드포인트는 문서 검색 라우팅 대상이 아니므로 적용 범위에서 제외했다.