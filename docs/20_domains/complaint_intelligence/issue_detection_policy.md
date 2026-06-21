# IssueAlert 감지 정책

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/complaint_intelligence/issue_detection/engine.py`
  - `app/complaint_intelligence/config.py`
  - `app/complaint_intelligence/schemas.py`
- 관련 문서:
  - `docs/10_contracts/data/current_data_contract.md`

## 목적

IssueAlert는 “요즘 갑자기 늘어나는 특정 지역/주제 민원”을 감지해 관제 담당자에게 알려주는 read-model입니다.

예:

- 도로 침하/싱크홀 위험
- 야간 하수 악취
- 불법주정차 반복
- 처리 지연/미처리 누적
- 재민원/반복 민원 증가

## 기본 감지 흐름

```text
ComplaintIntelligenceEvent[]
  -> PII-safe analysis text
  -> embedding/semantic clustering
  -> 최근 window 필터
  -> baseline 대비 surge 계산
  -> region compatibility
  -> confidence/severity 계산
  -> IssueAlert 생성
```

## 핵심 기준

- 의미적으로 유사한 민원이 일정 시간 window 안에 집중되어야 합니다.
- 지역이 충돌하면 같은 hotspot으로 묶지 않습니다.
- baseline 대비 급증 비율이 낮으면 alert를 만들지 않습니다.
- 위험 키워드가 있으면 severity/confidence 산정에 반영합니다.

## 운영 메타데이터 기반 alert

semantic surge만으로 잡기 어려운 운영 패턴은 별도 rule로 보완합니다.

- `OPERATIONAL_BACKLOG`: 특정 부서의 처리 지연/미처리 누적
- `REOPEN_REPEAT`: reopened, 낮은 feedback, 반복 문의
- `SERVICE_ACCESSIBILITY_PATTERN`: 고령자/장애인/외국인/접근성 불편
- `SERVICE_UX_PATTERN`: 공공앱/예약/결제/대여 UX 반복 불편

## severity

- `WATCH`: 관찰 필요
- `WARNING`: 담당자 확인과 초기 조치 필요
- `CRITICAL`: 안전 또는 긴급 대응 가능성이 높음

## 금지선

- 단순 키워드 하나만으로 alert를 만들지 않습니다.
- 지역/시간이 분산된 낮은 건수 민원을 hotspot으로 과잉 승격하지 않습니다.
- PII가 포함된 원문을 alert summary나 representative text로 노출하지 않습니다.

## PublicAgencyInsight와의 관계

IssueAlert는 PublicAgencyInsight의 근거 입력이 될 수 있습니다. 예를 들어 도로 침하 alert는 `SAFETY_RISK_SIGNAL` 또는 `HOTSPOT_RESPONSE_REQUIRED` 인사이트와 연결될 수 있습니다.
