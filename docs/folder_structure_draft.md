# 폴더 구조 초안

문서 버전: v1.0  
기준 문서: [prd_draft.md](../prd_draft.md), [MVP 범위 문서](mvp_scope.md), [8주 WBS 문서](wbs_8weeks.md)  
작성일: 2026-03-11

## 1. 문서 목적

본 문서는 프로젝트의 초기 디렉토리 구조와 모듈 책임을 정의한다.  
목표는 다음과 같다.

- 팀원이 같은 위치에 같은 종류의 코드를 배치하도록 기준 제공
- ingestion / structuring / retrieval / generation / ui 모듈 경계 고정
- API, 데이터, 평가, 문서를 분리해 유지보수성을 높임
- 후반 통합 단계에서 파일 위치 혼란을 줄임

## 2. 설계 원칙

### 2.1 원칙
- 기능 축이 다른 코드는 디렉토리로 분리한다.
- 데모용 UI와 API 서버는 분리하되, 공통 서비스 레이어를 공유한다.
- 데이터 원본, 중간 산출물, 평가 결과는 섞지 않는다.
- 스키마와 설정은 코드보다 먼저 찾을 수 있는 위치에 둔다.
- 로그와 실험 결과는 재현 가능하도록 저장 위치를 고정한다.

### 2.2 모듈 경계
- `ingestion`: 로더, 정제, 익명화, 중복 탐지
- `structuring`: 4요소 추출, NER, 스키마 검증
- `retrieval`: 청킹, 임베딩, 인덱싱, 검색
- `generation`: 프롬프트, RAG, citation, 파싱 재시도
- `ui`: Streamlit 화면 및 사용자 상호작용

## 3. 추천 루트 구조

```text
AI-Civil-Affairs-Systems/
├─ README.md
├─ prd_draft.md
├─ prompt.md
├─ docs/
│  ├─ prd_draft.md
│  ├─ prompt.md
│  ├─ mvp_scope.md
│  ├─ wbs_8weeks.md
│  ├─ folder_structure_draft.md
│  ├─ api_spec.md
│  ├─ schema_contract.md
│  ├─ demo_scenarios.md
│  └─ evaluation_plan.md
├─ app/
│  ├─ api/
│  │  ├─ main.py
│  │  ├─ routers/
│  │  │  ├─ ingest.py
│  │  │  ├─ structure.py
│  │  │  ├─ index.py
│  │  │  ├─ search.py
│  │  │  ├─ qa.py
│  │  │  └─ health.py
│  │  ├─ schemas/
│  │  │  ├─ ingest.py
│  │  │  ├─ structure.py
│  │  │  ├─ search.py
│  │  │  └─ qa.py
│  │  └─ dependencies/
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ logging.py
│  │  ├─ exceptions.py
│  │  └─ utils.py
│  ├─ ingestion/
│  │  ├─ loaders/
│  │  │  ├─ csv_loader.py
│  │  │  ├─ json_loader.py
│  │  │  └─ manual_input.py
│  │  ├─ preprocess/
│  │  │  ├─ cleaner.py
│  │  │  ├─ pii_masker.py
│  │  │  └─ deduplicator.py
│  │  └─ service.py
│  ├─ structuring/
│  │  ├─ extractors/
│  │  │  ├─ four_part_extractor.py
│  │  │  └─ ner_extractor.py
│  │  ├─ validators/
│  │  │  └─ schema_validator.py
│  │  ├─ postprocess/
│  │  │  └─ rule_corrector.py
│  │  └─ service.py
│  ├─ retrieval/
│  │  ├─ chunking/
│  │  │  └─ chunker.py
│  │  ├─ embeddings/
│  │  │  └─ embedder.py
│  │  ├─ vectorstores/
│  │  │  ├─ chroma_store.py
│  │  │  └─ faiss_store.py
│  │  ├─ search/
│  │  │  ├─ retriever.py
│  │  │  └─ filters.py
│  │  └─ service.py
│  ├─ generation/
│  │  ├─ llm/
│  │  │  └─ ollama_client.py
│  │  ├─ prompts/
│  │  │  ├─ structure_prompt.txt
│  │  │  └─ qa_prompt.txt
│  │  ├─ parsing/
│  │  │  ├─ json_parser.py
│  │  │  └─ retry_handler.py
│  │  ├─ citation/
│  │  │  └─ citation_builder.py
│  │  └─ service.py
│  ├─ ui/
│  │  ├─ Home.py
│  │  ├─ pages/
│  │  │  ├─ 1_Upload_and_Structure.py
│  │  │  ├─ 2_Search_and_QA.py
│  │  │  └─ 3_Admin_Dashboard.py
│  │  ├─ components/
│  │  │  ├─ upload_form.py
│  │  │  ├─ result_card.py
│  │  │  ├─ citation_viewer.py
│  │  │  └─ status_banner.py
│  │  └─ services/
│  │     └─ api_client.py
│  └─ tests/
│     ├─ unit/
│     ├─ integration/
│     └─ fixtures/
├─ data/
│  ├─ raw/
│  ├─ interim/
│  ├─ processed/
│  ├─ annotations/
│  └─ samples/
├─ schemas/
│  ├─ civil_case.schema.json
│  ├─ search_result.schema.json
│  └─ qa_response.schema.json
├─ scripts/
│  ├─ run_api.py
│  ├─ run_ui.py
│  ├─ build_index.py
│  ├─ evaluate_structuring.py
│  ├─ evaluate_retrieval.py
│  └─ evaluate_qa.py
├─ configs/
│  ├─ base.yaml
│  ├─ local.yaml
│  └─ models.yaml
├─ logs/
│  ├─ api/
│  ├─ pipeline/
│  └─ evaluation/
├─ artifacts/
│  ├─ reports/
│  ├─ figures/
│  └─ demo/
├─ .env.example
├─ requirements.txt
└─ .gitignore
```

## 4. 디렉토리별 책임

### 루트 파일

| 경로 | 역할 |
| --- | --- |
| `README.md` | 실행 방법, 환경 설정, 프로젝트 개요 |
| `prd_draft.md` | 상위 요구사항 기준 문서 |
| `prompt.md` | 멘토 에이전트 운영 프롬프트 |
| `.env.example` | 필수 환경 변수 샘플 |
| `requirements.txt` | Python 의존성 목록 |

### `docs/`

기획 및 운영 문서를 저장한다.

- PRD 보완 문서
- API 명세
- 스키마 계약
- 데모 시나리오
- 평가 계획
- 회고 및 의사결정 기록

### `app/api/`

FastAPI 서버 진입점과 라우터를 관리한다.

- `main.py`: 앱 생성, 라우터 등록, 미들웨어 설정
- `routers/`: 엔드포인트별 분리
- `schemas/`: Pydantic 요청/응답 모델
- `dependencies/`: 공통 의존성 주입

### `app/core/`

모든 모듈이 공유하는 공통 인프라를 둔다.

- 설정 로딩
- 공통 로거
- 예외 정의
- 범용 유틸리티

### `app/ingestion/`

입력 데이터 수집과 정제를 담당한다.

- CSV/JSON/수동 입력 파싱
- 문자열 정제
- 개인정보 마스킹
- 중복 탐지

### `app/structuring/`

민원 원문을 구조화된 JSON으로 변환한다.

- 4요소 추출
- NER 추출
- 룰 기반 보정
- 스키마 검증

### `app/retrieval/`

검색 품질과 속도에 직접 영향을 주는 모듈이다.

- 청킹 전략
- 임베딩 생성
- 벡터 저장소 연동
- 검색 및 필터링

### `app/generation/`

RAG 응답 생성 및 citation 정합성을 담당한다.

- Ollama 호출
- 프롬프트 관리
- JSON 파싱
- 파싱 실패 재시도
- citation 생성

### `app/ui/`

Streamlit 화면과 사용자 상호작용을 담당한다.

- 업로드 화면
- 검색/QA 화면
- 관리자 대시보드
- 공통 UI 컴포넌트
- API 호출 클라이언트

### `app/tests/`

테스트 코드를 계층별로 분리한다.

- `unit/`: 단일 함수/클래스 테스트
- `integration/`: API와 파이프라인 연결 테스트
- `fixtures/`: 샘플 데이터 및 테스트 입력

### `data/`

데이터 수명주기 단계를 구분한다.

| 경로 | 용도 |
| --- | --- |
| `raw/` | 원본 민원 데이터 |
| `interim/` | 전처리 중간 결과 |
| `processed/` | 구조화 완료 데이터 |
| `annotations/` | 정답셋/라벨링 결과 |
| `samples/` | 데모/개발용 소형 샘플 |

### `schemas/`

실제 저장 및 교환되는 JSON 스키마를 둔다.

- 구조화 민원
- 검색 결과
- QA 응답

이 디렉토리는 API의 Pydantic 모델과 별개로, 데이터 계약의 기준점 역할을 한다.

### `scripts/`

실행 및 평가용 스크립트를 둔다.

- 서버 실행
- UI 실행
- 인덱스 빌드
- 구조화 평가
- 검색 평가
- QA 평가

### `configs/`

환경별 설정과 모델 설정을 분리한다.

- `base.yaml`: 공통 설정
- `local.yaml`: 로컬 머신 설정
- `models.yaml`: 임베딩/LLM/벡터DB 설정

### `logs/`

로그는 목적별로 분리 저장한다.

- `api/`: 요청/응답, 에러
- `pipeline/`: 전처리/구조화/인덱싱 로그
- `evaluation/`: 평가 결과 로그

### `artifacts/`

발표와 실험 결과물을 저장한다.

- `reports/`: KPI 보고서
- `figures/`: 그래프, 시각화 결과
- `demo/`: 발표용 샘플 출력, 스크린샷

## 5. API와 서비스 계층 분리 기준

### 원칙
- 라우터는 요청/응답 처리만 담당한다.
- 실제 로직은 각 도메인 `service.py`에 둔다.
- 도메인 간 호출은 가능한 서비스 레이어를 통해 수행한다.

### 예시 흐름
- `/structure` 요청 → `app/api/routers/structure.py`
- 서비스 호출 → `app/structuring/service.py`
- 검증 호출 → `app/structuring/validators/schema_validator.py`
- 결과 반환 → API 스키마로 직렬화

이 구조를 지키면 테스트와 리팩터링이 쉬워진다.

## 6. 초기 생성 우선순위

### 반드시 먼저 만들어야 하는 디렉토리
- `app/api/`
- `app/core/`
- `app/ingestion/`
- `app/structuring/`
- `app/retrieval/`
- `app/generation/`
- `app/ui/`
- `data/samples/`
- `schemas/`
- `configs/`

### 1차 파일 우선 생성 목록
- `app/api/main.py`
- `app/core/config.py`
- `app/ingestion/service.py`
- `app/structuring/service.py`
- `app/retrieval/service.py`
- `app/generation/service.py`
- `app/ui/Home.py`
- `schemas/civil_case.schema.json`
- `.env.example`
- `requirements.txt`

## 7. 팀 역할 매핑

| 역할 | 주 책임 디렉토리 | 협업 디렉토리 |
| --- | --- | --- |
| FE | `app/ui/` | `app/api/`, `docs/` |
| BE-A | `app/ingestion/`, `app/structuring/`, `schemas/` | `data/`, `scripts/` |
| BE-B | `app/retrieval/`, `scripts/`, `artifacts/` | `data/`, `schemas/` |
| BE-C | `app/api/`, `app/generation/`, `app/core/`, `configs/` | `app/retrieval/`, `docs/` |

## 8. 파일 네이밍 규칙

- Python 파일은 소문자 + snake_case 사용
- Streamlit 페이지는 정렬용 숫자 prefix 사용
- 스키마 파일은 `.schema.json` 접미사 사용
- 평가 스크립트는 `evaluate_*.py` 형식 사용
- 실행 스크립트는 `run_*.py` 또는 동사형 이름 사용

## 9. 지금 구조에서 주의할 점

- `Civil/`은 현재 가상환경 디렉토리로 보이며, 애플리케이션 소스와 분리 유지하는 것이 맞다.
- 실제 프로젝트 코드는 가상환경 내부가 아니라 루트의 `app/` 아래에 생성해야 한다.
- 문서, 코드, 데이터, 산출물을 섞지 않도록 초기부터 경계를 지켜야 한다.

## 10. 권장 다음 단계

1. 이 구조를 기준으로 실제 디렉토리 생성
2. `api_spec.md` 작성
3. `schema_contract.md` 작성
4. `requirements.txt` 초안 정리
5. `app/api/main.py`와 각 도메인 `service.py` 골격 생성

## 11. 결론

이 폴더 구조 초안의 목적은 “예쁘게 보이는 구조”가 아니라, **4인 팀이 8주 동안 충돌 없이 병렬 개발하고, 후반에 안정적으로 통합할 수 있는 구조**를 만드는 것이다.  
따라서 초기에는 단순하되, `ingestion / structuring / retrieval / generation / ui`의 경계만큼은 반드시 유지해야 한다.
