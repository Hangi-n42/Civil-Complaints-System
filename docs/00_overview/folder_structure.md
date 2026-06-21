# 프로젝트 폴더 구조

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/api/main.py`
  - `app/api/routers/`
  - `app/complaint_intelligence/`
  - `frontend/app/`
  - `frontend/components/intelligence/`
  - `scripts/`
  - `data/`
  - `reports/`
- 관련 문서:
  - `docs/00_overview/architecture.md`
  - `docs/10_contracts/README.md`
  - `docs/30_manuals/README.md`

## 최상위 구조

```text
AI-Civil-Affairs-Systems/
├─ app/                         # FastAPI 백엔드와 도메인 파이프라인
├─ frontend/                    # Next.js 기반 Workbench/Intelligence UI
├─ configs/                     # 모델, retrieval pipeline, category/region 설정
├─ data/                        # demo, replay, processed, evaluation, ChromaDB 데이터
├─ docs/                        # 프로젝트 문서
├─ reports/                     # 평가, 검증, 시각화 산출물
├─ scripts/                     # 인덱싱, seed, replay, 평가, 진단 스크립트
├─ schemas/                     # JSON Schema 원본 또는 보조 스키마
├─ requirements.txt             # Python 의존성
├─ frontend/package.json        # Next.js 의존성 및 npm scripts
└─ .env.example                 # 환경변수 예시
```

## `app/` 백엔드 구조

```text
app/
├─ api/
│  ├─ main.py                   # FastAPI 앱 진입점
│  ├─ error_utils.py            # 공통 오류 응답 유틸
│  ├─ schemas/                  # retrieval, generation, structuring API 스키마
│  └─ routers/
│     ├─ retrieval.py           # /api/v1/index, /api/v1/search
│     ├─ generation.py          # /api/v1/qa, /api/v1/qa/stream
│     ├─ complaint_intelligence.py # 관제형 민원 인텔리전스 API
│     ├─ structuring.py         # 단건 구조화 API
│     ├─ ui.py                  # Workbench용 case API
│     ├─ admin.py               # 관리자 통계 API
│     └─ chroma_debug.py        # ChromaDB 진단 API
├─ core/                        # 설정, 로깅, 공통 예외
├─ ingestion/                   # 원천 데이터 로딩/전처리
├─ structuring/                 # observation/result/request/context 4요소 구조화
├─ retrieval/                   # ChromaDB, hybrid search, router, analyzers
├─ generation/                  # QA 생성, prompt, JSON parsing, citation validation
├─ complaint_intelligence/      # IssueAlert, PublicAgencyInsight, Duplicate Merge sidecar
└─ tests/                       # unit/integration test
```

## `app/complaint_intelligence/` 구조

```text
app/complaint_intelligence/
├─ service.py                   # 분석 실행, 저장소 연동, dashboard read-model 진입점
├─ schemas.py                   # ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight
├─ repository.py                # repository interface, in-memory repository
├─ sqlite_repository.py         # SQLite repository 구현
├─ scheduler.py                 # 단일 프로세스 scheduler
├─ collector.py                 # collector interface, noop/repository replay collector
├─ config.py                    # Complaint Intelligence 설정
├─ pii.py                       # PII masking
├─ issue_detection/
│  └─ engine.py                 # IssueAlert 감지 엔진
├─ public_insights/
│  ├─ service.py                # EvidencePack 기반 PublicAgencyInsight orchestration
│  ├─ candidate_generator.py
│  ├─ evidence_pack.py
│  ├─ aspect_extractor.py
│  ├─ llm_provider.py
│  ├─ llm_synthesizer.py
│  ├─ grounding_verifier.py
│  ├─ quality_gate.py
│  ├─ action_catalog.py
│  ├─ action_rubric.py
│  └─ action_repair.py
└─ duplicate_merger/
   ├─ candidate_generator.py
   ├─ scoring.py
   ├─ merge_verifier.py
   ├─ representative_selector.py
   ├─ draft_payload.py
   ├─ reply_context.py
   ├─ reply_safety.py
   ├─ service.py
   └─ schemas.py
```

## `frontend/` 구조

```text
frontend/
├─ app/
│  ├─ page.tsx                  # 민원 선택/queue 진입 화면
│  ├─ workbench/page.tsx        # 검색/QA Workbench
│  ├─ intelligence/page.tsx     # 민원 인텔리전스 대시보드
│  └─ admin/page.tsx            # 관리자 통계 화면
├─ components/
│  └─ intelligence/             # IssueAlert, PublicInsight, 중복 병합 카드/지도/상세 패널
├─ lib/
│  ├─ api.ts                    # FastAPI client와 FE-facing 타입
│  ├─ draft.ts
│  ├─ mockData.ts
│  └─ safe-data.ts
└─ scripts/
   └─ prepareComplaintIntelligenceReplay.mjs
```

## `data/` 구조

```text
data/
├─ demo/                        # demo seed
├─ complaint_intelligence/      # real replay, duplicate merge demo seed
├─ processed/                   # processed consulting/civil data
├─ evaluation/                  # 평가 scenario, holdout, qrels, pool
├─ departments/                 # 부서 master/evaluation data
├─ laws/                        # 법령/조례 corpus
├─ chroma_db/                   # ChromaDB persist directory
└─ urgency/                     # 긴급도 모델/label data
```

`data/chroma_db`와 SQLite DB는 로컬 실행 산출물을 포함할 수 있으므로 공유 전 PII와 용량 정책을 확인해야 합니다.

## `scripts/` 주요 범주

- 서버 실행: `run_api.py`
- 인덱싱: `build_index.py`, `inspect_chromadb.py`, `repair_chromadb_hnsw.py`
- RAG/QA 평가: `evaluate_retrieval.py`, `evaluate_qa.py`, `eval_*`
- Complaint Intelligence seed/replay: `build_complaint_intelligence_demo_seed.py`, `seed_complaint_intelligence_demo.py`, `prepare_complaint_intelligence_real_replay.py`
- Complaint Intelligence 평가: `evaluate_complaint_intelligence_scenarios.py`, `evaluate_complaint_intelligence_holdout.py`, `evaluate_public_insight_llm.py`
- Duplicate Merge 평가/demo: `seed_duplicate_merge_demo.py`, `evaluate_duplicate_merge_*`

## `docs/` 구조

```text
docs/
├─ 00_overview/                 # 현재 프로젝트 개요의 기준 문서
├─ 10_contracts/                # 현재 API/데이터/FE-BE 계약의 기준 문서
├─ 20_domains/                  # 도메인 정책과 설계 판단
├─ 30_manuals/                  # 실행, seed, replay, 평가 runbook
├─ 40_delivery/                 # 주차별 delivery 산출물과 인수인계 기록
├─ 50_issues/                   # 이슈별 설계, 검증, handoff, 운영 메모
└─ 60_specs/                    # 과거/source spec. 현재 계약은 10_contracts 기준
```

## 주의해야 할 오래된 표현

- 현재 기준 UI는 `frontend/`의 Next.js입니다. 과거 `app/ui` Streamlit은 PoC 성격으로만 봅니다.
- 현재 Search/QA endpoint는 `/api/v1/search`, `/api/v1/qa`입니다.
- Complaint Intelligence endpoint는 `/complaint-intelligence/...`이며 `/api/v1` prefix를 붙이지 않습니다.
- `60_specs`는 기준 계약이 아니라 source-spec입니다.
