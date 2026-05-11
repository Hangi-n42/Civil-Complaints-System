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

---

## 스펙 경계(중요)

Week6 기준으로 **generation 단계 내부 결과(모델/파서 변형 허용)** 와 **`/api/v1/qa` 최종 응답(unified contract 고정)** 는 계약이 다르다.
프롬프트/파서/서비스는 아래 경계를 넘어서 필드를 섞지 않는다.

### 1) 내부(LLM 파싱) 스키마: `parse_qa_json_response()`

- 목적: 모델 출력(JSON)을 안정적으로 파싱/정규화해서 generation 단계에서 활용
- 허용 변형:
   - `confidence`는 optional (누락 시 기본값 0.5로 정규화)
   - `limitations`는 `string` 또는 `string[]` 허용 (list면 문자열로 조합해 string으로 정규화)

내부 파서 출력 예시:

```json
{
   "answer": "string",
   "citations": [{"chunk_id":"string","case_id":"string","snippet":"string","relevance_score":0.0}],
   "confidence": 0.5,
   "limitations": "string"
}
```

### 2) generation 서비스 결과 스키마: `GenerationService.generate_qa()`

- 목적: 파서 결과 + 컨텍스트 기반 보정을 포함한 generation 단계 결과
- 비고: 내부 결과에는 `model`, `question` 같은 부가 필드가 포함될 수 있으나, 이는 **API unified contract로 노출하지 않는다.**

### 3) API 최종 응답(unified contract): `/api/v1/qa`

- 목적: FE가 안정적으로 렌더링 가능한 고정 스키마
- `normalize_response(payload)`로 아래 필드들을 강제:
   - `routing_trace`, `structured_output`, `answer`, `citations`, `limitations`, `latency_ms`, `quality_signals`
- `limitations`: 항상 `string[]`
- citations: 항상 `{doc_id, source, quote}`
- 내부 필드(`confidence`, `model`, `question`)는 `/api/v1/qa` `data`에 포함하지 않는다.

### 4) 매핑 규칙(요약)

| 단계 | 입력 필드 | 최종(`/qa data`) 필드 | 규칙 |
|---|---|---|---|
| LLM 파싱 | `limitations: string | string[]` | `limitations: string[]` | `normalize_response`가 list로 강제 |
| LLM 파싱 | `citations[].snippet` | `citations[].quote` | `/qa` 라우터에서 snippet → quote로 변환 |
| LLM 파싱 | `confidence` | (노출 없음) | 내부 품질/디버그 용도(필수 아님) |
| generation 결과 | `model`, `question` | (노출 없음) | API 계약 밖의 내부 메타 |

### 5) 테스트 고정 위치

- 통합 경계 테스트: `app/tests/integration/test_week6_search_to_qa_e2e_sample10.py`
   - 내부 generation 결과 변형(limitations string/list, confidence optional)에도 `/qa` unified contract 유지
