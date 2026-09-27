# 기존 민원 시스템 — 현재 구현 아키텍처

- 문서 상태: 기존 민원 구현 참고 기준; 신규 제품의 주 PRD가 아님
- 문서 버전: v2.0
- 코드 정적 확인·정리일: 2026-09-26
- 기준 코드:
  - `app/api/main.py`
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `app/complaint_intelligence/service.py`
  - `frontend/app/workbench/page.tsx`
  - `frontend/app/intelligence/page.tsx`
- 관련 문서:
  - `docs/10_contracts/api/current_api_contract.md`
  - `docs/20_domains/complaint_intelligence/README.md`
  - `docs/30_manuals/local_dev_runbook.md`

## 전체 경계

```text
원천/가공 민원 데이터
  ├─ ingestion/structuring
  │    └─ observation/result/request/context 4요소, PII-safe structured data
  ├─ RAG/Search/QA 메인 파이프라인
  │    ├─ /api/v1/search
  │    ├─ /api/v1/qa
  │    └─ Workbench UI
  └─ Complaint Intelligence sidecar
       ├─ IssueAlert
       ├─ PublicAgencyInsight
       ├─ Duplicate Merge Recommendation
       ├─ SQLite/InMemory repository
       └─ Intelligence dashboard UI
```

## 메인 RAG/QA 파이프라인

메인 파이프라인은 개별 민원에 대한 검색과 답변 생성을 담당합니다.

```text
query/case
  -> Topic/Complexity/Request Segment 분석
  -> 요청 분석·routing hint/trace
  -> 설정·필터에 따른 ChromaDB/Hybrid retrieval
  -> context mapping
  -> PromptFactory
  -> GenerationService
  -> response normalizer/citation validation
  -> Workbench 표시
```

주요 endpoint:

- `POST /api/v1/search`
- `POST /api/v1/qa`
- `POST /api/v1/qa/stream`

## Complaint Intelligence sidecar

Complaint Intelligence는 RAG/QA 요청 처리 경로에 직접 끼어들지 않는 sidecar입니다. 분석 결과는 repository에 저장되고 FE는 dashboard read-model을 조회합니다.

```text
ComplaintIntelligenceEvent[]
  -> ComplaintIntelligenceService.run_analysis
  -> IssueDetectionEngine
  -> PublicAgencyInsightEngine
  -> EvidencePack 저장
  -> IssueAlert/PublicAgencyInsight 저장
  -> dashboard read-model 조회
```

주요 endpoint:

- `POST /complaint-intelligence/run-analysis`
- `GET /complaint-intelligence/dashboard`
- `POST /complaint-intelligence/dashboard/run-analysis`
- `GET /complaint-intelligence/issue-alerts`
- `GET /complaint-intelligence/public-insights`
- `GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack`

## Duplicate Merge Recommendation Layer

중복 병합 레이어는 유사 민원 묶음을 담당자에게 제안하는 read-model입니다. 실제 민원 DB의 상태를 직접 바꾸지 않습니다.

```text
ComplaintIntelligenceEvent[]
  -> DuplicateCandidateGenerator
  -> scoring + MergeVerifier
  -> DuplicateMergeRecord(candidate)
  -> 담당자 action: confirm/split/reject
  -> confirmed에서만 draft-reply 또는 reply-draft 허용
```

핵심 원칙:

- blocker risk가 있으면 confirm과 draft reply를 막습니다.
- candidate는 제안 상태일 뿐 실제 병합이 아닙니다.
- confirmed도 내부 read-model 상태이며 자동 발송이 아닙니다.

## FE Intelligence Dashboard

`frontend/app/intelligence/page.tsx`는 다음 데이터를 함께 사용합니다.

- dashboard summary
- issue alert cards
- public insight cards
- duplicate group triage
- hotspot map
- evidence pack drawer

FE는 LLM을 직접 호출하지 않습니다. 저장된 read-model을 조회하고, 필요한 담당자 action만 API로 요청합니다.

## 저장소

Complaint Intelligence repository는 interface로 분리되어 있습니다.

- `InMemoryComplaintIntelligenceRepository`: 테스트/개발 fallback
- `SQLiteComplaintIntelligenceRepository`: 로컬 demo/운영 준비용 기본 영속 저장소

향후 Postgres 같은 운영 DB로 전환할 때는 repository interface를 기준으로 교체합니다.

## 평가와 replay

- demo seed: `data/demo/complaint_intelligence_demo_events.json`
- real replay seed: `data/complaint_intelligence/complaint_intelligence_real_replay_events.json`
- duplicate merge demo: `data/complaint_intelligence/duplicate_merge_demo_events.json`
- curated evaluation: `data/evaluation/complaint_intelligence_eval_scenarios.json`
- holdout: `data/evaluation/complaint_intelligence_holdout_50.json`

평가 결과는 `reports/`에 저장합니다. PR에는 최종 리포트 중심으로 포함하고, raw response/prompt/checkpoint는 포함하지 않는 것이 기본 원칙입니다.

## 2026-09-26 구현 확인 사항

신규 제품 설계는 [회사 지식 아키텍처](../05_plans/company_knowledge/architecture.md)를 따른다. 이 문서의 메인 파이프라인은 기존 민원 기능 내부의 주 경로를 뜻한다.

- `app/retrieval/service.py`에서 hybrid는 선택 전략이 hybrid이고 필터가 없을 때 사용된다. routing 분석만으로 모든 요청이 다른 랭킹 전략을 사용하는 것으로 해석하지 않는다.
- 생성·재작성 기본 모델은 EXAONE `exaone3.5:7.8b`, 온라인 평가는 Qwen `qwen3.5:4b`다.
- `app/evaluation/civil_llm_rubric.py`의 호출 그룹은 Q2 / Q3·Q4·Q5 / Q1·Q7 / Q6 / Q0으로 최초 5회이며 같은 요청에서 Q2를 재사용한 재평가는 4회다. Q0~Q7 응답 점수 구조는 유지된다.
- 이번 확인은 코드 정적 대조이며 서버 실행·정확도·Windows 호환성 재검증 결과가 아니다.
