# 로컬 개발 실행 Runbook

- 문서 상태: runbook
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `scripts/run_api.py`
  - `app/api/main.py`
  - `frontend/package.json`
  - `frontend/lib/api.ts`
- 관련 문서:
  - `docs/00_overview/dev_stack.md`
  - `docs/10_contracts/api/current_api_contract.md`

## 1. 사전 준비

권장 Python 실행기는 repo venv입니다.

```powershell
civil\Scripts\python.exe --version
```

프론트엔드는 `frontend/package.json` 기준으로 npm dependency를 설치합니다.

```powershell
npm --prefix frontend install
```

## 2. Backend 실행

```powershell
civil\Scripts\python.exe scripts\run_api.py
```

확인 endpoint:

- `GET /health`
- `GET /api/v1/health`
- FastAPI docs: `http://localhost:8000/docs`

확인 필요:

- 일부 FE 설정은 기본 API URL을 `http://127.0.0.1:8001`로 둘 수 있습니다. backend 포트가 다르면 `NEXT_PUBLIC_API_BASE_URL`을 맞춥니다.

## 3. Frontend 실행

```powershell
npm --prefix frontend run dev
```

주요 화면:

- `/`: case 선택/진입
- `/workbench`: 검색/QA Workbench
- `/intelligence`: 민원 인텔리전스 dashboard
- `/admin`: 관리자 통계

## 4. 기본 API smoke

```powershell
curl http://localhost:8000/health
```

Search/QA는 환경에 ChromaDB와 index가 준비되어 있어야 합니다.

## 5. 흔한 문제

### FE가 API를 못 찾는 경우

- backend 실행 포트와 `NEXT_PUBLIC_API_BASE_URL`이 일치하는지 확인합니다.
- `frontend/lib/api.ts`의 기본값은 `http://127.0.0.1:8001`입니다.

### Intelligence dashboard가 비어 있는 경우

- read-model이 비어 있으면 정상입니다.
- `docs/30_manuals/complaint_intelligence_demo_replay.md` 절차로 seed/replay를 적재합니다.

### ChromaDB 관련 오류

- `docs/30_manuals/local_chromadb_indexing.md`
- `docs/30_manuals/chromadb_lfs_policy.md`

## 6. 검증 원칙

문서 변경만 하더라도 최소 다음을 확인합니다.

```powershell
git diff --check
```

코드 변경이 있을 때는 관련 pytest를 별도로 실행합니다.
