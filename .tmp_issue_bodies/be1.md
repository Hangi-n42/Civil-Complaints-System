## 배경
BE2 라우팅이 길이/복합요청 중심에서 complexity 기반으로 변경됨에 따라, BE1은 FastAPI 파이프라인에서 Router 입력 메타데이터를 complexity 기준으로 안정 공급해야 한다.

## 작업 범위
- ComplexityAnalyzer 연동용 입력 어댑터 구현
- Analyzer 출력 필수 키 정렬: topic_type, complexity_level, complexity_score
- Router 호출 계약 정렬: route(topic_type, complexity_level, complexity_score)
- /search 파이프라인 전달 및 로깅 정렬
- length_bucket/is_multi/request_segments는 라우팅 필수 입력에서 제외(필요 시 telemetry 용도)

## DoD
- 동일 입력 텍스트에 대해 동일 complexity_level/complexity_score 산출
- /search 라우팅 전 단계에서 Analyzer 출력이 정상 생성되어 Router로 전달
- /search routing_trace에 complexity_level, complexity_score 포함
- route_key 포맷이 {topic_type}/{complexity_level} 규칙과 일치
- Analyzer/Router 계약 키가 스펙과 일치

## 참조
- docs/50_issues/week5/task_02_be1_length_analyzer.md
- docs/60_specs/data_schema_spec.md
- docs/60_specs/api_interface_spec.md
- docs/60_specs/ui_workbench_spec.md
