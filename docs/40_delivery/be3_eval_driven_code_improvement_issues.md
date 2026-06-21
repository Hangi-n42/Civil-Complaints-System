# BE3 평가 기반 코드 개선 이슈 분리안

기준 산출물:

- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/civil_llm_rubric_summary.md`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/ares_llm_reassessment_followup_update.md`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/followup_human_review_manual_findings.md`
- `logs/evaluation/week11/be3_model_benchmark_exaone_rand100_direct_new_rubric_v2_20260619/rand100_ares_rubric_comparison_20260620.md`

## Issue 1. Retrieval/Router 의미 일치 강화

### 배경

LLM-Rubric과 ARES 재평가에서 context relevance가 낮거나, 민원과 다른 유사 사례가 답변 결론으로 섞이는 사례가 확인됐다. 특히 키워드가 겹치지만 실제 처리 쟁점이 다른 context가 상위에 올 때 결론 반전과 사례 오답이 발생한다.

### 작업

- PromptFactory auto-retrieve 결과에 `semantic_match_score`를 부여한다.
- `derived_query`, `request_segments`, `query_signals` 기준으로 context를 재정렬한다.
- PromptFactory 기본 경로에서는 기존 `top_k` 개수를 보존하되, 의미 점수 기준으로 재정렬하고 `routing_trace.semantic_context_rerank`에 진단값을 남긴다.
- 실험/후속 개선에서는 같은 유틸의 threshold 옵션으로 명백히 관련도가 낮은 context tail 제거를 적용할 수 있다.

### 완료 기준

- benchmark 결과 row에 `semantic_context_rerank`가 남는다.
- prompt에 들어가는 context 순서가 민원 쟁점과 더 직접적인 순서로 정렬되고, 기존 평가 조건의 context 개수는 보존된다.
- context relevance 저점 사례가 후속 ARES 평가에서 감소한다.

## Issue 2. 권한 초과·확정 표현 차단

### 배경

사람 검토에서 설치, 철거, 보수, 개방, 예산 확보, 일정 확정 등 행정기관 권한을 넘는 확약 표현이 발견됐다. 근거가 불충분한 상태에서 `확인하였습니다`, `완료되었습니다`, `예정입니다` 같은 표현도 위험하다.

### 작업

- 생성 결과에 unsupported commitment detector를 적용한다.
- 위험 표현은 `현장 여건, 소관 권한 및 관련 기준 확인 후 처리 가능 여부 검토` 형태로 완화한다.
- `generation_metadata`와 benchmark row에 `unsupported_commitment_count`, `unsupported_commitments`를 기록한다.

### 완료 기준

- API `/qa`와 direct benchmark 모두 동일한 완화 로직을 적용한다.
- `unsupported_commitment_count > 0`이면 Prometheus 재작성 후보로 들어간다.
- 후속 사람 검토에서 권한 초과 확약 빈도가 감소한다.

## Issue 3. Citation semantic support 검증 강화

### 배경

기존 strict citation match는 `chunk_id/case_id` 정합성에는 강하지만, citation snippet이 답변 주장 자체를 충분히 뒷받침하는지는 약하게 본다.

### 작업

- 답변 본문, citation snippet, retrieval context 간 의미 토큰 overlap 기반 `citation_semantic_support_rate`를 산출한다.
- `citation_semantic_support_rate`가 낮으면 루브릭/Prometheus 재작성 조건에 포함한다.
- 기존 `citation_match_rate`는 호환성을 위해 유지한다.

### 완료 기준

- benchmark row에 `citation_semantic_support_rate`가 추가된다.
- Civil LLM-Rubric 입력의 `quality_signals`에 semantic citation support가 포함된다.
- citation id는 맞지만 근거 연결이 약한 사례가 별도 진단된다.

## Issue 4. 복합 민원 segment 누락 개선

### 배경

복합 민원에서 일부 요청만 답하거나, 생성 답변이 특정 segment를 건너뛰는 사례가 있었다. ARES answer relevance의 missing segment 진단과 수동 검토 결과가 이 문제를 공통으로 지적했다.

### 작업

- `routing_trace.request_segments` 기준으로 `segment_coverage_rate`를 산출한다.
- segment coverage가 1.0 미만이면 quality low item으로 추가한다.
- Prometheus 재작성 시 누락 segment를 보완하도록 feedback에 포함한다.

### 완료 기준

- benchmark row와 API `quality_signals`에 `segment_coverage_rate`가 기록된다.
- 복합 민원에서 segment 누락이 후속 평가에서 감소한다.

## Issue 5. ARES LLM 평가 운영 최적화

### 배경

ARES가 rule 기반에서 LLM judge 기반으로 전환되면서 진단력은 개선됐지만, rand100 이상 전체 평가에서는 실행 시간이 길고 중단 후 재개가 필요하다.

### 작업

- `scripts/evaluate_ares_lite_civil_replies.py`에 `--start-index`를 추가해 중단 지점 이후부터 재평가할 수 있게 한다.
- 기존 `--max-cases`, `--max-contexts`, `--use-rule-fallback`과 함께 sample/full 평가를 분리 운영한다.
- 통합 judge는 추후 과제로 두되, 현재는 context relevance, faithfulness, answer relevance 3축 분리 평가를 유지한다.

### 완료 기준

- 중단된 평가를 `--start-index N`으로 이어 실행할 수 있다.
- full 평가 전 sample 평가로 비용을 제어할 수 있다.
- 후속 보고서에서 LLM judge와 rule fallback 분포가 분리 기록된다.
