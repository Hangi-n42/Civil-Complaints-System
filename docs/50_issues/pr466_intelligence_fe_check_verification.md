# PR #466 — 민원 인텔리전스 FE 확인 포인트 검증

- 문서 상태: verification log
- 검증일: 2026-06-21
- 검증 대상 PR: [#466](https://github.com/Hangi-n42/Civil-Complaints-System/pull/466) (MERGED) — "민원 인텔리전스 데모 UI와 replay 데이터 보강"
- 검증 기준 코드: `origin/main` (`e42b1e35`, #466·#470 머지 포함)
- 검증 방식: 코드 정적 검증(파일·라인 근거) + FE 단위테스트 + lint + production build

## 요약

PR #466 본문의 **FE 확인 포인트 5개 모두 PASS**. 빌드/테스트/lint 그린. 구조적으로 한 가지 낮은 위험의 개선 여지(아래 §개선 권고)만 남는다.

| # | 확인 포인트 | 판정 | 핵심 근거 |
|---|---|---|---|
| 1 | 실시간 이슈 카드 목록 ↔ 지도 연결 | ✅ PASS | `focusedAlertId` 공유 상태로 카드 클릭→지도 recenter, 마커 클릭→카드 scroll-into-view (양방향) |
| 2 | 지도 문구 = `지도 위에 민원 발생 중심과 반경을 표시합니다.` | ✅ PASS | `HotspotMap.tsx:49` 정확 일치(전 코드베이스 1건) |
| 3 | 카드 스크롤 시 우측 지도 패널 sticky | ✅ PASS | `page.tsx:202` `xl:sticky xl:top-4 xl:self-start`, 상위 overflow 깨짐 없음 |
| 4 | 중복 병합 탭에 `demo-*` ID 직접 노출 없음, 한국어 제목 | ✅ PASS | 모든 `demo-` 문자열이 제목 매퍼 내부에만 존재(렌더 JSX엔 없음) |
| 5 | 행정 인사이트 지표 표현 `신뢰도`로 통일 | ✅ PASS | `PublicInsightCard.tsx:38` `신뢰도`, 영문/enum 라벨 미노출 |

## 점검 상세

### 1. 카드 목록 ↔ 지도 연결 — PASS
- 공유 상태: `app/intelligence/page.tsx:49` `const [focusedAlertId, setFocusedAlertId] = useState<string | null>(null)`
- 목록·지도에 동일 전달: `page.tsx:196,198`(목록), `page.tsx:206-207`(지도)
- 카드 클릭 핸들러: `IssueAlertCard.tsx:49` `onClick={() => onFocusAlert?.(alert.id)}`
- 지도 recenter: `LeafletHotspotMap.tsx`의 `MapFocus`가 포커스 좌표로 `map.setView(...)`
- 역방향: 마커 클릭→`onFocusAlert`→`IssueAlertList`가 `issue-alert-${id}`로 scroll-into-view. 단순 표시가 아니라 실제 양방향 배선.

### 2. 지도 문구 — PASS (문자 단위 일치)
- `components/intelligence/HotspotMap.tsx:49`: `지도 위에 민원 발생 중심과 반경을 표시합니다.` (요구 문구와 정확히 일치, 전체 1건)

### 3. 지도 패널 sticky — PASS
- `app/intelligence/page.tsx:202` 컨테이너 `className="order-1 xl:sticky xl:top-4 xl:order-2 xl:self-start"`
- 그리드 `xl:grid-cols-[minmax(0,1fr)_420px]`(`page.tsx:182`)에서 목록 섹션이 스크롤되고 지도는 `xl:top-4`로 고정. `self-start`가 있어 sticky가 정상 동작(셀 높이 stretch로 무력화되지 않음). 상위에 sticky를 깨는 `overflow`/`height` 없음. 지도 내부는 `max-h-[calc(100vh-2rem)] overflow-y-auto`로 자체 스크롤.
- 참고(설계상 의도): sticky는 `xl`(≥1280px) 전용. 그 미만에선 지도가 목록 위로 쌓이는 스택 레이아웃이라 sticky 아님.

### 4. `demo-*` ID 비노출 + 한국어 제목 — PASS
- 그룹 제목: `DuplicateGroupTriage.tsx:247` → `duplicateGroupTitle(group)`(`duplicateMerge.ts:33-49`)
- 대표/구성원 ID·초안 payload: `DuplicateGroupTriage.tsx:249,303,175` 모두 `formatComplaintName(...)`(`:320-402`) 경유 → `demo-*` 접두사를 시나리오별 한국어 제목으로 치환
- `grep "demo-"` 결과 10건 전부 위 두 매퍼 함수 내부(접두사 매칭)일 뿐, 렌더 JSX에 raw ID 없음. 현행 큐레이션 데모셋의 모든 ID가 매핑됨.

### 5. 지표 표현 `신뢰도` 통일 — PASS
- 행정 인사이트 카드 유일 지표 라벨: `PublicInsightCard.tsx:38` `<span>신뢰도 {(insight.grounding_score * 100).toFixed(0)}%</span>`
- `InsightDetailPanel.tsx`엔 경쟁 지표 라벨 없음. 중복 병합 탭도 동일 단어 `신뢰도`(`DuplicateGroupTriage.tsx:235`) 사용 → 대시보드 전체 통일. 영문 enum(`confidence`/`grounding`/`semantic`) 미노출.

## 검증 산출물

- FE 단위테스트: `npm test` → **12 files / 95 tests passed** (#466이 추가한 `hotspotMap`/`duplicateMerge`/`duplicateQueueContext`/`issueAlertTrend` 테스트 포함)
- Lint: `npx eslint .` → exit 0
- Production build: `npm run build` → ✅ Compiled, `/intelligence` 정적 prerender 성공(= Leaflet SSR 처리 정상)

> 빌드 주의: #466이 `leaflet`/`react-leaflet`를 새 의존성으로 추가했다. 기존 체크아웃에서 빌드 전 **`npm install` 필수**(미설치 시 `Module not found: 'leaflet'`로 build 실패 — 코드 결함 아님).

## 개선 권고 (낮은 위험, 선택)

- **P4 fallback raw-ID 누출 여지**: `DuplicateGroupTriage.tsx:401` `return \`민원 ${caseId}\`` — 카탈로그에 없는 ID(임의/미등록 `demo-*`)는 raw ID가 그대로 노출된다. 현행 큐레이션 데모셋은 전부 매핑되어 실제 누출은 없으나 구조적으로 보장되진 않는다. 하드 가드가 필요하면 fallback을 일반 라벨(예: `민원 사례`)로 마스킹 권고. (`duplicateGroupTitle` fallback은 ID를 echo하지 않아 안전)

판정: PR #466의 FE 확인 포인트는 현재 코드 기준 **모두 충족**. 위 권고는 필수 아님.
