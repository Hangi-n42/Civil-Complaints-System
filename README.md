# AI-Civil-Affairs-Systems

민원 담당자를 위한 온디바이스 LLM 기반 검색, 구조화, 질의응답 시스템입니다.
로컬 환경에서 민원 데이터를 구조화하고, ChromaDB 기반 검색과 Ollama 기반 생성 모델을 연결해 담당자가 검토할 수 있는 근거 기반 답변 초안을 제공합니다.

## 한눈에 보기

- 목적: 민원 데이터를 로컬 환경에서 안전하게 구조화하고 검색/QA까지 연결
- 핵심 가치: 온디바이스 실행, 보안/프라이버시 중심 파이프라인, 근거 기반 답변 생성
- 백엔드: FastAPI, Uvicorn, Pydantic
- 검색/RAG: ChromaDB, sentence-transformers, BAAI/bge-m3, BM25, RRF, adaptive routing
- 생성: Ollama, PromptFactory, citation 검증, 응답 정규화
- 프론트엔드: `frontend/` 기준 Next.js Workbench
- 레거시/PoC UI: `app/ui/Home.py` 기반 Streamlit
- 데이터 축: AIHub 공공 민원 상담 데이터 기반 실험/평가 체계

## 주요 기능

1. 데이터 입수: CSV/JSON 배치 및 수동 입력용 서비스 계층
2. 구조화: Observation/Result/Request/Context 4요소 추출
3. 엔티티 추출: LOCATION/TIME/FACILITY/HAZARD/ADMIN_UNIT
4. 적응형 검색: topic/complexity 분석 후 검색 전략과 파라미터 선택
5. 벡터/하이브리드 검색: ChromaDB dense 검색, BM25, RRF, rerank/filter 실험
6. 생성: citation 포함 RAG 응답 생성, 법령 인용 보조, 응답 스키마 정규화
7. Workbench UI: 민원 선택, 유사 민원 검색, 답변 초안 검토/편집, 관리자 통계 화면

## 아키텍처 요약

```text
민원 원천/데모 데이터
  -> ingestion/structuring
  -> retrieval analyzer + adaptive router
  -> ChromaDB/BM25 검색
  -> generation PromptFactory + Ollama
  -> FastAPI API
  -> Next.js Workbench 또는 Streamlit UI
```

핵심 API 계약은 `/api/v1/search`와 `/api/v1/qa`입니다. `/api/v1/search`는 `routing_trace`, `routing_hint`, `strategy_id`, `route_key`를 반환하고, `/api/v1/qa`는 검색 단계의 `routing_hint`와 검색 결과를 받아 답변 초안과 citation을 생성합니다.

## 빠른 시작

### 1) Python 환경 준비

```bash
git clone https://github.com/Hangi-n42/AI-Civil-Affairs-Systems.git
cd AI-Civil-Affairs-Systems

python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

pip install -r requirements.txt
```

### 2) Ollama 실행

```bash
ollama serve
```

기본 모델은 `app/core/config.py`와 `.env.example` 기준 `exaone3.5:7.8b`입니다. 로컬에 모델이 없다면 별도로 pull이 필요합니다.

### 3) FastAPI 실행

```bash
python scripts/run_api.py
```

- API 문서: http://localhost:8000/docs
- 헬스 체크: http://localhost:8000/api/v1/health
- 주요 엔드포인트: `/api/v1/search`, `/api/v1/qa`, `/api/v1/ui/cases`, `/api/v1/chroma/*`

### 4) Next.js Workbench 실행

```bash
npm run dev
```

또는:

```bash
npm --prefix frontend run dev
```

- Next.js UI: http://localhost:3000
- 프론트엔드 기본 API URL은 `frontend/lib/api.ts` 기준 `http://127.0.0.1:8001`입니다.
- 로컬 FastAPI 기본 포트 `8000`을 직접 바라보려면 실행 환경에서 `NEXT_PUBLIC_API_BASE_URL`을 데모 구성에 맞게 지정하세요.

### 5) Streamlit UI 실행(레거시/PoC)

```bash
python scripts/run_ui.py
```

- Streamlit UI: http://localhost:8501
- 현재 신규 UI 작업 기준은 `frontend/`의 Next.js Workbench입니다.

## 테스트와 검증

```bash
python -m pytest app/tests
```

프론트엔드 검증:

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
```

일부 검색/생성 테스트는 ChromaDB 인덱스, Ollama 서버, 로컬 모델 상태에 영향을 받습니다. 인프라가 준비되지 않은 환경에서는 단위 테스트 중심으로 먼저 확인하세요.

## 디렉터리 구조

```text
AI-Civil-Affairs-Systems/
├── app/                    # FastAPI, RAG 코어, Streamlit UI, 테스트
│   ├── api/                # FastAPI 앱, 라우터, Pydantic 스키마
│   ├── core/               # 설정, 로깅, 예외, 공통 유틸
│   ├── ingestion/          # CSV/JSON 입수, 전처리
│   ├── structuring/        # 4요소 구조화, NER, 긴급도/부서/법령 신호
│   ├── retrieval/          # ChromaDB, BM25, RRF, adaptive routing
│   ├── generation/         # Ollama QA 생성, 프롬프트, citation, 정규화
│   ├── evaluation/         # 검색/생성 평가 데이터와 지표 유틸
│   ├── ui/                 # Streamlit 레거시/PoC UI
│   └── tests/              # unit/integration 테스트
├── frontend/               # Next.js Workbench UI
│   ├── app/                # App Router 페이지: queue, workbench, admin
│   ├── components/         # AppSidebar, SearchUI 등
│   ├── lib/                # API client, mock data, 안전 파싱 유틸
│   └── public/             # 정적 자산
├── configs/                # 런타임/모델/검색 파이프라인 설정
├── data/                   # 데모, 원천, 가공, 평가, 법령, ChromaDB 데이터
├── docs/                   # 프로젝트 문서
├── logs/                   # 실행 로그(로컬 산출물)
├── reports/                # 평가/분석 결과
├── schemas/                # JSON Schema 원본
├── scripts/                # 실행/인덱싱/평가/진단 스크립트
├── requirements.txt        # Python 의존성
└── package.json            # frontend npm script 프록시
```

더 자세한 구조는 [docs/00_overview/folder_structure.md](docs/00_overview/folder_structure.md)를 참고하세요.

## 관심사별 위치

- Frontend UI: `frontend/app`, `frontend/components`, `frontend/lib`
- 레거시 UI: `app/ui/Home.py`, `app/ui/components`, `app/ui/services`
- Backend/API: `app/api/main.py`, `app/api/routers`, `app/api/schemas`
- 검색/RAG: `app/retrieval`, `configs/retrieval_pipelines`
- 생성/LLM: `app/generation`, `app/generation/prompts`, `app/generation/validators`
- 구조화/전처리: `app/ingestion`, `app/structuring`
- DB/영속성: `data/chroma_db`, `app/retrieval/vectorstores/chroma_store.py`
- 설정/환경변수: `.env.example`, `app/core/config.py`, `configs/*.yaml`
- 테스트: `app/tests/unit`, `app/tests/integration`
- 배포/CI: `.github/workflows`

현재 명시적인 로그인, JWT, OAuth 기반 인증 흐름은 별도 모듈로 분리되어 있지 않습니다.

## 데이터와 로컬 산출물

- `data/demo/pending_cases_8.json`: Next.js/Streamlit UI가 사용할 수 있는 데모 민원 목록
- `data/chroma_db`: ChromaDB persist 디렉터리
- `data/raw_data`, `data/processed`, `data/evaluation`, `data/laws`: 원천/가공/평가/법령 데이터
- `logs`, `reports`, `.pytest_cache`, `frontend/.next`, `frontend/node_modules`, `civil`: 로컬 실행 또는 개발 환경 산출물 성격이 강합니다.

민원 데이터와 벡터 DB에는 원문 일부나 검색 metadata가 포함될 수 있으므로, 외부 공유 전 개인정보와 저장소 추적 정책을 확인해야 합니다.

## 주요 문서

- 개요/로드맵: [docs/00_overview/prd.md](docs/00_overview/prd.md), [docs/00_overview/mvp_scope.md](docs/00_overview/mvp_scope.md), [docs/00_overview/wbs_8weeks_v2_updated.md](docs/00_overview/wbs_8weeks_v2_updated.md)
- 스택/구조: [docs/00_overview/dev_stack.md](docs/00_overview/dev_stack.md), [docs/00_overview/folder_structure.md](docs/00_overview/folder_structure.md)
- 인터페이스/계약: [docs/10_contracts/api/api_spec.md](docs/10_contracts/api/api_spec.md), [docs/10_contracts/schema/schema_contract.md](docs/10_contracts/schema/schema_contract.md), [docs/10_contracts/interfaces/README.md](docs/10_contracts/interfaces/README.md)
- 운영/개발 매뉴얼: [docs/30_manuals/manual.md](docs/30_manuals/manual.md), [docs/30_manuals/local_chromadb_indexing.md](docs/30_manuals/local_chromadb_indexing.md)
- 구현 명세: [docs/60_specs/api_interface_spec.md](docs/60_specs/api_interface_spec.md), [docs/60_specs/data_schema_spec.md](docs/60_specs/data_schema_spec.md), [docs/60_specs/ui_workbench_spec.md](docs/60_specs/ui_workbench_spec.md)

## 팀 구성

- BE1(팀장): 데이터 파이프라인, 구조화, 평가, 발표 총괄
- FE: Next.js Workbench UI/UX, 검색/QA 화면, 데모 흐름
- BE2: 임베딩/벡터DB/검색/검색평가
- BE3: API/LLM/RAG/파싱/성능 안정화

## 저장소 링크

- 저장소: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems
- 이슈: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues
- PR: https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/pulls

## 라이선스

대학 졸업 프로젝트 (비공개)

Last Updated: 2026-06-09
Status: Active Development
