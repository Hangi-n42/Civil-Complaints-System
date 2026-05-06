### [W7-BE2-03] [BE2] Week 7 핵심 태스크: 유사 민원 패널 응답 형식 고정

- **Assignee**: BE2 - 민건
- **목표**: 우측 AI 패널에서 유사 민원 목록을 Workbench 형식으로 고정해, FE가 그대로 렌더링할 수 있는 안정적인 retrieval 응답 계약을 제공한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/dev_stack.md`

- **작업 상세 내용 (Technical Spec)**:
  1. 유사 민원 패널 응답 모델 고정
     - 응답 항목 필드:
       - `doc_id`
       - `title`
       - `snippet`
       - `score`
       - `source`
       - `metadata.strategy_id`
       - `metadata.topic_type`
       - `metadata.complexity_level`
  2. Workbench 전용 응답 포맷 확정
     - FE가 패널 카드/리스트로 바로 렌더 가능한 구조 유지
     - `top_k`와 패널 카드 수를 일치시키는 정책 정의
  3. 선택 민원 컨텍스트와 검색 결과 연결
     - 중앙 목록에서 선택된 민원 기준으로 유사 민원 응답을 재조회 가능해야 함
     - `route_key`와 `strategy_id`를 검색 결과에 일관 표기
  4. 정렬/중복 제거 규칙 고정
     - score 내림차순 정렬
     - 동일 문서 중복 제거
     - summary only 결과와 panel result 구조를 분리하지 않음
  5. observability 최소 세트 유지
     - `retrieval_latency_ms`
     - `result_count`
     - `route_key`

- **완료 기준 (DoD)**:
  - 우측 패널용 유사 민원 응답이 FE에서 변환 없이 렌더된다.
  - 선택 민원 기준으로 동일한 route_key/strategy_id가 유지된다.
  - 중복 문서가 패널에 반복 노출되지 않는다.
  - 검색 결과 수와 패널 카드 수의 정책이 일관된다.
