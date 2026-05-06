### [W7-BE1-02] [BE1] Week 7 핵심 태스크: Workbench 중앙 목록용 구조화/분류 요약 필드 제공

- **Assignee**: BE1 - 현기
- **목표**: Workbench 중앙 민원 목록에서 담당자가 빠르게 상태와 분류를 확인할 수 있도록 구조화/분류 요약 필드를 안정적으로 제공한다.
- **참고 Spec**:
  - `docs/60_specs/data_schema_spec.md`
  - `docs/00_overview/prd.md`
  - `docs/00_overview/wbs_8weeks_v2_updated.md`

- **작업 상세 내용 (Technical Spec)**:
  1. Workbench list summary 계약 고정
     - 중앙 목록 항목에 아래 필드 제공
       - `complaint_id`
       - `title`
       - `status`
       - `topic_type`
       - `complexity_level`
       - `complexity_score`
  2. 구조화 요약 파생 필드 제공
     - 목록 표시용 짧은 설명 문구 생성
     - request_segments 기반 대표 요약 1개 제공
  3. 선택 민원 컨텍스트 제공
     - FE가 우측 패널에 바로 전달할 수 있도록 선택 항목 메타데이터 정리
     - `routing_trace` 요약은 표시용, 핵심 값은 그대로 전달
  4. 데이터 정합성 검증
     - `complaint_id` 기준으로 목록-상세-패널이 일치해야 함
     - 누락 필드 발생 시 명시적 validation 에러 반환
  5. 중앙 목록 응답 안정화
     - empty 상태에서도 목록 구조는 유지하고 빈 결과 메타만 반환

- **완료 기준 (DoD)**:
  - 중앙 민원 목록에서 상태와 분류 정보가 한눈에 보인다.
  - FE가 별도 변환 없이 선택 민원 정보를 우측 패널로 넘길 수 있다.
  - 목록 응답의 필수 필드 누락이 없다.
  - empty 상태에서도 Workbench 중앙 영역이 무너 지지 않는다.
