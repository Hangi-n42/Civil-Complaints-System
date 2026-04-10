### [W6-BE1-02] [BE1] Week 6 핵심 태스크: Topic/Complexity Analyzer 통합 출력 고정

- **Assignee**: BE1 - 현기
- **목표**: Topic + Complexity 분석 결과를 단일 계약(`AnalyzerOutput`)으로 통합해 BE2 Router 및 BE3 Generation 단계에서 동일 입력 스키마를 사용하도록 고정한다.
- **참고 Spec**:
  - `docs/60_specs/data_schema_spec.md`
  - `docs/60_specs/api_interface_spec.md`
  - `docs/00_overview/wbs_8weeks_v2_updated.md`

- **작업 상세 내용 (Technical Spec)**:
  1. `TopicAnalyzer.classify(text, category, entity_labels)` 구현
     - 출력: `topic_type`, `topic_confidence`
     - category/entity_labels 미제공 시 fallback 분류 규칙 정의
  2. `ComplexityAnalyzer.analyze(text, topic_type)` 구현/정렬
     - 출력: `complexity_level`, `complexity_score`, `complexity_trace`
     - `topic_type`를 반영한 도메인 가중치 규칙 적용
  3. 통합 출력 어댑터 구현
     - 시그니처: `build_analyzer_output(text, category, entity_labels) -> AnalyzerOutput`
     - 최종 키:
       - `topic_type`
       - `complexity_level`
       - `complexity_score`
       - `complexity_trace`
       - `request_segments`
  4. 요청 분할(request segmentation) 고정
     - 복합 민원 분리 규칙을 `request_segments`로 표준화
     - 빈 분할 방지: 최소 1개 segment 보장
  5. 관측 및 계약 검증
     - analyzer 로그: `topic_type`, `complexity_level`, `complexity_score`, `segment_count`
     - 응답 직전 계약 검증으로 필수 키 누락 시 명시적 에러 반환

- **완료 기준 (DoD)**:
  - Analyzer 출력이 `{topic_type, complexity_level, complexity_score, complexity_trace, request_segments}`로 일관 생성된다.
  - 동일 입력에 대해 topic/complexity 결과가 재현 가능하게 산출된다.
  - `request_segments`가 단일/복합 입력 모두에서 유효 배열로 반환된다.
  - BE2/BE3가 추가 변환 없이 통합 analyzer 출력을 직접 소비할 수 있다.
