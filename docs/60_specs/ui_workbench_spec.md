# UI Workbench Spec (Next.js 3-Tier)

문서 버전: v1.1  
기준: PRD v2.1, 사용자 시나리오 v1.1, WBS v4.1, folder_structure v3.1

## 1. 목적

Next.js(App Router) 기반 3단 워크벤치 UI의 컴포넌트 트리, 상태 모델, 사용자 액션별 상태 전이를 정의한다.  
중점은 `/search` → `/qa` E2E 흐름에서 `routing_trace`, `routing_hint`, `structured_output`을 일관 가시화하는 것이다.  
라우팅 판단은 `topic_type + complexity_level`을 중심으로 표시한다.

## 2. 페이지/컴포넌트 구조

- 페이지 경로: `web/app/workbench/page.tsx`
- 기본 레이아웃: 좌(네비게이션) / 중(민원 목록) / 우(AI 패널)

## 2.1 컴포넌트 트리

```text
WorkbenchPage
├─ NavigationSidebar
│  ├─ NavHeader
│  ├─ NavMenu (워크벤치, 민원함, 관리자)
│  └─ NavFooter (사용자 정보)
├─ ComplaintList
│  ├─ ListToolbar (검색, 상태 필터)
│  ├─ ComplaintListItem[]
│  │  ├─ StatusBadge
│  │  ├─ TopicBadge
│  │  └─ RoutingBadge (complexity_level/strategy_id)
│  └─ ListPagination (옵션)
└─ AIAssistantPanel
   ├─ AnalysisSummaryCard (topic_type, complexity_level, complexity_score)
   ├─ RoutingTraceCard (route_key, strategy_id, route_reason)
   ├─ RetrievalEvidenceCard (retrieved_docs, score, citation)
   ├─ DraftAnswerEditor (answer, editable)
   ├─ StructuredOutputCard (summary, action_items, request_segments)
   └─ PanelActions (재생성, 저장, 검토완료)
```

필수 루트 컴포넌트 명:
- `NavigationSidebar`
- `ComplaintList`
- `AIAssistantPanel`

## 3. 상태(State) 모델

## 3.1 전역 상태 (예: Zustand/Context)

```ts
type WorkbenchStatus = "idle" | "loading" | "success" | "error";

interface WorkbenchState {
  selectedComplaintId: string | null;
  complaints: ComplaintListItem[];
  uiStatus: WorkbenchStatus;
  errorMessage: string | null;

  analyzerOutput: AnalyzerOutput | null;
  routingTrace: RoutingTrace | null;
  routingHint: RoutingHint | null;

  retrievedDocs: RetrievedDoc[];
  qaResult: {
    answer: string;
    citations: Citation[];
    limitations: string[];
    structured_output: StructuredOutput | null;
  } | null;
}
```

## 3.2 컴포넌트별 핵심 상태

- `NavigationSidebar`
  - `activeMenu`: `"workbench" | "complaints" | "admin"`
- `ComplaintList`
  - `selectedComplaintId`
  - `statusFilter`: `"all" | "pending" | "in_progress" | "review_completed"`
- `AIAssistantPanel`
  - `isGenerating` (검색/생성 로딩)
  - `draftAnswer` (편집 버퍼)
  - `isDirty` (수정 여부)

## 4. 사용자 액션별 상태 변화 흐름

## 4.1 민원 선택

1. 사용자: `ComplaintListItem` 클릭  
2. 상태 변경:
   - `selectedComplaintId` 설정
   - `uiStatus = "loading"`
3. 시스템:
   - `/search` 호출
4. 성공 시:
   - `routingTrace`, `routingHint`, `retrievedDocs` 저장
   - `uiStatus = "success"`
5. 실패 시:
   - `uiStatus = "error"`
   - `errorMessage` 표시

## 4.2 검색 결과 기반 QA 생성

1. 사용자: `PanelActions > 답변 생성` 클릭 (또는 자동 트리거)
2. 시스템:
   - `/qa` 호출 (`routing_hint` 포함)
   - `/search` 연계 시 `use_search_results=true`, `search_results[]` 함께 전달
3. 성공 시:
   - `qaResult.answer`, `citations`, `limitations`, `structured_output` 저장
   - `draftAnswer = answer`
4. 실패 시:
   - 에러 배지 + 재시도 버튼 표시

## 4.3 답변 수정 및 검토완료

1. 사용자: `DraftAnswerEditor`에서 텍스트 수정
2. 상태 변경:
   - `draftAnswer` 갱신
   - `isDirty = true`
3. 사용자: `검토완료` 클릭
4. 시스템:
   - 완료 API 또는 상태 업데이트 이벤트 기록
   - 리스트의 해당 민원 `status = "review_completed"`로 반영

## 5. API 연동 계약 (UI 관점)

- `/search` 성공 시 필수 사용 필드:
  - `strategy_id`, `route_key`, `routing_hint`, `routing_trace`, `retrieved_docs`
- `/qa` 요청 시 필수 전송 필드:
  - `complaint_id`, `query`, `routing_hint`
- `/qa` 요청 시 연계 전달 필드(권장):
   - `use_search_results`, `search_results`
- `/qa` 성공 시 필수 사용 필드:
  - `routing_trace`, `structured_output`, `answer`, `citations`, `limitations`

## 6. 렌더링 규칙

- `routing_trace.complexity_level`, `routing_trace.complexity_score`, `strategy_id`는 중앙 리스트 카드와 우측 라우팅 카드 모두 표시한다.
- `routing_trace.complexity_trace`는 "복잡도 산출 근거" 섹션으로 접기/펼치기 렌더링한다.
- `route_key`는 `{topic_type}/{complexity_level}` 포맷으로 표시한다.
- `request_segments` 체크리스트를 우측 패널에 표시한다.
- citation 없는 답변 문장은 경고 배지(근거 부족) 표시를 기본 정책으로 둔다.
- 상태 UX 4종을 공통 처리한다: `success`, `loading`, `error`, `empty`.

## 7. DoD (UI Spec 관점)

- 3단 레이아웃 컴포넌트가 분리되어 렌더된다.
- 민원 선택 → `/search` → `/qa` 흐름이 단일 화면에서 연속 동작한다.
- 우측 패널에서 `routing_trace`, `structured_output`, `answer`, `citations`를 확인 가능하다.
- 라우팅 판단 근거(`complexity_level`, `complexity_score`)를 사용자가 해석 가능하게 확인할 수 있다.
- 초안 편집 후 `review_completed` 상태 전환이 목록에 반영된다.