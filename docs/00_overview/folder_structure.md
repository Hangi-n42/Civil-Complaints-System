# 폴더 구조 설계 문서 (Adaptive RAG + Next.js)

문서 버전: v3.2
최신화: 2026-06-09

## 1. 목적

본 문서는 현재 저장소의 실제 구조를 기준으로 Adaptive RAG 코어 모듈, FastAPI API, Next.js Workbench UI, 데이터/평가 산출물의 경계를 정리한다.
신규 UI 작업 기준은 `frontend/`의 Next.js Workbench이며, 기존 `app/ui` Streamlit UI는 레거시/PoC 용도로 유지한다.

핵심 API 계약은 `/api/v1/search`와 `/api/v1/qa`입니다. `/api/v1/search`는 `routing_trace`, `routing_hint`, `strategy_id`, `route_key`를 반환하고, `/api/v1/qa`는 검색 단계의 `routing_hint`를 이어받아 `structured_output`, `answer`, `citations`를 반환한다.

## 2. 현재 최상위 구조

```text
AI-Civil-Affairs-Systems/
├─ app/                         # Python 애플리케이션 코드
├─ frontend/                    # Next.js Workbench UI
├─ configs/                     # 런타임, 모델, 검색 파이프라인 설정
├─ data/                        # 데모/원천/가공/평가/법령/벡터 DB 데이터
├─ docs/                        # 프로젝트 문서
├─ logs/                        # 실행 로그(로컬 산출물)
├─ reports/                     # 평가/분석 결과
├─ schemas/                     # JSON Schema 원본
├─ scripts/                     # 실행, 인덱싱, 평가, 진단 스크립트
├─ .github/                     # GitHub Actions, 협업 자동화
├─ requirements.txt             # Python 의존성
├─ package.json                 # frontend npm script 프록시
├─ pytest.ini                   # pytest 설정
├─ README.md                    # 프로젝트 진입 문서
└─ .env.example                 # 환경변수 예시
```

## 3. `app/` 구조

```text
app/
├─ api/
│  ├─ main.py                   # FastAPI 앱 진입점
│  ├─ error_utils.py            # 공통 에러 응답, request_id, timestamp 유틸
│  ├─ routers/
│  │  ├─ retrieval.py           # /api/v1/index, /api/v1/search
│  │  ├─ generation.py          # /api/v1/qa
│  │  ├─ ui.py                  # /api/v1/ui/cases
│  │  └─ chroma_debug.py        # /api/v1/chroma/* read-only 진단 API
│  └─ schemas/
│     ├─ retrieval.py           # Search/Index 요청·응답 모델
│     └─ generation.py          # QA 요청·응답 모델
├─ core/
│  ├─ config.py                 # 환경변수와 기본 설정
│  ├─ logging.py                # API/파이프라인 로그 설정
│  ├─ exceptions.py             # 도메인 예외
│  └─ title_builder.py          # 민원 제목 생성 유틸
├─ ingestion/
│  ├─ service.py                # CSV/JSON 로딩, 정제, 중복 제거, PII 처리
│  ├─ loaders/                  # 입력 로더 확장 지점
│  └─ preprocess/               # 전처리 확장 지점
├─ structuring/
│  ├─ service.py                # 4요소 구조화 오케스트레이션
│  ├─ structured_extractor.py   # 규칙 기반 구조화 추출
│  ├─ llm_extractor.py          # Ollama 기반 의미 추출
│  ├─ merger.py                 # 추출 결과 병합
│  ├─ structured_merge.py       # 구조화 필드 병합 유틸
│  ├─ verifier.py               # evidence/self verification
│  ├─ enrichment.py             # issue/entity/key term 보강
│  ├─ department_assigner.py    # 담당 부서 후보 도출
│  ├─ legal_dictionary.py       # 법령 참조 후보 매칭
│  ├─ law_corpus.py             # 법령 corpus 파싱/검증
│  ├─ urgency/                  # 긴급도 feature/model/scorer/safety rules
│  ├─ validators/               # 구조화 검증 확장 지점
│  └─ extractors/               # 추출기 확장 지점
├─ retrieval/
│  ├─ service.py                # 검색 서비스 진입점
│  ├─ vectorstores/
│  │  ├─ chroma_store.py        # ChromaDB adapter
│  │  └─ chroma_validation.py   # ChromaDB 필터/컬렉션 점검
│  ├─ analyzers/
│  │  ├─ topic_analyzer.py      # topic_type 분석
│  │  └─ complexity_analyzer.py # complexity_level/score 분석
│  ├─ router/
│  │  └─ adaptive_router.py     # topic/complexity 기반 route_key 결정
│  ├─ search/
│  │  └─ hybrid.py              # BM25 + Dense RRF 검색
│  ├─ pipeline/
│  │  ├─ base.py                # retrieval pipeline 공통 타입
│  │  ├─ runner.py              # YAML 기반 pipeline runner
│  │  └─ stages/                # bm25, chroma_dense, rrf, rerank, llm filter
│  ├─ law_article_store.py      # 법령 조문 검색 저장소
│  ├─ grounding_filter.py       # LLM relevance/grounding filter
│  ├─ entity_labels.py          # 엔티티 라벨 정규화
│  └─ embeddings/               # 임베딩 확장 지점
├─ generation/
│  ├─ service.py                # Ollama QA 생성 서비스
│  ├─ context_mapper.py         # 검색 결과 -> QA context 변환
│  ├─ prompts/
│  │  └─ prompt_factory.py      # topic-aware prompt 생성
│  ├─ parsing/
│  │  └─ json_utils.py          # LLM JSON 응답 파싱
│  ├─ normalization/
│  │  └─ response_normalizer.py # unified QA response 정규화
│  ├─ validators/
│  │  └─ qa_response_validator.py # answer/citation 검증
│  ├─ citation/
│  │  ├─ citation_mapper.py     # 검색 context와 citation 정합성 검증
│  │  └─ legal_citation.py      # 법령 인용 추출/검증
│  └─ llm/                      # LLM adapter 확장 지점
├─ evaluation/                  # 평가 dataset, metrics, reporting, artifacts
├─ ui/                          # Streamlit 레거시/PoC UI
│  ├─ Home.py                   # Streamlit 앱 진입점
│  ├─ components/               # Streamlit UI 컴포넌트
│  ├─ services/                 # UI용 API adapter/parser
│  └─ pages/                    # Streamlit page 확장 지점
└─ tests/
   ├─ unit/                     # 단위 테스트
   ├─ integration/              # 통합 테스트
   └─ fixtures/                 # 테스트 fixture
```

## 4. `frontend/` 구조

```text
frontend/
├─ app/
│  ├─ layout.tsx                # 앱 공통 레이아웃
│  ├─ page.tsx                  # 민원 선택/queue 화면
│  ├─ workbench/
│  │  └─ page.tsx               # 처리 Workbench 화면
│  ├─ admin/
│  │  └─ page.tsx               # 관리자 통계 대시보드
│  ├─ error.tsx                 # Next.js 에러 화면
│  ├─ globals.css               # Tailwind 전역 스타일
│  └─ favicon.ico
├─ components/
│  ├─ AppSidebar.tsx            # 좌측 네비게이션
│  └─ SearchUI.tsx              # 상태/우선순위 배지, 검색 결과 카드
├─ lib/
│  ├─ api.ts                    # FastAPI client, 응답 매핑, mock fallback
│  ├─ mockData.ts               # 데모 민원/통계 mock data
│  └─ safe-data.ts              # 안전 파싱/상태 sanitizing 유틸
├─ public/                      # 정적 SVG 자산
├─ package.json                 # Next.js/React 의존성 및 npm scripts
├─ package-lock.json            # npm lockfile
├─ next.config.ts
├─ tsconfig.json
├─ eslint.config.mjs
└─ postcss.config.mjs
```

현재 `frontend/lib/api.ts`의 기본 API URL은 `http://127.0.0.1:8001`이다. FastAPI 기본 실행 포트는 `8000`이므로, 실제 데모 실행 시에는 실행 환경의 `NEXT_PUBLIC_API_BASE_URL` 또는 프록시 구성과 함께 확인한다. 이 기본값은 유지한다.

## 5. `configs/` 구조

```text
configs/
├─ base.yaml                    # 기본 런타임 설정
├─ local.yaml                   # 로컬 개발 설정 예시
├─ models.yaml                  # 모델/벡터스토어 설정
├─ CATEGORY_ENUM.yaml           # 카테고리 enum
├─ REGION_MAPPING.yaml          # 지역 매핑
├─ week3_* / week6_*            # 주차별 벤치마크 설정
└─ retrieval_pipelines/
   ├─ baseline_dense.yaml
   ├─ dense_reranked*.yaml
   └─ hybrid_bm25*_rrf*.yaml
```

`app/core/config.py`는 `.env`/환경변수를 직접 읽고, `configs/*.yaml`은 실험과 평가 스크립트에서 주로 사용한다.

## 6. `data/` 구조

```text
data/
├─ demo/                        # UI 데모용 pending cases
├─ raw_data/                    # 원천 민원 데이터
├─ processed/                   # 가공 민원 데이터
├─ chroma_db/                   # ChromaDB persist 디렉터리
├─ evaluation/                  # 평가 corpus/query/qrels/checkpoints
├─ departments/                 # 부서 매핑/마스터 데이터
├─ laws/                        # 법령 사전/조문/조례 데이터
├─ urgency/                     # 긴급도 모델/라벨 데이터
└─ finetune/                    # reranker 등 파인튜닝 데이터
```

`data/chroma_db`는 검색 런타임에 직접 사용되는 persist 디렉터리다. 민원 원문 일부나 metadata가 포함될 수 있으므로 저장소 추적, 공유, 배포 전에 개인정보와 용량 정책을 확인해야 한다.

## 7. `scripts/` 구조

대표 스크립트:

- `run_api.py`: FastAPI 실행
- `run_ui.py`: Streamlit UI 실행
- `build_index.py`: ChromaDB 인덱스 구축
- `inspect_chromadb.py`: ChromaDB/SQLite 진단
- `repair_chromadb_hnsw.py`: ChromaDB HNSW 복구/재생성
- `e2e_api_search_qa.py`, `e2e_be1_query_signals_search_qa.py`: API E2E 점검
- `run_v2_evaluation.py`, `run_v3_evaluation.py`: 검색 평가
- `Be3_run_week6_model_benchmark.py`, `be1_run_week3_model_benchmark.py`: 주차별 모델 벤치마크
- `check_chromadb_*`, `validate_*`, `spotcheck_*`: 데이터/검색/라벨 검증

## 8. API 실행 경계

FastAPI 진입점:

- `app/api/main.py`
- 실행: `python scripts/run_api.py`
- 기본 문서: `http://localhost:8000/docs`

등록 라우터:

- `retrieval_router`: `/api/v1/index`, `/api/v1/search`
- `generation_router`: `/api/v1/qa`
- `ui_router`: `/api/v1/ui/cases`
- `chroma_debug_router`: `/api/v1/chroma/collections`, count/sample 진단

주요 서비스 연결:

```text
/api/v1/search
  -> TopicAnalyzer + ComplexityAnalyzer
  -> AdaptiveRouter
  -> RetrievalService
  -> ChromaVectorStore / HybridRetriever

/api/v1/qa
  -> RetrievalService 또는 전달받은 search_results
  -> context_mapper
  -> GenerationService
  -> PromptFactory + Ollama
  -> response_normalizer + citation validator
```

## 9. UI 실행 경계

신규 UI 기준:

- `frontend/app/page.tsx`: 민원 선택/queue
- `frontend/app/workbench/page.tsx`: 유사 민원 검색, 답변 초안 생성/편집
- `frontend/app/admin/page.tsx`: 관리자 통계 대시보드
- 실행: `npm run dev` 또는 `npm --prefix frontend run dev`

레거시/PoC UI:

- `app/ui/Home.py`
- 실행: `python scripts/run_ui.py`
- 목적: 빠른 PoC, 벤치마크/데모 흐름, 기존 화면 보존

## 10. 문서와 실제 코드의 차이 정리

- 과거 문서의 `web/` 프론트엔드 표기는 현재 실제 디렉터리인 `frontend/`로 읽는다.
- 과거 문서의 `app/api/routers/search.py`, `qa.py` 표기는 현재 `retrieval.py`, `generation.py`로 대체되었다.
- endpoint 명칭은 여전히 `/api/v1/search`, `/api/v1/qa`를 사용한다.
- `app/api/dependencies`, `app/api/middleware`, `app/retrieval/strategies` 같은 디렉터리는 설계 문서에 언급되지만 현재 실제 코드에는 별도 디렉터리로 존재하지 않는다.
- `app/ui`는 삭제 대상이 아니라 Streamlit 레거시/PoC UI로 유지한다.

## 11. 로컬 산출물과 주의 디렉터리

- `civil/`: 로컬 Python 가상환경으로 보인다. 코드 구조로 해석하지 않는다.
- `frontend/node_modules/`, `frontend/.next/`: npm/Next.js 생성물이다.
- `.pytest_cache/`, `__pycache__/`: 테스트/Python 캐시다.
- `logs/`, `reports/`: 실행/평가 산출물이다.
- `.tmp_issue_bodies/`: 이슈 본문 임시 작업물로 보인다.
- `data/chroma_db/`: 로컬 벡터 DB persist 디렉터리다. 용량과 개인정보 노출 가능성을 고려한다.

## 12. 문서-코드 정합성 규칙

- 신규 UI 문서와 작업 지시는 `frontend/` 경로를 사용한다.
- API 계약 필드는 `app/api/schemas`와 `frontend/lib/api.ts`에 같은 의미로 반영한다.
- `routing_trace`, `routing_hint`, `structured_output`, `strategy_id`, `route_key`는 별칭 없이 유지한다.
- Analyzer 출력(`topic_type`, `complexity_level`, `complexity_score`, `complexity_trace`, `request_segments`)은 API/UI에서 같은 의미로 사용한다.
- 기존 Streamlit 경로를 수정할 때는 Next.js Workbench와 책임이 겹치지 않는지 먼저 확인한다.
- 데이터/벡터 DB/로그 산출물은 코드 변경과 분리해서 취급한다.
