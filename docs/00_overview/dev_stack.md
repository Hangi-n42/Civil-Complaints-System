# 개발 기술 스택 가이드 (dev_stack)

문서 버전: v1.1  
작성일: 2026-03-11  
최신화: 2026-03-20 (ChromaDB/LangChain 계열 버전 상향 반영)  
대상 프로젝트: AI Civil Affairs Systems (Python 3.11.9)

---

## 1) 문서 목적

이 문서는 아래를 한 번에 정리합니다.

- 우리 프로젝트에서 사용하는 **필수 기술 스택**
- 기능별로 **어떤 스택이 어디에 들어가는지**
- 각 스택이 **왜 필요한지(선정 이유)**
- 개발/운영 단계에서의 **실무 체크 포인트**

즉, 팀원이 새로 합류해도 이 문서만 보면 바로 작업을 시작할 수 있도록 만든 안내서입니다.

---

## 2) 한눈에 보는 아키텍처와 스택 배치

### 전체 흐름

입수(Ingestion) → 구조화(Structuring) → 인덱싱/검색(Retrieval) → 답변 생성(QA) → UI

### 레이어별 핵심 스택

- API 레이어: `FastAPI`, `Uvicorn`, `Pydantic`
- UI 레이어: `Streamlit`
- 임베딩/검색 레이어: `sentence-transformers`, `torch`, `transformers`, `ChromaDB`
- 생성 레이어: `Ollama`, `LangChain`
- 데이터/설정/유틸: `pandas`, `numpy`, `pyyaml`, `python-dotenv`, `httpx`
- 품질/개발 생산성: `pytest`, `black`, `flake8`, `mypy`

---

## 3) 현재 기준 버전(고정)

기준 파일: [requirements.txt](../requirements.txt)

- fastapi==0.115.12
- uvicorn[standard]==0.35.0
- pydantic==2.11.7
- pydantic-settings==2.10.1
- streamlit==1.44.1
- chromadb==1.5.5
- sentence-transformers==3.4.1
- torch==2.5.1
- transformers==4.46.3
- tokenizers==0.20.3
- ollama==0.6.1
- langchain==1.0.0
- langchain-chroma==1.1.0
- langchain-core==1.2.20
- langchain-text-splitters==1.0.0
- pandas==2.2.3
- numpy==1.26.4
- pyyaml==6.0.2
- requests==2.32.3
- httpx==0.28.1
- python-json-logger==3.3.0
- pytest==8.3.5
- pytest-asyncio==0.25.3
- black==25.1.0
- flake8==7.1.2
- mypy==1.15.0
- python-dotenv==1.0.1

> 참고: Python 3.11.9 환경에서 `pip install --dry-run -r requirements.txt` 기준 의존성 해석 검증을 완료한 조합입니다.

---

## 4) 기능별 상세 매핑 (무엇을, 왜)

## 4.1 API 서버 / 인터페이스

**적용 기능**
- `/health`, `/ingest`, `/structure`, `/index`, `/search`, `/qa` 엔드포인트 제공
- 요청/응답 검증
- 서비스 모듈과 UI 사이의 안정적 인터페이스

**사용 스택**
- `FastAPI`: 비동기 API 프레임워크
- `Uvicorn`: ASGI 서버 실행 엔진
- `Pydantic`, `pydantic-settings`: 스키마 검증 및 설정 관리
- `httpx`/`requests`: 외부 서비스(Ollama 등) 호출

**왜 필요한가**
- FastAPI는 타입 힌트 기반 검증과 문서화(`/docs`)가 강력해서 팀 협업 시 인터페이스 충돌을 줄입니다.
- Pydantic으로 데이터 계약을 강제하면, 모듈 간 JSON 형식 불일치를 초기에 차단할 수 있습니다.
- Uvicorn은 가볍고 빠르며 로컬/데모 운영에 적합합니다.

**연결 파일**
- [app/api/main.py](../app/api/main.py)
- [scripts/run_api.py](../scripts/run_api.py)
- [app/core/config.py](../app/core/config.py)

---

## 4.2 데이터 입수/전처리 (Ingestion)

**적용 기능**
- CSV/JSON 로드
- 텍스트 정제(공백/특수문자 정리)
- 개인정보 마스킹(PII)
- 중복 제거

**사용 스택**
- `pandas`: CSV/표 구조 데이터 처리
- `numpy`: 수치 처리 및 보조 연산
- `pydantic`: 입수 데이터 형식 검증

**왜 필요한가**
- 민원 데이터는 입력 원천이 다양하고 노이즈가 많아서 전처리 품질이 전체 성능의 출발점입니다.
- pandas는 대량 레코드 처리 속도와 코드 가독성 균형이 좋아 초기 MVP에 적합합니다.

**연결 파일**
- [app/ingestion/service.py](../app/ingestion/service.py)

---

## 4.3 구조화 (Structuring)

**적용 기능**
- 4요소 추출(예: 당사자/청구취지/원인/증빙)
- 개체명 인식 결과 정리
- 신뢰도 점수 계산
- 스키마 검증

**사용 스택**
- `Ollama`: 온디바이스 LLM 실행
- `LangChain`: 프롬프트 체인 구성, 후처리 보조
- `Pydantic`: 구조화 출력 스키마 강제

**왜 필요한가**
- 온디바이스 요구사항(개인정보/비용/오프라인 대응)에 맞추려면 Ollama 기반 로컬 추론이 필요합니다.
- 구조화 단계에서 스키마를 엄격히 강제해야 검색/QA 단계가 안정적으로 동작합니다.

**연결 파일**
- [app/structuring/service.py](../app/structuring/service.py)
- [schemas/civil_case.schema.json](../schemas/civil_case.schema.json)

---

## 4.4 벡터 인덱싱/검색 (Retrieval)

**적용 기능**
- 문서 청킹
- 임베딩 생성
- 벡터 인덱싱
- Top-K 검색 + 메타데이터 필터

**사용 스택**
- `sentence-transformers`: 임베딩 모델 로딩/추론
- `torch`: 모델 추론 백엔드(CPU/GPU)
- `transformers`, `tokenizers`: 모델/토크나이징 호환 계층
- `chromadb`: 벡터 저장소/검색 엔진
- `numpy`: 유사도/벡터 연산 보조

**왜 필요한가**
- 검색 품질은 RAG 전체 성능의 핵심입니다. 임베딩 품질 + 벡터DB 설계가 직접적으로 `Recall@K`를 좌우합니다.
- ChromaDB는 로컬 개발과 빠른 PoC에 유리하며, 유지보수 복잡도가 낮습니다.
- `torch/transformers/tokenizers`를 명시 고정하면 설치 백트래킹/충돌을 줄여 재현성이 높아집니다.

**연결 파일**
- [app/retrieval/service.py](../app/retrieval/service.py)
- [scripts/build_index.py](../scripts/build_index.py)

---

## 4.5 답변 생성 (RAG QA)

**적용 기능**
- 검색 결과를 컨텍스트로 프롬프트 구성
- LLM 답변 생성
- JSON 파싱/재시도
- citation(근거) 생성

**사용 스택**
- `Ollama`: 로컬 LLM 추론
- `LangChain`: 프롬프트 구성/체인화
- `httpx`: 비동기 호출(필요 시)
- `Pydantic`: 응답 JSON 구조 검증

**왜 필요한가**
- QA는 단순 생성이 아니라, 근거(citation)와 제한사항까지 반환해야 신뢰 가능한 민원 보조 시스템이 됩니다.
- 파싱 실패 대비 재시도/검증 로직이 없으면 데모 및 실제 사용에서 실패율이 급증합니다.

**연결 파일**
- [app/generation/service.py](../app/generation/service.py)

---

## 4.6 UI / 사용자 경험

**적용 기능**
- 업로드 탭
- 검색 탭
- 채팅(QA) 탭
- 상태/에러 메시지 표시

**사용 스택**
- `Streamlit`: 빠른 프로토타이핑과 데모 친화 UI

**왜 필요한가**
- 졸업 프로젝트 일정(8주)에서 Streamlit은 프론트 개발 속도가 매우 빠르고, 데이터/ML 파이프라인 데모에 강점이 있습니다.
- MVP 단계에서 “완전한 프론트 프레임워크”보다 기능 검증 속도가 중요합니다.

**연결 파일**
- [app/ui/Home.py](../app/ui/Home.py)
- [scripts/run_ui.py](../scripts/run_ui.py)

---

## 4.7 설정/환경/운영

**적용 기능**
- 환경변수 관리
- YAML 설정 분리(base/local/models)
- 실행 환경별 토글

**사용 스택**
- `python-dotenv`: `.env` 로딩
- `pyyaml`: YAML 설정 파일 파싱
- `pydantic-settings`: 타입 안전 설정 객체화

**왜 필요한가**
- 모델/포트/경로를 코드에 하드코딩하면 팀원별 환경 차이로 장애가 반복됩니다.
- 설정 분리는 재현성과 디버깅 속도를 동시에 높입니다.

**연결 파일**
- [configs/base.yaml](../configs/base.yaml)
- [configs/local.yaml](../configs/local.yaml)
- [configs/models.yaml](../configs/models.yaml)
- [app/core/config.py](../app/core/config.py)

---

## 4.8 로깅/관측성

**적용 기능**
- API 로그
- 파이프라인 로그
- 평가 로그

**사용 스택**
- `python-json-logger`
- Python 표준 `logging`

**왜 필요한가**
- 성능 저하/파싱 실패/데이터 누락 이슈를 재현하려면 구조화된 로그가 필수입니다.
- 주차별 KPI 리포트(응답시간, 실패율) 작성 근거로 활용됩니다.

**연결 파일**
- [app/core/logging.py](../app/core/logging.py)

---

## 4.9 테스트/품질

**적용 기능**
- 단위/통합 테스트
- 비동기 테스트
- 정적 품질 점검

**사용 스택**
- `pytest`, `pytest-asyncio`
- `black`, `flake8`, `mypy`

**왜 필요한가**
- 4인 병렬 개발에서는 코드 스타일/타입/비동기 동작이 자주 깨집니다.
- 자동 점검이 있어야 Week 5 이후 통합 속도가 떨어지지 않습니다.

**연결 파일/폴더**
- [app/tests](../app/tests)
- [scripts/evaluate_structuring.py](../scripts/evaluate_structuring.py)
- [scripts/evaluate_retrieval.py](../scripts/evaluate_retrieval.py)
- [scripts/evaluate_qa.py](../scripts/evaluate_qa.py)

---

## 5) 기능별 “필수/권장/선택” 스택 요약

| 기능 | 필수 스택 | 권장 스택 | 선택 스택 |
| --- | --- | --- | --- |
| API | FastAPI, Uvicorn, Pydantic | pydantic-settings, httpx | requests |
| 입수/전처리 | pandas | numpy | - |
| 구조화 | Ollama, Pydantic | LangChain | - |
| 검색 | sentence-transformers, ChromaDB | torch, transformers, tokenizers | numpy |
| QA | Ollama, LangChain | httpx, Pydantic | - |
| UI | Streamlit | - | - |
| 설정/운영 | python-dotenv, pyyaml | pydantic-settings | - |
| 품질 | pytest | mypy, flake8, black | - |

---

## 6) 실무 운영 가이드 (중요)

### 6.1 성능 관련
- `EMBEDDING_DEVICE`는 GPU가 없으면 `cpu`로 고정한다.
- 대량 테스트 전에는 `BATCH_SIZE`를 보수적으로 시작(예: 8~16) 후 점진적으로 올린다.
- 목표 지표는 WBS 기준으로 관리한다.
  - 구조화 F1 >= 0.70
  - 검색 Recall@5 >= 0.60
  - QA 응답 <= 5초

### 6.2 안정성 관련
- LLM 응답은 항상 JSON 파싱 + 예외 처리 + 재시도 로직으로 감싼다.
- API 경계에서 입력/출력 스키마를 엄격히 검사한다.
- 검색/QA 단계는 실패 시 사용자에게 제한사항을 명확히 반환한다.

### 6.3 버전 관리 원칙
- `requirements.txt`는 핀 고정 유지(재현성 우선).
- 대규모 업그레이드는 주차 마일스톤 종료 시점(예: W2 끝)에서만 수행.
- 핵심 전이 의존성(`torch/transformers/tokenizers`)은 함께 검증 후 반영.

---

## 7) 지금 팀이 바로 해야 할 적용 순서

1. API/ UI 스모크 테스트를 주기적으로 유지한다.  
2. Week 2에서 Priority 2~5 PoC를 병렬 진행한다.  
3. 평가 스크립트에 최소 지표 계산을 먼저 붙인다.  
4. Week 3부터는 기능 추가보다 E2E 연결 안정화에 우선순위를 둔다.

---

## 8) 결론

현재 스택은 **온디바이스 제약 + 8주 일정 + 4인 병렬 개발** 조건에서,

- 개발 속도,
- 성능,
- 재현성,
- 데모 안정성

사이의 균형이 좋은 조합입니다.

핵심은 “최신 버전” 자체보다, **검증된 호환 조합을 유지하며 기능별 KPI를 달성하는 것**입니다.
