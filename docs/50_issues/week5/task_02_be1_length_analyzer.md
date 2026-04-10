### [W5-BE1-02] [BE1] Week 5 핵심 태스크: Complexity Analyzer 입력 어댑터 정렬

- **Assignee**: BE1 - 현기
- **목표**: BE2의 AdaptiveRouter가 `topic_type + complexity_level` 기준으로 분기하도록 변경됨에 따라, FastAPI 파이프라인에서 복잡도 기반 Analyzer 메타데이터를 안정 공급한다. 기존 `length_bucket`/`is_multi`는 라우팅 필수 입력에서 제외한다.
- **참고 Spec**:
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/ui_workbench_spec.md`

- **작업 상세 내용 (Technical Spec)**:
  1. BE2 `ComplexityAnalyzer` 연동용 입력 어댑터 구현
     - 시그니처: `build_analyzer_output(text: str, topic_type: str) -> AnalyzerOutput`
     - BE2 analyzer 호출 기준:
       - `analyze(text: str, topic_type: str) -> ComplexityAnalysis`
     - 반환 필드(라우팅 필수):
       - `topic_type`
       - `complexity_level` (`low | medium | high`)
       - `complexity_score` (0.0~1.0)
  2. 라우터 입력 계약 정렬
     - AdaptiveRouter 호출 시그니처와 동일하게 전달:
       - `route(topic_type: str, complexity_level: str, complexity_score: float)`
     - `route_key` 생성 입력은 `{topic_type}/{complexity_level}` 기준으로 고정
  3. `/search` 파이프라인 연결
     - `/search` 처리 시 analyzer 출력을 Router 입력으로 전달
     - 라우팅 trace 전달 필드:
       - `complexity_level`, `complexity_score`
     - 로깅 필드:
       - `analyzer_latency`, `complexity_level`, `complexity_score`
  4. 기존 길이/복합요청 지표 처리 방침
     - `length_bucket`, `is_multi`, `request_segments`는 라우팅 결정의 필수 입력에서 제외
     - 필요 시 관측(telemetry) 용도로만 유지 가능하나, 라우팅 분기 조건으로 사용 금지
  5. 계약 키 정합성 고정
     - 라우팅 관련 키: `topic_type`, `complexity_level`, `complexity_score` 키명 변경 금지

- **완료 기준 (DoD)**:
   - 동일 입력 텍스트에 대해 동일 `complexity_level`, `complexity_score`가 산출되어 Router로 전달된다.
   - `/search` 내부 라우팅 전 단계에서 Analyzer 출력이 정상 생성되어 `route(topic_type, complexity_level, complexity_score)` 호출로 연결된다.
   - `/search` 응답의 `routing_trace`에 `complexity_level`, `complexity_score`가 포함된다.
   - `route_key={topic_type}/{complexity_level}` 포맷이 BE2 라우터 규칙과 일치한다.
   - Analyzer/Router 계약 키가 `docs/60_specs/data_schema_spec.md`와 일치한다.