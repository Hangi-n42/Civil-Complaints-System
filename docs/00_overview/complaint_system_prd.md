# 민원 시스템 — 업무 지식 기반 답변 검토 지원 PRD

- 문서 역할: 회사 지식 기반의 첫 활용 애플리케이션. 기존 민원 기능과 후속 연계 요구 구분
- 문서 버전: v2.2 · 활용 시연 구체화 2026-09-29
- 코드 정적 확인·정리일: 2026-09-26
- 기준 코드:
  - `app/api/routers/retrieval.py`
  - `app/api/routers/generation.py`
  - `app/api/routers/complaint_intelligence.py`
  - `frontend/app/workbench/page.tsx`
  - `frontend/app/intelligence/page.tsx`
- 관련 문서:
  - `docs/00_overview/complaint_system_architecture.md`
  - `docs/10_contracts/README.md`
  - `docs/20_domains/complaint_intelligence/README.md`

- [회사 지식 PRD](company_knowledge_prd.md): 공통 개념·대상·정책·근거·변경 관리의 주 요구사항.
- 본 문서: 기존 민원 기능을 유지하며 공통 지식을 민원 요구별 판단·답변 검토에 연결하는 활용 요구사항.

## 1. 문제 정의와 제품 목표

### 1.1 현장 근거

- 근거: 팀원이 조사하고 사용자가 제공한 부산 콜센터 관리자 인터뷰 요약. 상세 출처 구분은 [인터뷰 활용 기록](../70_research/company_knowledge/complaint_interview_problem_definition_2026-09-29.md) 참조.
- 콜센터: 전화·문자·채팅을 Genesys로 통합 관리. 대·중·소분류는 사람이 수행.
- 문서 민원: 국민신문고 등 별도 시스템에서 운영. 복합 민원은 주관부서·협조부서로 배분하고 주관부서가 단일 회신.
- 도입 조건: AI·음성 처리·기존 시스템 연동 비용과 지속 운영 예산이 우선순위 판단의 핵심.
- 제품 선택: 기존 접수·채널 통합과 부서 배분 절차를 유지하고 담당자의 근거 확인·답변 검토 업무에 집중.

### 1.2 해결할 문제

- **민원 담당자는 접수된 문장의 개별 요구를 실제 업무 대상·정책·적용 조건·담당 책임·근거와 연결한 뒤, 누락 없이 하나의 답변으로 정리해야 함.**
- 핵심 부담 가설: 요구별 자료 탐색·조건 대조·부서 검토 내용 통합을 건별로 반복하고, 정책 변경 시 기존 안내와 답변 근거를 다시 확인하는 작업.
- 첫 대상: 문서 민원 담당자의 답변 준비·통합 검토. 콜센터 관리자 인터뷰에서 도출한 가설을 문서 민원 담당자의 비식별 처리 사례로 확인.
- 채널군 간 정보 접근 경계와 업무 지식 공유를 구분. 동일인의 다중 채널 사건 통합보다 공통 정책·안내·근거의 재사용을 우선.

### 1.3 제품 목표와 사용 흐름

- **목표: 기존 업무 절차 안에서 요구별 근거·조건·검토 결과를 확인하도록 지원하고, 검토·수정 비용을 포함한 답변 준비 부담 감소.**
- 업무 연결: **민원 요구 → 업무 대상 → 적용 정책·조건 → 담당 책임 → 근거 → 검토 결과 → 통합 답변**.
- AI 역할: 요구 분해·근거 검색·답변 초안·누락 및 불일치 후보 제시.
- 담당자 역할: 업무 배분, 적용 기준과 답변 확정. 실제 회신과 처리 책임은 기존 업무 체계 유지.

| 단계 | 담당자에게 제공할 결과 | 구현 구분 |
|---|---|---|
| 민원 이해 | 개별 요청과 구조화 정보 | 기존 구조화·요청 분해 기능 활용 |
| 근거 탐색 | 유사 민원·답변과 인용 근거 | 기존 Search/QA 활용 |
| 업무 지식 확인 | 요구에 대응하는 정책·조건·문서 근거와 사용 버전 | 회사 지식 P1 연계 |
| 답변 검토 | 요구별 근거 대응, 초안과 누락·불일치 확인 | 기존 생성·평가 활용 및 P1 연결 |
| 협업·처리 추적 | 담당자 배정·검토 완료 상태·외부 회신 결과 | 후속 연동 범위 |

### 1.4 온톨로지·지식그래프 활용

- 공통 용어: 시민 표현과 내부 업무 개념을 연결하고 적용 범위 보존.
- 업무 관계: 대상·정책·요건·서류·담당 책임을 근거와 함께 연결.
- 요구별 적용: 같은 유형의 민원도 대상·시점·예외에 맞는 근거 선택.
- 변경 대응: 개정된 정책과 연결된 안내·지식의 재검토 지원.
- 재사용: 상담·문서 회신·관제가 같은 지식 정의와 근거를 참조하도록 확장.
- 담당 책임 제안은 업무분장 근거를 제시하고 기존 담당자가 확정. 온톨로지 연결만으로 법적 판단·자동 배분·이행 확약을 실행하지 않음.

### 1.5 유지할 기존 기능

- Search/QA Workbench: 유사 민원 검색, 근거 기반 답변 초안, 인용·요청별 검토·편집.
- Complaint Intelligence: 급증·핫스팟 탐지, 근거 기반 행정 조치 제안, 유사 민원 그룹 검토.
- 기존 기능 계약 유지: 회사 지식 출처와 민원 사례 인용을 구분하고 실제 원문 조회 지원.
- 초기 연동: 기존 화면의 별도 지식 패널·assist API. 콜센터 교체·STT/TTS 신규 구축·외부 접수 시스템 통합은 별도 사업 범위.

### 1.6 첫 시연 사례와 교통 영향 검토의 구분

- 문서 민원 시연: 국민임대 자료로 답할 수 있는 복합 문의 1건. 제출서류·발급기관과 청약통장 재사용 조건 등 서로 다른 근거가 필요한 요구 선택.
- 목적: **개별 요구와 적용 조건·근거·답변 문장을 연결해 담당자가 빠짐없이 검토하도록 지원**.
- 흐름: 민원 입력 → 요구 수정 → 요구별 지식 근거 선택 → 통합 초안 → 담당자 검토·저장.
- 화면: 요구 목록과 답변 상태, 선택한 요구의 원문·관계 경로, 통합 답변. 답변 문장에서 요구와 출처로 이동.
- 완료: 고정한 모든 요구의 답변 또는 추가 확인 사유 표시, 근거 없는 부서·일정 확약 방지, 수정 결과·스냅샷·근거 ID 재조회.
- 측정: 직접 자료 탐색 대비 사람의 확인·수정 시간, 요구 누락, 조건 오적용. 실제 민원이 없으면 재구성 입력임을 표시.
- 별도 버스 시연: 같은 지식 계층으로 정류장 이전안의 영향 대상과 접근 거리 변화를 비교. 문서 민원 사례가 답변 검토를 보여준다면 버스 사례는 실행 전 대안 판단을 보여줌.
- 교통 사례의 데이터·계산·완료 기준은 [회사 지식 PRD §4.3](company_knowledge_prd.md#43-사례-b--버스-정류장-변경안의-편익과-불편-비교) 적용. 기존 민원 QA 경로에 교통 계산을 일괄 삽입하지 않음.

## 2. 사용자

### 민원 담당자

- 유사 민원과 근거를 빠르게 확인.
- 답변 초안을 검토하고 필요한 내용을 보완.
- 중복 민원 후보를 확인하고 병합, 분리, 반려 여부를 판단.

### 관제/운영 담당자

- 최근 민원 급증 지역과 주제를 확인.
- 안전, 시설, 안내, 단속, 처리 지연 등 행정 조치 우선순위를 확인.
- replay/demo seed와 평가 리포트로 관제 품질을 검증.

### FE 담당자

- `frontend/lib/api.ts`와 `docs/10_contracts/frontend/*`를 기준으로 화면을 연결.
- Intelligence dashboard는 실시간 LLM 호출이 아니라 저장된 read-model 조회를 기본 UX로 설정.

### BE 담당자

- API 계약은 `docs/10_contracts`를 기준으로 유지.
- 도메인 정책은 `docs/20_domains`를 기준으로 검토.

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

- PII는 API, EvidencePack, report에 raw 형태로 노출 금지.
- PublicAgencyInsight는 EvidencePack과 GroundingVerifier/QualityGate를 통과 필수.
- Duplicate Merge는 blocker risk가 있으면 자동 confirm과 draft reply를 차단.
- FE 계약은 후방 호환 필드를 최대한 유지.
- 구현 기능과 후속 연계 요구 구분. 답변 근거의 대상·조건·시점 및 요구별 대응 확인.

## 6. 현재 데모/검증 전략

- 실제 공개/가공 데이터를 demo/replay timeline으로 재배치해 관제형 흐름을 시뮬레이션합니다.
- curated scenario와 holdout 데이터로 IssueAlert/PublicAgencyInsight 품질을 평가.
- 현재 main 모델: 생성·구조화·민원 평가·지식 검색은 Gemma `gemma4:31b-it-q4_K_M`, 피드백과 K3 반례 검토는 Qwen `qwen3.8:27b-q4_K_M`. [모델 선정 기록](../30_manuals/llm_two_model_selection.md) 참조.
- 과거 EXAONE·Qwen 4B 평가 수치는 당시 조건의 기록으로 보존. 두 활용 사례는 현재 역할 설정으로 확인하며 꺼진 기능을 임의 활성화하지 않음.

## 7. 효용·도입 판단

| 지표 | 측정 내용 |
|---|---|
| 담당자 작업시간 | 건별 근거 탐색·조건 확인·답변 검토·수정 시간 |
| 답변 품질 | 핵심 요구 누락, 정책 오적용, 근거 없는 서술, 수정·반려 사유 |
| 협업 부담 | 실제 시범 범위에서 부서 제안 수정과 협조 내용 재확인 정도 |
| 갱신 부담 | 정책 변경 후 관련 지식·안내 확인 및 수정 시간·누락 |
| 운영 비용 | 초기 자료 정리·온톨로지 유지·모델 실행·연동·오류 수정 비용 |

- 기존 작업과 동일한 필수 산출물 기준으로 비교. 자동 생성 속도보다 사람의 최종 검토까지 포함한 총부담을 우선.
- 기존 답변 품질을 유지하면서 반복 작업과 수정 부담이 줄어드는지 확인. 분류 정확도만으로 도입 효과를 판단하지 않음.
- 현장 확인 순서: 국민신문고 담당자·주관부서의 비식별 사례 → 접수·배분·근거 확인·협조·회신 과정 → 반복·대기·재작업 구간 → 좁은 시범 적용.
- 전화 중심 운영과 비용 제약을 고려해 기존 시스템의 내보내기·허용된 연계 방식부터 검토.
