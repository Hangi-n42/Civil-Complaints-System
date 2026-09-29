# 로컬 개발 실행 안내 — 현재 민원 시스템

- 문서 버전: v2.0
- 상태: 현재 구현 실행 기준
- 기준일: 2026-09-26
- 확인 범위: 설정·실행 스크립트·의존성 선언을 정적으로 대조. 이번 문서 정리에서 설치, 서버 실행, Windows 실행은 재검증하지 않음.
- 제품의 메인 목표: [회사 지식 PRD](../00_overview/company_knowledge_prd.md). 아래는 현재 존재하는 민원 활용 시스템의 실행법이며 회사 지식 API/UI는 아직 구현 예정이다.

## 1. 실행 환경과 설치

프로젝트 루트에서 실행한다. Python **3.11.9**를 사용하고, Mac과 Windows의 가상환경은 각각 만든다. 가상환경과 개인 `.env`는 공유하거나 커밋하지 않는다. Node.js는 현재 Next.js 패키지가 요구하는 **20.9 이상**을 사용한다.

Mac:

```bash
python3.11 --version  # 3.11.9인지 확인
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env  # 최초 생성 때만; 기존 .env는 덮어쓰지 않는다
npm --prefix frontend ci
```

Windows PowerShell:

```powershell
py -3.11 --version  # 3.11.9인지 확인
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # 최초 생성 때만
npm --prefix frontend ci
```

기존 `civil` 환경을 유지한다면 해당 Python 실행 파일을 대신 사용한다. 버전 선언은 `requirements.txt`와 `frontend/package-lock.json`이 기준이며 위 설치 명령은 새 환경의 설치 성공을 보증한 결과가 아니다.

## 2. 로컬 설정

백엔드는 루트 `.env`를 읽는다. 이미 셸에 설정된 환경변수가 우선한다(`override=False`). 프론트엔드는 별도 `frontend/.env.local`을 사용한다. 다음은 **권장 로컬 예시**이며 개인 설정의 현재값을 의미하지 않는다.

루트 `.env`의 해당 항목:

```dotenv
API_HOST=127.0.0.1
API_PORT=8001
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:31b-it-q4_K_M
STRUCTURING_MODEL=gemma4:31b-it-q4_K_M
CIVIL_STRUCTURING_MODEL=gemma4:31b-it-q4_K_M
CIVIL_LLM_RUBRIC_MODEL=gemma4:31b-it-q4_K_M
KNOWLEDGE_SEARCH_MODEL=gemma4:31b-it-q4_K_M
GROUNDING_FILTER_MODEL=gemma4:31b-it-q4_K_M
PROMETHEUS_FEEDBACK_MODEL=qwen3.8:27b-q4_K_M
PROMETHEUS_REVISION_MODEL=gemma4:31b-it-q4_K_M
OLLAMA_TIMEOUT=180
KNOWLEDGE_DESIGN_TIMEOUT=360
GENERATION_NUM_PREDICT=1536
GENERATION_NUM_CTX=8192
CHROMA_DB_PATH=./data/chroma_db
DEFAULT_CHROMA_COLLECTION=civil_cases_v3
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DEVICE=cpu
COMPLAINT_INTELLIGENCE_REPOSITORY=sqlite
COMPLAINT_INTELLIGENCE_DB_PATH=./data/complaint_intelligence/complaint_intelligence_real_replay.db
```

`frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

- API 코드·`.env.example` 기본 포트는 **8000**, FE 기본 주소는 **8001**이다. 위 예시는 둘을 8001로 맞춘 것이다. 8000을 사용하려면 FE 주소도 8000으로 바꾼다.
- `.env.example`의 `EMBEDDING_DEVICE=cuda`는 Mac에 그대로 적용하지 않는다. 코드 기본값인 `cpu`로 시작하고, 다른 장치는 별도 확인 후 로컬 설정으로만 변경한다.
- `COMPLAINT_INTELLIGENCE_DB_PATH`의 코드 기본 파일은 `complaint_intelligence.db`다. 위 예시는 아래 FE predev가 만드는 **별도 replay DB**에 맞춘 것이다. 실시간 저장소를 쓸 때에는 그 저장소 경로를 유지한다.
- 상대경로와 공통 설정에는 Mac 개인 절대경로를 넣지 않는다. API는 루트에서 시작해 SQLite 상대경로의 실행 위치 차이를 피한다.

## 3. 데이터와 외부 모델

- 원천 자료: `data/raw` (없고 `data/raw_data`가 있으면 설정 코드가 후자를 사용).
- 처리된 민원: `data/processed`.
- 벡터 저장소: `CHROMA_DB_PATH`의 실제 Chroma 데이터와 일치하는 collection이 필요하다. 빈 폴더만 생성하면 검색 자료가 생기지 않는다.
- 관제 replay: `data/complaint_intelligence/complaint_intelligence_real_replay_events.json` 및 대응 SQLite DB.
- 임베딩 모델 `BAAI/bge-m3`의 로컬 캐시가 없으면 최초 사용 시 모델 다운로드가 필요하다.

Ollama 실행 프로그램을 설치·시작하고 다음 모델을 준비한다. 이미 있으면 다시 다운로드할 필요는 없다.

```bash
ollama list
ollama pull gemma4:31b-it-q4_K_M
ollama pull qwen3.8:27b-q4_K_M
```

생성·구조화·평가·지식 작업은 Gemma, 피드백은 Qwen을 사용한다. 재작성의 최종 선택과 한계는 [두 모델 선정 보고서](llm_two_model_selection.md)를 확인한다. 두 모델은 별도 자산이며 Python 패키지 설치에 포함되지 않는다. Ollama 앱이 이미 서버를 실행 중이면 `ollama serve`를 중복 실행하지 않는다.

## 4. API와 프론트엔드 시작

Mac, 루트에서:

```bash
.venv/bin/python scripts/run_api.py
```

Windows PowerShell, 루트에서:

```powershell
.\.venv\Scripts\python.exe scripts\run_api.py
```

별도 터미널에서 프론트엔드를 시작한다. `CIVIL_PYTHON`은 FE **predev용 셸 환경변수**이며 `.env.local`에 넣는 것으로 이 Node 스크립트에 전달되지 않는다.

Mac:

```bash
export CIVIL_PYTHON="$PWD/.venv/bin/python"
npm --prefix frontend run dev
```

Windows PowerShell:

```powershell
$env:CIVIL_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm --prefix frontend run dev
```

**현재 `npm run dev`는 화면만 시작하지 않는다.** `predev`가 processed 입력 또는 기존 seed로 관제 replay를 준비하며, 유효 seed를 확인한 뒤 `complaint_intelligence_real_replay.db`를 초기화·재구성한다. 보고서도 `reports`에 출력한다. 기존 replay DB를 보존해야 하거나 FE만 띄우려면 다음처럼 predev를 거치지 않는다(기존 DB/데이터는 별도 준비되어 있어야 함).

```bash
cd frontend
npx next dev --webpack
```

화면: `http://localhost:3000`의 `/`, `/workbench`, `/intelligence`, `/admin`. 회사 지식 전용 화면은 아직 없다.

## 5. 확인과 문제 해결

위 8001 예시 기준:

```bash
curl http://127.0.0.1:8001/health
```

PowerShell에서는 `Invoke-RestMethod http://127.0.0.1:8001/health`를 사용할 수 있다. `/api/v1/health`와 `http://127.0.0.1:8001/docs`도 제공한다. Health 응답만으로 검색·모델 생성의 정상 동작까지 확인한 것은 아니다.

| 증상 | 먼저 확인할 항목 |
|---|---|
| FE가 API를 못 찾음 | 실행 포트와 `NEXT_PUBLIC_API_BASE_URL`, FE 재시작 |
| 관제 화면이 비어 있음 | API의 DB 경로와 replay가 생성한 DB 경로가 같은지, 필터·모드·자료 적재 여부 |
| predev 실패 | `CIVIL_PYTHON` 및 processed 입력/기존 replay seed 존재 여부 |
| 검색 자료 없음 | Chroma 경로·collection·실제 인덱스 유무 |
| 모델 호출 실패 | Ollama 실행 상태·주소·모델 태그·로컬 자원 |

관련 안내: [Chroma 인덱싱](local_chromadb_indexing.md), [replay 절차](complaint_intelligence_demo_replay.md), [현재 API 계약](../10_contracts/api/current_api_contract.md), [기술 스택](../00_overview/dev_stack.md).

문서만 바꿀 때는 링크와 `git diff --check`를 확인한다. 코드 변경은 영향받는 경로에 한해 확인하며, 위 실행 명령을 문서 검증 명목으로 자동 실행하지 않는다.

K3 반례 검토 모델은 `KNOWLEDGE_REVIEW_MODEL=qwen3.8:27b-q4_K_M`로 지정한다. 민원 평가의 `CIVIL_LLM_RUBRIC_MODEL`과 독립적이며 새 K3 실행부터 적용된다.
