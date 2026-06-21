# Duplicate Merge UI/UX FE Handoff

## 목적

민원 인텔리전스 탭에서 담당자가 급증 이슈와 중복 병합 후보를 함께 검토하도록 돕는다. 화면은 자동 병합을 수행하지 않으며, 추천 후보는 담당자 확정 전까지 실제 민원 상태를 바꾸지 않는다.

## 화면 구조

- 왼쪽: 핫스팟 카드 목록
  - 담당자가 먼저 볼 업무 단위다.
  - 심각도, 최근 접수 건수, 기준선 문구, 중복 후보 수를 빠르게 스캔한다.
  - `중복 후보 보기`를 누르면 중복 병합 탭으로 이동하고 해당 핫스팟에 연결된 후보만 필터링한다.
- 오른쪽: 핫스팟 지도
  - Leaflet + react-leaflet 기반 지도 패널이다.
  - 지도는 판단 보조 정보이며, 카드보다 우선하지 않는다.
  - 민원 발생 중심과 반경을 원형 레이어로 표시한다.

좁은 화면에서는 지도와 카드가 세로로 쌓인다. 핵심 판단 정보는 카드에 남기고, 지도는 보조 패널로 둔다.

## HotspotMap 컴포넌트

파일:

- `frontend/components/intelligence/HotspotMap.tsx`
- `frontend/components/intelligence/LeafletHotspotMap.tsx`
- `frontend/components/intelligence/hotspotMapUtils.ts`

역할:

- `IntelIssueAlertCard[]`를 받아 지도 위에 핫스팟 원형 레이어와 마커를 표시한다.
- 원형 레이어 반경은 API의 `radius`를 우선 사용한다.
- `center.latitude`, `center.longitude`가 있으면 관측 중심으로 표시한다.
- `center`가 없고 `region`이 있으면 데모용 행정구역 대표 좌표로 표시한다.
- `center`와 `region`이 모두 불명확하면 지도에 찍지 않고 `위치 불명확` 목록으로 분리한다.

주의:

- 지도 좌표는 실제 주소가 아니라 관제용 위치 신호다.
- 위치가 불명확한 alert를 정확한 위치처럼 보이게 하지 않는다.
- 외부 지도 타일 네트워크가 느리면 배경 지도는 늦게 보일 수 있으나, UI는 카드 중심으로 계속 동작해야 한다.

## 카드와 지도 상호작용

- 카드 hover/focus/click: `focusedAlertId`를 갱신하고 지도 마커를 강조한다.
- 지도 마커 hover/click: `focusedAlertId`를 갱신하고 카드 목록에서 해당 카드가 강조된다.
- 카드 목록은 `focusedAlertId` 변경 시 해당 카드로 스크롤한다.
- 중복 후보가 있는 alert에는 카드와 지도 팝업·요약 영역에 `중복 후보 보기` 버튼을 둔다.

## 중복 병합 탭 문구

화면에는 내부 개발 용어를 노출하지 않는다.

- `payload` 대신 `대표 답변 초안 자료`
- `PII-safe` 대신 `민감정보를 제외한 요약` 또는 더 자연스러운 설명 문장
- `exact` 대신 `장소와 시설 신호가 일치`
- `멤버 민원` 대신 `함께 검토할 민원`
- 내부 merge id 대신 사건 중심 제목

대표 민원 선정 이유는 `PII 노출 위험이 낮음`을 그대로 보여주지 않고, `장소와 요청 내용이 가장 구체적으로 정리되어 대표로 검토하기 좋습니다.`처럼 업무 판단 문장으로 표현한다.

## 상태 규칙

- `candidate`: 추천 후보, 담당자 검토 필요
- `confirmed`: 담당자 확정 그룹, 대표 답변 초안 자료 생성 가능
- `split`: 분리됨
- `rejected`: 추천 기각

`draft-reply`는 confirmed 상태에서만 허용한다. candidate/rejected/split 상태에서는 FE 버튼을 비활성화하고, API도 기존처럼 409를 반환한다.

## Risk Flag / Evidence 표시

risk flag는 코드가 아니라 업무 언어로 표시한다.

- `REQUEST_TYPE_MISMATCH`: 요청 유형 혼합
- `LEGAL_RIGHTS_OR_DEADLINE_RISK`: 권리관계·처리기한 주의
- `LOCATION_MISMATCH`: 장소가 서로 다름
- `LOCATION_AMBIGUOUS`: 장소 근거 부족
- `PII_RISK`: 개인정보 확인 필요

evidence는 그룹 카드 하단에 최대 2개 우선 노출한다. 원문 전체나 내부 분석 문장을 그대로 표시하지 않고, 담당자가 판단할 수 있는 문장으로 바꾼다.

## Baseline 0 문구

계산 로직은 유지하고 FE 표시만 바꾼다.

- baseline = 0: `최근 N건 · 과거 7일 기준선 0건 · 신규 급증`
- 0 < baseline < 1: `최근 N건 · 기준선 없음 · 급증 감지`
- baseline >= 1: `최근 N건 · 과거 7일 기준선 B건 대비 R배`

영어 `baseline` 문구는 화면에 노출하지 않는다.

## 접근성 / 반응형

- 심각도는 색상만으로 구분하지 않고 텍스트 라벨을 함께 표시한다.
- 카드와 지도 마커는 click/focus로 같은 강조 상태를 공유한다.
- 버튼 텍스트는 짧게 유지하고, 비활성 버튼에는 이유를 title로 제공한다.
- 좁은 화면에서는 카드·지도·중복 후보 영역이 넘치지 않도록 flex wrap과 line clamp를 사용한다.

## 남은 리스크

- 지도 타일은 네트워크 의존성이 있으므로 오프라인 데모에서는 배경 지도 로딩이 늦거나 실패할 수 있다.
- 데모용 region fallback 좌표는 실제 주소 좌표가 아니며 운영 위치 정확도를 보장하지 않는다.
- `linked_issue_alert_ids`는 alert와 duplicate group의 사건 연결 신호에 의존하므로, alert 생성 기준이 바뀌면 badge 수가 달라질 수 있다.
- confirmed도 실제 민원 상태 변경이나 자동 발송을 하지 않는다.
