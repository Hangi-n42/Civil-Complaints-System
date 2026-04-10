### [W6-BE3-04] [BE3] Week 6 핵심 태스크: PromptFactory 및 Unified Output 정규화

- **Assignee**: BE3 - 현석
- **목표**: 라우팅 정보를 반영한 generation 프롬프트를 표준화하고, `/qa` 응답을 `normalize_response`로 통일해 FE가 안정적으로 렌더링할 수 있는 unified schema를 확정한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/dev_stack.md`

- **작업 상세 내용 (Technical Spec)**:
  1. `PromptFactory.build(query, context, routing_trace)` 구현
     - 입력: 질의, 검색 컨텍스트, `routing_trace`
     - 반영 요소:
       - `topic_type` 기반 도메인 지시문
       - `complexity_level` 기반 답변 깊이/구조 지시문
       - `request_segments` 기반 섹션 분할 지시문
  2. `/qa` generation 파이프라인 통합
     - search 단계 전략(`strategy_id`, `route_key`)을 generation 단계까지 유지
     - `routing_hint` 누락/불일치 시 검증 에러 처리
  3. `normalize_response(payload)` 구현
     - 필수 출력 보장:
       - `routing_trace`
       - `structured_output {summary, action_items, request_segments}`
       - `answer`
       - `citations`
       - `limitations`
       - `latency_ms`
       - `quality_signals`
  4. citation/제약사항 정규화
     - citation 항목을 `doc_id/source/quote` 구조로 고정
     - limitations는 문자열 배열로 강제
  5. 응답 계약 검증 레이어 추가
     - `/qa` 응답 직전 필수 필드 누락 검사
     - 계약 위반 시 `VALIDATION_ERROR` 포맷으로 반환

- **완료 기준 (DoD)**:
  - `/qa`가 topic/multi 입력에 대해 `structured_output + routing_trace`를 일관 반환한다.
  - `PromptFactory`가 `routing_trace`를 반영한 프롬프트를 생성한다.
  - `normalize_response` 이후 응답 스키마가 FE 타입 계약과 일치한다.
  - `citations`, `limitations`, `latency_ms`, `quality_signals`가 계약대로 유지된다.
