# 폴더 구조 설계 문서 (Adaptive RAG + Next.js)

문서 버전: v3.1  
최신화: 2026-04-10

## 1. 목적

본 구조는 Week5-8 동안 Adaptive RAG 코어 모듈(FastAPI)과 3단 Workbench UI(Next.js)를 병렬 개발하면서, `/search`·`/qa` API 계약 필드(`routing_trace`, `routing_hint`, `structured_output`)를 안정적으로 유지하기 위한 실행 경계를 정의한다.

## 2. 핵심 디렉터리 (구체화)

```text
AI-Civil-Affairs-Systems/
├─ app/
│  ├─ api/
│  │  ├─ routers/                    # FastAPI 라우터 (/search, /qa 등)
│  │  ├─ schemas/                    # Pydantic 요청/응답 모델
│  │  ├─ dependencies/               # 공통 DI/설정 주입
│  │  └─ middleware/                 # request_id, 에러 래퍼, 로깅
│  ├─ retrieval/
│  │  ├─ analyzers/                  # TopicAnalyzer, ComplexityAnalyzer, MultiRequestDetector(보조)
│  │  ├─ router/                     # AdaptiveRouter, route_key/strategy 결정
│  │  ├─ strategies/                 # topic/complexity 기반 retrieval 전략
│  │  └─ services/                   # 검색 실행, trace 생성, metadata 조합
│  ├─ generation/
│  │  ├─ prompt_factory/             # topic-aware prompt 구성
│  │  ├─ normalizers/                # normalize_response, unified output 변환
│  │  └─ services/                   # QA 생성 파이프라인
│  ├─ structuring/
│  │  ├─ parsers/                    # 원문 파싱
│  │  ├─ validators/                 # 스키마/필드 검증
│  │  └─ models/                     # 구조화 내부 모델
│  ├─ ingestion/
│  │  ├─ loaders/                    # 입력 로딩
│  │  ├─ cleaners/                   # 전처리/정제
│  │  └─ pii/                        # 개인정보 마스킹/필터
│  ├─ core/                          # 설정, 공통 유틸, 상수
│  └─ tests/                         # 회귀 확인용 최소 E2E 스모크
│
├─ web/                              # Next.js 프론트엔드
│  ├─ app/
│  │  ├─ layout.tsx                  # 앱 공통 레이아웃
│  │  ├─ page.tsx                    # 엔트리/리다이렉트
│  │  └─ workbench/
│  │     └─ page.tsx                 # 3단 Workbench 메인
│  ├─ components/
│  │  ├─ navigation/                 # NavigationSidebar 계층
│  │  ├─ case-list/                  # ComplaintList 계층
│  │  ├─ assistant-panel/            # AIAssistantPanel 계층
│  │  ├─ common/                     # Badge, EmptyState, ErrorState 등
│  │  └─ layout/                     # 3단 분할 레이아웃 컴포넌트
│  ├─ services/
│  │  ├─ api-client.ts               # 공통 HTTP 클라이언트
│  │  ├─ search.service.ts           # /search 호출
│  │  └─ qa.service.ts               # /qa 호출 (routing_hint 전달)
│  ├─ types/
│  │  ├─ api.ts                      # API 계약 타입
│  │  ├─ complaint.ts                # 민원 모델 타입
│  │  └─ workbench.ts                # 화면 상태 타입
│  └─ stores/                        # 전역 상태(zustand/context)
│
├─ docs/
│  ├─ 00_overview/                   # PRD/WBS/아키텍처 개요
│  ├─ 10_contracts/                  # 주차별 인터페이스 계약
│  ├─ 20_domains/
│  ├─ 30_manuals/                    # 운영/개발 매뉴얼
│  ├─ 40_delivery/                   # 전달 산출물
│  ├─ 50_issues/                     # Tier 3 주차별 실행 이슈
│  └─ 60_specs/                      # Tier 2 기술 명세(api/data/ui)
│
│
├─ configs/                          # 모델/환경 설정
├─ schemas/                          # JSON Schema 원본
├─ scripts/                          # 실행/유틸 스크립트
└─ reports/                          # 주차별 리포트/로그 산출물
```

## 3. Workbench UI 구조 (고정)

- `web/app/workbench/page.tsx`: 3단 분할 메인 화면
- `web/components/navigation/*`: 좌측 네비게이션
- `web/components/case-list/*`: 중앙 민원 목록
- `web/components/assistant-panel/*`: 우측 AI 패널

필수 루트 컴포넌트:
- `NavigationSidebar`
- `ComplaintList`
- `AIAssistantPanel`

## 4. FastAPI API 구조 (고정)

- `app/api/routers/search.py`: `/search` 라우트
- `app/api/routers/qa.py`: `/qa` 라우트
- `app/api/schemas/search.py`: SearchRequest/SearchResponse
- `app/api/schemas/qa.py`: QARequest/QAResponse

필수 계약 필드:
- `/search` 응답: `routing_trace`, `routing_hint`, `strategy_id`, `route_key`
- `/qa` 요청: `routing_hint`
- `/qa` 응답: `routing_trace`, `structured_output`, `answer`, `citations`

## 5. 문서-코드 정합성 규칙

- 문서 계약 필드는 `app/api/schemas`와 `web/types`에 동일 키로 반영한다.
- `routing_trace`, `routing_hint`, `structured_output`는 별칭 없이 고정 표기한다.
- Analyzer 출력(`topic_type`, `complexity_level`, `complexity_score`, `complexity_trace`, `request_segments`)은 Router/API/UI 전체에서 동일 키를 사용한다.
- `length_bucket`, `is_multi`는 보조 표시 필드로만 사용하며 라우팅 핵심 키로 사용하지 않는다.
- Week7 이후 디렉터리 대규모 이동은 금지한다.