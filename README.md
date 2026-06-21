# AI-Civil-Affairs-Systems

민원 데이터를 구조화하고, 유사 민원 검색과 RAG 기반 답변 초안을 지원하며, 공공기관 담당자가 민원 급증/반복 패턴을 관제할 수 있도록 돕는 로컬 중심 민원 AI 시스템입니다.

- 문서 상태: canonical entry
- 최종 확인일: 2026-06-21
- 기준 문서:
  - `docs/00_overview/README.md`
  - `docs/10_contracts/README.md`
  - `docs/20_domains/README.md`
  - `docs/30_manuals/README.md`

## 현재 시스템 범위

이 저장소는 크게 네 흐름으로 구성됩니다.

1. 메인 RAG/QA 파이프라인
   - 민원 텍스트 구조화
   - 유사 민원 검색
   - RAG 기반 답변 초안 생성
   - citation 및 응답 스키마 검증

2. Complaint Intelligence Layer
   - 민원 이벤트 기반 관제 read-model
   - IssueAlert 자동 감지
   - PublicAgencyInsight 생성
   - EvidencePack, QualityGate, GroundingVerifier 기반 검증

3. Duplicate Merge Recommendation Layer
   - 중복/유사 민원 그룹 후보 생성
   - risk flag 및 blocker 기반 자동 병합 방지
   - candidate/confirmed/split/rejected 내부 상태 관리
   - confirmed 그룹에서만 draft-reply/reply-draft 허용

4. Frontend Workbench 및 Intelligence Dashboard
   - Next.js 기반 업무 화면
   - 검색/QA Workbench
   - 민원 인텔리전스 대시보드
   - IssueAlert, PublicAgencyInsight, Duplicate Group 표시

## 기술 스택

- Backend: FastAPI, Pydantic, Uvicorn
- Frontend: Next.js, React, TypeScript
- Search/RAG: ChromaDB, BM25, Hybrid/RRF, adaptive routing
- LLM: Ollama 기반 로컬 모델, PromptFactory, RAG 응답 검증
- Intelligence: SQLite read-model, replay/demo seed, evaluation scripts
- Test/Validation: pytest, scenario evaluation, report artifacts

자세한 스택과 폴더 구조는 다음 문서를 기준으로 확인하세요.

- `docs/00_overview/dev_stack.md`
- `docs/00_overview/folder_structure.md`
- `docs/00_overview/architecture.md`

## 빠른 실행

### 1. Python 환경 준비

```bash
python -m venv civil
civil\Scripts\activate
pip install -r requirements.txt
```

기존 로컬 환경이 이미 있다면 이 저장소에서는 `civil\Scripts\python.exe`를 기준 실행기로 사용하는 것이 가장 안전합니다.

### 2. Backend 실행

```bash
civil\Scripts\python.exe scripts\run_api.py
```

확인:

- API 문서: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`

### 3. Frontend 실행

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

확인:

- Next.js UI: `http://localhost:3000`
- API base URL은 `frontend/lib/api.ts`와 환경 변수 설정을 함께 확인하세요.

### 4. Ollama 실행

```bash
ollama serve
```

로컬 LLM 평가와 PublicAgencyInsight 생성에는 운영 환경의 모델 상태가 영향을 줍니다. 현재 프로젝트 문서와 평가 리포트는 `exaone3.5:7.8b` 기준 결과를 중심으로 정리되어 있습니다.

## 주요 API

현재 기준 API 계약은 `docs/10_contracts/api/current_api_contract.md`를 기준으로 합니다.

대표 endpoint:

- `POST /api/v1/search`
- `POST /api/v1/qa`
- `GET /complaint-intelligence/dashboard`
- `GET /complaint-intelligence/issue-alerts`
- `GET /complaint-intelligence/public-insights`
- `GET /complaint-intelligence/public-insights/{insight_id}`
- `GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack`
- `GET /complaint-intelligence/duplicate-groups`
- `POST /complaint-intelligence/duplicate-groups/run-analysis`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/confirm`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/split`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/reject`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/draft-reply`
- `POST /complaint-intelligence/duplicate-groups/{merge_id}/reply-draft`

## 문서 읽는 순서

처음 온 개발자는 아래 순서로 읽는 것을 권장합니다.

1. `docs/00_overview/README.md`
2. `docs/00_overview/architecture.md`
3. `docs/10_contracts/README.md`
4. `docs/10_contracts/api/current_api_contract.md`
5. `docs/10_contracts/data/current_data_contract.md`
6. `docs/10_contracts/frontend/intelligence_fe_contract.md`
7. `docs/20_domains/complaint_intelligence/README.md`
8. `docs/30_manuals/local_dev_runbook.md`

문서 상태의 기준:

- `00_overview`, `10_contracts`, `20_domains`, `30_manuals`: 현재 기준 문서
- `40_delivery`: 주차별 산출물과 handoff 자료
- `50_issues`: 이슈 분석, 운영 메모, 평가/검증 기록
- `60_specs`: source-spec 및 과거 설계 원본

자세한 문서 감사 결과는 `docs/DOCS_AUDIT.md`를 확인하세요.

## 데이터와 산출물

- `data/raw_data`, `data/processed`: 원천/가공 데이터
- `data/demo`: 데모 seed
- `data/evaluation`: curated scenario 및 holdout 평가 데이터
- `data/complaint_intelligence`: SQLite 기반 민원 인텔리전스 read-model
- `reports`: 평가 리포트와 분석 산출물
- `logs`: 로컬 실행 로그

민원 데이터와 평가 산출물에는 개인정보가 포함될 수 있으므로 외부 공유 전 반드시 마스킹 여부를 확인해야 합니다.

## 테스트와 검증

대표 검증 명령:

```bash
civil\Scripts\python.exe -m pytest app\tests\unit -q
```

문서 작업 검증:

```bash
git diff --check
```

Complaint Intelligence 평가:

```bash
civil\Scripts\python.exe scripts\evaluate_complaint_intelligence_scenarios.py --provider fake --output reports\complaint_intelligence_eval_report_final_fake.json
```

Local LLM 평가와 replay/demo 실행 절차는 다음 문서를 기준으로 확인하세요.

- `docs/30_manuals/complaint_intelligence_demo_replay.md`
- `docs/30_manuals/evaluation_runbook.md`

## 주의 사항

- 운영 코드 변경 전에는 현재 계약 문서와 실제 router/schema를 함께 확인하세요.
- `60_specs`는 현재 기준 계약이 아니라 source-spec입니다.
- Duplicate Merge의 `candidate`와 `confirmed`는 모두 내부 read-model 상태이며, 실제 민원 상태 변경이나 자동 발송을 의미하지 않습니다.
- `draft-reply`와 `reply-draft`는 confirmed 그룹에서만 허용됩니다.
- raw PII를 문서, 리포트, FE 화면, 답변 초안에 노출하지 않는 것이 기본 원칙입니다.

## 저장소

- Repository: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems
- Issues: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues
- Pull requests: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/pulls
