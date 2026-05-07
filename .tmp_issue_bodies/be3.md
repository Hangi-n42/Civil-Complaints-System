## 배경
/search 결과에 routing_trace를 계약대로 통합하고, /qa가 routing_hint를 수신/유지하도록 선연결하여 Week6 generation 통합 기반을 마련한다.

## 작업 범위
- /search 응답 스키마 업데이트(strategy_id, route_key, routing_trace, routing_hint, retrieved_docs[].metadata.strategy_id)
- /qa 요청 스키마 업데이트(routing_hint 필수 및 strategy_id/route_key 유효성 검증)
- /qa 응답 골격 준비(routing_trace, structured_output, answer, citations, limitations)
- search→qa 전달 경로에서 strategy_id/route_key 동일성 유지
- FastAPI 공통 래퍼 정합(success/request_id/timestamp/data|error)
- /qa 관측 필드 뼈대(latency_ms, quality_signals)

## DoD
- /search routing_trace가 FE 즉시 렌더 가능한 형태
- /qa 요청에서 routing_hint 누락 시 명시적 검증 에러 반환
- 동일 요청 흐름에서 /search.strategy_id와 /qa.strategy_id 일치
- /qa 응답 골격 필수 필드 포함

## 참조
- docs/50_issues/week5/task_04_be3_search_trace.md
- docs/60_specs/api_interface_spec.md
- docs/60_specs/data_schema_spec.md
- docs/60_specs/ui_workbench_spec.md
