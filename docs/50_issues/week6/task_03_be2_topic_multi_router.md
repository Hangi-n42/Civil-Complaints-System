### [W6-BE2-03] [BE2] Week 6 핵심 태스크: Topic-aware Retrieval 분기 및 Trace 확장

- **Assignee**: BE2 - 민건
- **목표**: `topic_type + complexity_level` 기반 라우팅을 유지하면서, 주제별 retrieval 정책과 복합 요청 처리 경로를 확장해 검색 결과의 일관성과 설명 가능성을 높인다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/wbs_8weeks_v2_updated.md`

- **작업 상세 내용 (Technical Spec)**:
  1. topic_type별 retrieval 분기 정책 구현
     - `field_ops`: 현장/절차 중심 필드 가중
     - `admin_policy`: 규정/행정 기준 필드 가중
     - 기본 정책(`general`) fallback 유지
  2. route_key 기반 전략 확장
     - `route_key`: `{topic_type}/{complexity_level}`
     - `strategy_id`는 topic + complexity 조합별 버전 키로 고정
  3. 복합 요청(segment) 검색 처리
     - `request_segments`가 2개 이상인 경우 segment별 후보 검색 후 병합 규칙 적용
     - 병합 시 중복 제거, 점수 정규화, 최대 문서 수 제한 적용
  4. retrieval trace 확장
     - 필수 포함:
       - `route_key`
       - `strategy_id`
       - `applied_filters`
       - `segment_count`
       - `merge_policy`
  5. 성능/관측 필드 정렬
     - `latency_ms.retrieval` 측정 유지
     - 로그 키: `route_key`, `applied_filters`, `top_k`, `chunk_policy`

- **완료 기준 (DoD)**:
  - topic_type별로 상이한 retrieval 필터/가중치가 실제 적용된다.
  - 복합 요청에서 segment 기반 검색 병합 결과가 반환된다.
  - `/search` 및 `/qa`에서 동일 `route_key`, `strategy_id`가 유지된다.
  - retrieval trace에 `route_key`, `applied_filters`가 항상 포함된다.
