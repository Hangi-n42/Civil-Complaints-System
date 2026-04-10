### [W5-BE3-04] [BE3] Week 5 핵심 태스크: /search routing_trace 통합 및 /qa 파이프라인 준비

- **Assignee**: BE3 - 현석
- **목표**: `/search` 응답에 `routing_trace`를 계약대로 통합하고, `/qa`가 `routing_hint`를 수신·유지하는 경로를 선연결해 Week6 generation 통합의 기반을 완성한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`

- **작업 상세 내용 (Technical Spec)**:
  1. `/search` 응답 스키마 업데이트
     - 필수 포함:
       - `strategy_id`
       - `route_key`
       - `routing_trace`
       - `routing_hint`
       - `retrieved_docs[].metadata.strategy_id`
  2. `/qa` 요청 스키마 업데이트
     - 필수 입력: `routing_hint`
     - `routing_hint.strategy_id`, `routing_hint.route_key` 유효성 검증 추가
  3. `/qa` 응답 기본 골격 준비
     - 필수 포함:
       - `routing_trace`
       - `structured_output` (초기 placeholder 허용)
       - `answer`
       - `citations`
       - `limitations`
  4. search→qa 전달 경로 유지
     - `/search`에서 생성된 `strategy_id/route_key`가 `/qa`에서도 동일하게 유지되도록 파이프라인 연결
  5. FastAPI 공통 래퍼 정합
     - 성공/실패 응답을 `success/request_id/timestamp/data|error` 형태로 통일
  6. 관측 필드 뼈대 추가
     - `/qa` 응답에 `latency_ms`, `quality_signals` 구조 키를 포함할 준비 코드 반영

- **완료 기준 (DoD)**:
  - `/search` 응답에서 `routing_trace`를 FE가 즉시 렌더 가능한 형태로 확인할 수 있다.
  - `/qa` 요청에 `routing_hint` 누락 시 명시적 검증 에러가 반환된다.
  - 동일 요청 흐름에서 `/search.strategy_id`와 `/qa.strategy_id`가 일치한다.
  - `/qa` 응답 골격이 `routing_trace`, `structured_output`, `answer`, `citations`, `limitations`를 포함한다.