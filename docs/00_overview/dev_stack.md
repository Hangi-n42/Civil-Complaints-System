# 개발 기술 스택

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `requirements.txt`
  - `frontend/package.json`
  - `app/core/config.py`
  - `app/api/main.py`
  - `app/retrieval/`
  - `app/generation/`
  - `app/complaint_intelligence/`
- 관련 문서:
  - `docs/30_manuals/local_dev_runbook.md`
  - `docs/30_manuals/evaluation_runbook.md`

## 백엔드

- 언어/런타임: Python
- API framework: FastAPI
- 데이터 모델: Pydantic
- 실행: Uvicorn 또는 `scripts/run_api.py`
- 설정: `.env`, `app/core/config.py`, 일부 YAML config
- 테스트: pytest

주요 API 라우터는 `app/api/routers/`에 있습니다.

- `retrieval.py`: `/api/v1/index`, `/api/v1/search`
- `generation.py`: `/api/v1/qa`, `/api/v1/qa/stream`
- `complaint_intelligence.py`: 관제형 민원 인텔리전스 API
- `ui.py`: Workbench case API
- `admin.py`: 관리자 통계 API
- `structuring.py`: 단건 구조화 API

## 프론트엔드

- framework: Next.js
- UI runtime: React
- 스타일: Tailwind 계열 CSS와 컴포넌트 스타일
- 지도: Leaflet 기반 Intelligence hotspot map
- API client: `frontend/lib/api.ts`
- 주요 화면:
  - `frontend/app/page.tsx`
  - `frontend/app/workbench/page.tsx`
  - `frontend/app/intelligence/page.tsx`
  - `frontend/app/admin/page.tsx`

기본 API URL은 `frontend/lib/api.ts`에서 `NEXT_PUBLIC_API_BASE_URL` 또는 `http://127.0.0.1:8001`로 정해집니다. 실제 로컬 실행 포트는 실행 명령과 환경변수에 맞춰 확인해야 합니다.

## RAG/Search/QA

메인 민원 답변 파이프라인은 다음 경계로 나뉩니다.

1. ingestion/structuring: 원천 민원 데이터 로딩, PII 처리, 4요소 구조화
2. retrieval: query 분석, adaptive routing, ChromaDB/hybrid search
3. generation: 검색 근거 기반 답변 생성, JSON parsing, citation/validation
4. Workbench: 검색 결과와 답변 초안을 FE에서 표시

주요 구성요소:

- ChromaDB vector store
- BM25/dense/hybrid retrieval
- topic/complexity analyzer
- request segment analyzer
- PromptFactory
- QA response normalizer
- citation/legal grounding validator

## Complaint Intelligence Layer

Complaint Intelligence는 메인 RAG/QA 파이프라인을 대체하지 않는 sidecar입니다. 목적은 민원 데이터 묶음에서 실시간 관제형 read-model을 만드는 것입니다.

주요 기능:

- IssueAlert: 의미/시간/지역/기준선 기반 민원 급증 감지
- PublicAgencyInsight: EvidencePack 기반 공공기관 행정 조치 인사이트
- Duplicate Merge Recommendation Layer: 유사 민원 그룹 후보와 담당자 action gate
- SQLite repository: demo/로컬 환경의 영속 read-model
- scheduler/collector: 향후 실시간 수집원 연결을 위한 단일 프로세스 구조

## Local LLM

PublicAgencyInsight는 Fake provider와 Local Ollama provider를 모두 지원합니다. 운영 준비 평가에서 사용한 모델은 `exaone3.5:7.8b`입니다.

주의:

- Local LLM은 요청-응답형 실시간 생성보다 scheduler/read-model 갱신에 적합합니다.
- GroundingVerifier와 QualityGate 기준은 운영 품질 기준입니다.
- raw PII, prompt dump, raw response는 기본 저장하지 않습니다.

## 저장소와 산출물

- `data/processed`: 실제/가공 민원 데이터
- `data/demo`: demo seed
- `data/complaint_intelligence`: real replay/duplicate merge demo seed
- `data/evaluation`: curated scenario, holdout, retrieval qrels/pool
- `reports`: 평가 결과와 검증 산출물

`reports`에는 PR에 포함할 최종 리포트와 로컬 검증용 중간 산출물이 함께 있을 수 있습니다. PR에 포함할 때는 최종 summary 중심으로 범위를 정리해야 합니다.
