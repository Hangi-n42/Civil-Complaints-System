# PublicAgencyInsight 정책

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/complaint_intelligence/public_insights/service.py`
  - `app/complaint_intelligence/public_insights/evidence_pack.py`
  - `app/complaint_intelligence/public_insights/aspect_extractor.py`
  - `app/complaint_intelligence/public_insights/grounding_verifier.py`
  - `app/complaint_intelligence/public_insights/quality_gate.py`
  - `app/complaint_intelligence/schemas.py`
- 관련 문서:
  - `docs/10_contracts/data/current_data_contract.md`
  - `docs/50_issues/complaint_intelligence_local_llm_operations.md`

## 목적

PublicAgencyInsight는 공공기관 담당자가 민원 데이터를 보고 실행할 수 있는 행정 조치와 서비스 개선 방향을 제안합니다.

나쁜 방향:

- “검색 품질을 개선하세요”
- “프롬프트를 수정하세요”
- “RAG dataset을 보강하세요”

좋은 방향:

- “해당 지역 도로 침하 민원이 급증했으므로 현장 점검과 안전 안내를 우선 수행하세요.”
- “복지 신청 절차와 지원 기준 문의가 반복되므로 체크리스트와 자가진단 안내를 보강하세요.”

## 생성 흐름

```text
ComplaintIntelligenceEvent[]
  -> PublicInsightCandidate
  -> EvidencePack
  -> aspect/request 집계
  -> LLM draft 또는 fallback template
  -> GroundingVerifier
  -> QualityGate/Ranker
  -> PublicAgencyInsight
```

## 구조화 4요소 재사용

기존 structuring pipeline의 4요소를 우선 사용합니다.

- observation: aspect와 problem diagnosis 근거
- result: 피해/영향/처리 상태 근거
- request: citizen request seed
- context: 지역/시간/상황/반복 패턴 근거

masked text 규칙 기반 추출은 4요소가 부족할 때 fallback으로 사용합니다.

## EvidencePack 원칙

- LLM에는 원본 DB나 raw complaint body를 직접 전달하지 않습니다.
- EvidencePack은 LLM의 유일한 근거 입력입니다.
- representative complaints는 masked text와 structured elements만 포함합니다.
- `valid_evidence_ids`를 통해 action evidence id를 제한합니다.

## GroundingVerifier/QualityGate

검증 항목:

- schema validity
- evidence id validity
- action evidence coverage
- PII safety
- forbidden AI-ops term
- unsupported numeric claim
- human review requirement
- minimum grounding/confidence/actionability
- action type rubric

검증 기준을 완화해서 LLM 성공률을 높이면 안 됩니다.

## fallback 정책

LLM parse/schema/grounding/quality gate 실패 시 fallback template을 사용할 수 있습니다. fallback이 사용되면 uncertainty나 metrics에 이유가 남아야 합니다.

## human review

다음 유형은 human review가 필요할 가능성이 높습니다.

- 안전 위험
- hotspot 즉시 대응
- 정책 개선
- 처리 지연/업무 병목
- 재민원/반복 민원
- 단속 우선순위

단, 모든 insight를 무조건 human review로 만들지는 않습니다.
