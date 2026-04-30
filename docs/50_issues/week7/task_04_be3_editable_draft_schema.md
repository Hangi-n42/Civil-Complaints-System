### [W7-BE3-04] [BE3] Week 7 핵심 태스크: 답변 초안/근거/제약사항 편집 가능 스키마 고정

- **Assignee**: BE3 - 현석
- **목표**: `/qa` 응답을 FE 편집 가능 구조로 고정해 답변 초안, 근거(citations), 제약사항(limitations)을 화면에서 수정/검토할 수 있도록 한다.
- **참고 Spec**:
  - `docs/60_specs/api_interface_spec.md`
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/prd.md`

- **작업 상세 내용 (Technical Spec)**:
  1. 답변 초안 스키마 고정
     - `answer`를 편집 가능한 본문으로 제공
     - `structured_output.summary`와 `structured_output.action_items`를 함께 반환
  2. 근거(citations) 편집/표시 계약 고정
     - `doc_id`, `source`, `quote` 구조 유지
     - citation은 읽기 전용, 선택 강조/접기 가능 상태만 허용
  3. 제약사항(limitations) 스키마 고정
     - 문자열 배열 유지
     - FE가 목록/배지 형태로 렌더 가능해야 함
  4. 응답 정규화 계층 적용
     - `normalize_response(payload)` 후 필수 필드 누락 금지
     - `routing_trace`, `structured_output`, `latency_ms`, `quality_signals` 유지
  5. 검증/오류 계약 고정
     - 편집 가능 필드 누락 또는 route 불일치 시 `VALIDATION_ERROR`
     - schema mismatch 시 `RESPONSE_SCHEMA_MISMATCH`

- **완료 기준 (DoD)**:
  - FE가 답변 초안을 수정 가능한 형태로 수신한다.
  - citations와 limitations가 계약대로 분리되어 렌더된다.
  - `/qa` 응답이 unified schema를 유지한다.
  - route_key/strategy_id가 search 단계와 일치한다.
