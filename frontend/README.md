# 민원 활용 프론트엔드

- 문서 버전: v2.0
- 상태: 현재 구현 실행 안내
- 기준일: 2026-09-26
- 확인 범위: package.json·API client·predev·화면 파일 정적 확인. 이번 문서 수정에서 dev/build/테스트는 실행하지 않음.

프로젝트의 주 제품은 [회사 지식 온톨로지·지식그래프](../docs/00_overview/company_knowledge_prd.md)이며, 이 디렉터리는 현재 구현된 민원 활용 UI다. 회사 지식 전용 UI와 Local/Global 검색 화면은 구현 예정이다.

## 실행

Next.js 16.2.3 / React 19.2.4를 사용한다. Node.js >=20.9.0, Python 3.11.9 환경을 준비하고 저장소 루트에서:

```bash
npm --prefix frontend ci
```

`frontend/.env.local`에 실제 API 주소를 설정한다:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001
```

FE 코드 기본값은 8001, 백엔드 코드 기본값은 8000이다. 루트 `.env`의 `API_PORT`와 맞춰야 한다. Python 의존성·Ollama·Chroma·DB 준비 및 API 실행은 [로컬 개발 안내](../docs/30_manuals/local_dev_runbook.md)를 따른다.

Mac (루트):

```bash
export CIVIL_PYTHON="$PWD/.venv/bin/python"
npm --prefix frontend run dev
```

Windows PowerShell (루트):

```powershell
$env:CIVIL_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
npm --prefix frontend run dev
```

`CIVIL_PYTHON`은 셸에 설정한다. predev Node 스크립트는 Next.js의 `.env.local`을 직접 읽지 않는다.

**`npm run dev`는 predev에서 관제 replay DB를 초기화·재구성한다.** `scripts/prepareComplaintIntelligenceReplay.mjs`가 processed 입력 또는 기존 replay seed를 사용해 Python 준비 스크립트를 실행한다. 대상 DB는 기본적으로 `data/complaint_intelligence/complaint_intelligence_real_replay.db`이며 API의 `COMPLAINT_INTELLIGENCE_DB_PATH`와 별도로 정해진다. 같은 replay를 보려면 API도 해당 파일을 사용해야 한다.

기존 데이터와 API를 그대로 두고 화면만 시작하려면:

```bash
cd frontend
npx next dev --webpack
```

이 경로는 replay 준비를 생략한다. 최초 데이터가 없다면 관제 화면 자료를 따로 준비해야 한다.

## 화면과 연결 코드

| 경로 | 현재 기능 |
|---|---|
| `/` | 민원 케이스 선택·진입 |
| `/workbench` | 검색 결과와 QA 답변 초안 |
| `/intelligence` | 관제 대시보드·급증·인사이트·중복 민원 |
| `/admin` | 관리자 통계 |

개발 주소는 `http://localhost:3000`이다. `lib/api.ts`가 API 주소와 호출·응답 변환을 담당하고 `lib/draft.ts`가 초안 관련 처리를 담당한다. 페이지 진입점은 `app/` 아래에 있다.

## 스크립트

| 명령 (`frontend`에서) | 용도 |
|---|---|
| `npm run dev` | replay 준비 후 webpack 개발 서버 |
| `npm run build` | 배포 빌드 |
| `npm start` | 빌드된 Next.js 서버 |
| `npm run lint` | ESLint |
| `npm test` | Vitest 단회 실행 |
| `npm run test:watch` | Vitest 감시 모드 |

문서만 수정할 때 이 명령들을 모두 실행할 필요는 없다. FE를 변경할 때에는 영향받는 테스트와 필요한 빌드 확인만 수행한다. Next.js 코드를 수정하기 전에는 [AGENTS.md](AGENTS.md)와 설치된 `node_modules/next/dist/docs/`의 관련 가이드를 확인한다.

[프로젝트 문서 지도](../docs/README.md) · [회사 지식 구현 설계](../docs/05_plans/company_knowledge/implementation.md) · [회사 지식 마일스톤](../docs/05_plans/company_knowledge/milestones.md)
