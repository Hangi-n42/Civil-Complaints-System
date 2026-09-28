# 기술 스택 — 현재 구현과 회사 지식 제품 계획

> **2026-09-27 병합 상태 보충:** #498에는 K2 지식 자료 API/UI와 파서 의존성 조정이 포함되어 있다. 아래 지식 모듈 부재·패키지 버전 표는 #497 작성 당시 기준이다. 변경 버전과 기존 확인 결과는 [K2 안내](../30_manuals/knowledge_k2_runbook.md) 및 현재 requirements를 따른다.

- 문서 버전: v2.0
- 상태: 현재 코드·의존성 선언 기준
- 기준일: 2026-09-26
- 확인 범위: 선언 파일과 소스의 정적 대조. 설치 패키지 실측·성능·Mac/Windows 실행 인증이 아님.

프로젝트의 메인 제품 기준은 [회사 지식 PRD](company_knowledge_prd.md), [아키텍처](../05_plans/company_knowledge/architecture.md), [구현 설계](../05_plans/company_knowledge/implementation.md)다. 현재 실행 가능한 코드는 민원 활용 시스템이며 `app/knowledge`와 회사 지식 전용 API/UI는 아직 없다. 아래 버전은 현재 선언이며, 신규 제품의 도입 후보가 이미 설치·통합됐다는 의미가 아니다.

## 현재 의존성

| 영역 | 선언·개발 기준 | 기준 파일 |
|---|---|---|
| Python | 개발 기준 3.11.9 | 로컬 개발 정책; 패키지 핀은 `requirements.txt` |
| API·검증 | FastAPI 0.115.12, Uvicorn 0.35.0, Pydantic 2.11.7 | `requirements.txt` |
| 검색 | ChromaDB 1.5.5, bm25s 0.3.9, kiwipiepy 0.23.1 | `requirements.txt` |
| 임베딩 | sentence-transformers 3.4.1, transformers 4.46.3, torch 2.5.1 | `requirements.txt` |
| 수치·데이터 | NumPy 1.26.4, pandas 2.2.3 | `requirements.txt` |
| LLM 접속 | Ollama Python 0.6.1, httpx 0.28.1; Ollama 서버는 외부 프로그램 | `requirements.txt`, 설정 |
| FE | Next.js 16.2.3, React/React DOM 19.2.4 | `frontend/package.json` |
| FE UI | Tailwind ^4, Leaflet ^1.9.4, react-leaflet ^5.0.0 | 동일; 정확한 해석 버전은 lock 파일 |
| 별도 기존 UI | Streamlit 1.44.1 | `app/ui`, `requirements.txt` |
| 확인 도구 | pytest 8.3.5, Vitest ^4.1.9 | Python/FE 선언 파일 |

현재 Next.js 설치 패키지는 Node.js >=20.9.0을 요구한다. 버전 변경이 필요한 신규 라이브러리는 관련 의존성을 함께 조정하고 해당 경로를 확인한다. 단순 버전 충돌만으로 도입 후보를 제외하지 않는다.

## 현재 실행 경계

1. `app/ingestion`, `app/structuring` 및 `app/structuring/pii`: 원천 입력·PII 처리·구조화.
2. `app/retrieval`: Chroma dense와 BM25를 결합한 hybrid 검색. `RETRIEVAL_STRATEGY` 기본값은 `hybrid`다. API는 분석·라우팅 정보를 남기되 검색 `top_k`는 요청값, snippet 1100, chunk policy balanced로 고정하며, 필터가 있으면 서비스의 hybrid 분기를 사용하지 않는다.
3. `app/generation`: 근거 기반 생성·정규화·인용 검증·재작성 흐름.
4. `app/evaluation/civil_llm_rubric.py`: 운영 Q0~Q7 평가. 현재 그룹은 Q2 / Q3·Q4·Q5 / Q1·Q7 / Q6 / Q0의 **5회**이며 같은 요청의 Q2 재사용 시 재평가 모델 호출은 4회다. 실제 성공 호출 수는 오류·설정에 따라 달라질 수 있다.
5. `app/complaint_intelligence`: 급증 알림·공공기관 인사이트·중복 민원 후보 및 담당자 action gate, SQLite read-model. 신규 회사 지식 원장과 같은 저장소로 간주하지 않는다.
6. `frontend`: 케이스 진입, Workbench, Intelligence, 관리자 화면. 기존 `app/ui`의 Streamlit UI는 별도다.

주요 라우터는 `app/api/routers` 아래 retrieval, generation, structuring, ui, admin, complaint_intelligence다. 회사 지식 검색 경로는 [신규 구현 설계](../05_plans/company_knowledge/implementation.md)의 계획이며 현재 API 목록에 포함하지 않는다.

## 모델과 환경 설정

- 생성·재작성: `OLLAMA_MODEL=exaone3.5:7.8b` 기본.
- 운영 평가: `CIVIL_LLM_RUBRIC_MODEL=qwen3.5:4b` 기본.
- 임베딩: `BAAI/bge-m3`, 코드의 장치 기본값 `cpu` (`.env.example`은 `cuda`여서 Mac 로컬 수정 필요).
- PublicAgencyInsight의 fake/Ollama 공급자는 별도 설정이다. `.env.example`은 fake이며 일반 민원 생성 모델 설정만 바꿔도 이 공급자가 자동 전환되는 것은 아니다.
- 루트 `.env`는 `app/core/config.py`에서 로드하며 기존 셸 환경변수가 우선한다.
- API 코드 기본 포트 8000과 FE 기본 8001이 달라 로컬에서 명시적으로 맞춰야 한다.
- FE `npm run dev`의 predev는 replay DB 초기화·분석을 수행한다. 데이터 보존과 DB 경로는 [실행 안내](../30_manuals/local_dev_runbook.md)를 따른다.

## 저장소와 문서 기준

| 위치 | 용도 |
|---|---|
| `data/raw` 또는 기존 `data/raw_data` | 원천 입력 |
| `data/processed` | 가공 민원 입력 |
| `data/chroma_db` | 기본 벡터 저장소 |
| `data/complaint_intelligence` | 관제 seed와 SQLite 데이터 |
| `data/evaluation` | 평가 과제·qrels 등 |
| `reports` | 스크립트의 현재 출력 경로; 과거 실험 기록은 문서 지도에서 별도 확인 |

문서 진입은 [문서 지도](../README.md), 실행은 [runbook](../30_manuals/local_dev_runbook.md), 현재 민원 범위는 [민원 시스템 PRD](complaint_system_prd.md)를 사용한다. 신규 제품의 라이브러리 적용 방식과 마일스톤은 해당 계획 문서가 기준이며 이 파일에 중복 정의하지 않는다.
