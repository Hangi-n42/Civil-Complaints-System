# 제품 요구사항 개요

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `frontend/app/workbench/page.tsx`
  - `frontend/app/intelligence/page.tsx`
- 관련 문서:
  - `docs/00_overview/architecture.md`
  - `docs/10_contracts/README.md`
  - `docs/20_domains/complaint_intelligence/README.md`

## 1. 제품 목표

이 프로젝트는 민원 데이터를 기반으로 담당자의 답변 작성과 관제 판단을 돕는 시스템입니다.

현재 제품은 두 축으로 구성됩니다.

1. 메인 RAG/QA Workbench
   - 민원 내용을 검색하고 유사 근거를 찾습니다.
   - 검색 근거를 바탕으로 답변 초안을 생성합니다.
   - citation, structured output, request segment를 통해 답변 검증과 편집을 돕습니다.

2. Complaint Intelligence Layer
   - 지속 유입되는 민원을 관제 read-model로 분석합니다.
   - IssueAlert로 민원 급증/핫스팟을 감지합니다.
   - PublicAgencyInsight로 공공기관 담당자가 실행할 행정 조치를 제안합니다.
   - Duplicate Merge Recommendation Layer로 유사 민원 묶음과 상태 전이를 제공합니다.

## 2. 사용자

### 민원 담당자

- 유사 민원과 근거를 빠르게 확인합니다.
- 답변 초안을 검토하고 필요한 내용을 보완합니다.
- 중복 민원 후보를 확인하고 병합, 분리, 반려 여부를 판단합니다.

### 관제/운영 담당자

- 최근 민원 급증 지역과 주제를 확인합니다.
- 안전, 시설, 안내, 단속, 처리 지연 등 행정 조치 우선순위를 봅니다.
- replay/demo seed와 평가 리포트로 관제 품질을 검증합니다.

### FE 담당자

- `frontend/lib/api.ts`와 `docs/10_contracts/frontend/*`를 기준으로 화면을 연결합니다.
- Intelligence dashboard는 실시간 LLM 호출이 아니라 저장된 read-model 조회를 기본 UX로 둡니다.

### BE 담당자

- API 계약은 `docs/10_contracts`를 기준으로 유지합니다.
- 도메인 정책은 `docs/20_domains`를 기준으로 검토합니다.

## 3. 핵심 기능 범위

### 3.1 Search/QA Workbench

- `/api/v1/search`
  - query, top_k, filters, query_signals 기반 검색
  - adaptive routing trace와 routing hint 반환
  - retrieved_docs/results/items 호환 필드 유지

- `/api/v1/qa`
  - query와 search_results 또는 자체 검색 결과 기반 답변 생성
  - answer, citations, structured_output, generation_metadata 반환

- `/api/v1/qa/stream`
  - QA 처리 stage event와 done event를 SSE로 반환

### 3.2 Complaint Intelligence Dashboard

- `/complaint-intelligence/dashboard`
  - FE가 바로 표시할 수 있는 summary, issue_alerts, public_insights 반환

- `/complaint-intelligence/dashboard/run-analysis`
  - 입력 events로 분석을 실행하고 dashboard read-model 형태로 반환

- `/complaint-intelligence/issue-alerts`
  - 저장된 IssueAlert 목록 조회

- `/complaint-intelligence/public-insights`
  - 저장된 PublicAgencyInsight 목록 조회

- `/complaint-intelligence/public-insights/{insight_id}/evidence-pack`
  - 관리자/검증용 masked EvidencePack 조회

### 3.3 Duplicate Merge Recommendation Layer

- `/complaint-intelligence/duplicate-groups/run-analysis`
  - 입력 events에서 유사 민원 그룹 후보 생성

- `/complaint-intelligence/duplicate-groups`
  - candidate/confirmed/split/rejected 상태별 그룹 조회

- `/complaint-intelligence/duplicate-groups/{merge_id}/confirm`
  - blocker가 없는 candidate를 confirmed로 전환

- `/complaint-intelligence/duplicate-groups/{merge_id}/split`
  - candidate 또는 confirmed 그룹을 split으로 전환

- `/complaint-intelligence/duplicate-groups/{merge_id}/reject`
  - candidate 그룹을 rejected로 전환

- `/complaint-intelligence/duplicate-groups/{merge_id}/draft-reply`
  - confirmed 그룹에서만 BE3 전달용 draft reply payload 생성

- `/complaint-intelligence/duplicate-groups/{merge_id}/reply-draft`
  - confirmed 그룹에서만 실제 답변 초안 생성

## 4. 비범위

- PublicAgencyInsight는 AI/RAG/prompt 개선 인사이트가 아닙니다.
- Duplicate Merge candidate는 실제 민원 상태를 바꾸지 않습니다.
- confirmed 상태도 자동 발송이나 외부 시스템 상태 변경이 아니라 내부 read-model 상태입니다.
- Local LLM을 FE 요청 시마다 동기 호출하는 UX는 기본 운영 방식이 아닙니다.
- 실제 외부 민원 접수 시스템, Kafka, Redis, 다중 인스턴스 분산 락은 현재 범위가 아닙니다.

## 5. 품질 기준

- PII는 API, EvidencePack, report에 raw 형태로 노출하지 않습니다.
- PublicAgencyInsight는 EvidencePack과 GroundingVerifier/QualityGate를 통과해야 합니다.
- Duplicate Merge는 blocker risk가 있으면 자동 confirm과 draft reply를 막습니다.
- FE 계약은 후방 호환 필드를 최대한 유지합니다.
- 문서 기준 계약은 코드로 확인된 범위만 적고, 불확실한 항목은 확인 필요로 표시합니다.

## 6. 현재 데모/검증 전략

- 실제 공개/가공 데이터를 demo/replay timeline으로 재배치해 관제형 흐름을 시뮬레이션합니다.
- curated scenario와 holdout 데이터로 IssueAlert/PublicAgencyInsight 품질을 평가합니다.
- Local LLM 평가는 `exaone3.5:7.8b` 기준으로 수행하되, latency는 운영 정책 문서에서 별도 관리합니다.
