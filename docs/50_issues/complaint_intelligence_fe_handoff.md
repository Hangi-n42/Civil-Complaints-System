# Complaint Intelligence FE 핸드오프

기준일: 2026-06-19  
범위: 민원 인텔리전스 탭 FE 연결 계약

## 1. 화면 컨셉

`민원 인텔리전스` 탭을 새로 두고 내부를 두 영역으로 나눈다.

```text
민원 인텔리전스
├─ 실시간 이슈
│  ├─ 지도/핫스팟
│  ├─ 급증 경보 카드
│  └─ 연결된 행정 인사이트 바로가기
└─ 행정 인사이트
   ├─ 우선순위 카드 목록
   ├─ 조치 브리핑 상세
   └─ 근거 민원/EvidencePack 확인
```

역할 구분:

| 영역 | 목적 | 주요 데이터 |
| --- | --- | --- |
| 실시간 이슈 | 지금 급증하는 지역/주제 경보 | `issue_alerts` |
| 행정 인사이트 | 담당자가 취할 행정 조치 브리핑 | `public_insights` |
| EvidencePack | 인사이트 근거 확인 | `/public-insights/{id}/evidence-pack` |

## 2. 신규 FE 전용 API

기존 raw API는 유지하고, FE가 바로 렌더링하기 쉬운 카드형 read model을 추가했다.

### 2.1 저장된 대시보드 조회

```http
GET /complaint-intelligence/dashboard
```

쿼리:

| 이름 | 설명 |
| --- | --- |
| `status` | 선택. `ACTIVE`, `UPDATED`, `RESOLVED`, `open` 등 저장 상태 필터 |
| `type` | 선택. `SAFETY_RISK_SIGNAL`, `PUBLIC_GUIDANCE_NEEDED` 등 인사이트 타입 |

### 2.2 분석 실행 후 대시보드 응답 받기

```http
POST /complaint-intelligence/dashboard/run-analysis
```

요청:

```json
{
  "request_id": "optional-client-request-id",
  "events": [
    {
      "id": "complaint-001",
      "received_at": "2026-06-19T01:00:00+09:00",
      "body": "OO동 도로에 구멍이 생겼습니다.",
      "region": "OO동",
      "final_department": "도로관리과",
      "status": "pending",
      "structured_elements": {
        "observation": {"text": "도로에 구멍이 생김", "confidence": 0.91},
        "result": {"text": "보행 안전 위험"},
        "request": {"text": "현장 점검 요청"},
        "context": {"text": "OO동 같은 위치에서 반복"}
      }
    }
  ]
}
```

## 3. 응답 구조

```json
{
  "success": true,
  "request_id": "...",
  "timestamp": "...",
  "data": {
    "summary": {},
    "tabs": [],
    "issue_alerts": [],
    "public_insights": [],
    "empty_state": {}
  }
}
```

### 3.1 `summary`

상단 KPI에 사용한다.

| 필드 | 의미 |
| --- | --- |
| `alert_count` | 이슈 경보 수 |
| `critical_alert_count` | 긴급 경보 수 |
| `public_insight_count` | 행정 인사이트 수 |
| `high_priority_insight_count` | HIGH/CRITICAL 인사이트 수 |
| `human_review_required_count` | 담당자 검토 필요 인사이트 수 |
| `linked_alert_count` | IssueAlert와 연결된 인사이트 수 |

### 3.2 `tabs`

FE 탭 라벨 힌트다.

```json
[
  {"id": "issue_alerts", "label": "실시간 이슈"},
  {"id": "public_insights", "label": "행정 인사이트"}
]
```

### 3.3 `issue_alerts`

실시간 이슈 카드와 지도 마커에 사용한다.

| 필드 | 렌더링 |
| --- | --- |
| `id` | 경보 상세/연결 키 |
| `severity`, `severity_label`, `color` | 배지 색상과 라벨 |
| `title`, `summary` | 카드 제목/요약 |
| `topic`, `keywords` | 이슈 주제/대표 표현 |
| `region`, `center`, `radius`, `map_focus` | 지도 표시 |
| `recent_count`, `baseline`, `surge_ratio` | 급증 수치 |
| `representative_complaint_ids` | 대표 민원 ID |
| `linked_insight_ids` | 연결된 행정 인사이트 |

색상:

| severity | label | color |
| --- | --- | --- |
| `WATCH` | 관찰 | `gray` |
| `WARNING` | 주의 | `amber` |
| `CRITICAL` | 긴급 | `red` |

### 3.4 `public_insights`

행정 인사이트 카드와 상세 패널에 사용한다.

| 필드 | 렌더링 |
| --- | --- |
| `id` | 인사이트 상세/EvidencePack 조회 키 |
| `type`, `type_label` | 인사이트 유형 배지 |
| `priority`, `priority_label`, `color` | 우선순위 배지 |
| `title`, `summary` | 카드 제목/요약 |
| `problem_diagnosis` | 상세 패널의 핵심 진단 |
| `topic`, `target_area` | 주제/업무 영역 |
| `affected_count`, `affected_region` | 규모/지역 |
| `related_department` | 담당 부서 후보 |
| `confidence`, `grounding_score` | 신뢰도 |
| `requires_human_review` | 담당자 검토 필요 표시 |
| `linked_alert_ids` | 연결된 이슈 경보 |
| `top_aspects` | 반복 불편 측면 |
| `citizen_requests` | 시민 요구 집계 |
| `recommended_actions` | 조치 카드 |
| `uncertainty` | 추가 확인 필요사항 |

우선순위 색상:

| priority | label | color |
| --- | --- | --- |
| `LOW` | 낮음 | `gray` |
| `MEDIUM` | 보통 | `blue` |
| `HIGH` | 높음 | `amber` |
| `CRITICAL` | 긴급 | `red` |

## 4. 권장 UI 구성

### 4.1 실시간 이슈 카드

카드 구성:

```text
[긴급] 중구 도로 침하 의심 민원 급증
최근 3시간 12건 / baseline 대비 4.2배
대표 표현: 구멍, 침하, 꺼짐, 아스팔트

[지도 보기] [연결 인사이트 2건]
```

지도:

- `map_focus.center`가 있으면 마커와 반경을 표시한다.
- `center`가 없으면 `region` 기반 리스트 카드만 표시한다.

### 4.2 행정 인사이트 카드

카드 구성:

```text
[높음] 안전 위험
중구 도로 침하 안전 위험 대응 필요

핵심 진단:
도로 침하 표현과 위험 언급이 반복되어 현장 확인이 필요합니다.

추천 조치:
- 즉시 현장 점검
- 시민 안전 안내
- 임시 안전 조치

근거: 대표 민원 5건 / grounding 0.91 / 담당자 검토 필요
```

### 4.3 상세 패널

권장 섹션:

1. 제목/우선순위/상태/담당부서 후보
2. 요약과 핵심 진단
3. 추천 조치
   - `horizon`별 그룹: 즉시, 단기, 중기, 장기
   - `action_type` 아이콘/배지
4. 근거 분석
   - `top_aspects`
   - `citizen_requests`
   - `representative_evidence_ids`
5. 불확실성
6. 액션 버튼
   - 확인 처리
   - 담당 부서 공유
   - 조치 계획으로 전환
   - 기각
   - EvidencePack 보기

## 5. EvidencePack 조회

```http
GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack
```

주의:

- debug/admin 용도다.
- 원문 PII는 포함하지 않는다.
- `representative_complaints[*].masked_text`만 표시한다.
- 일반 사용자 화면에는 기본 노출하지 말고 “근거 보기” 확장 영역이나 관리자 모드에서 사용한다.

## 6. FE 연결 순서

1. 새 탭 `민원 인텔리전스` 추가
2. 탭 진입 시 `GET /complaint-intelligence/dashboard` 호출
3. 분석 실행이 필요한 화면에서는 `POST /complaint-intelligence/dashboard/run-analysis` 호출
4. `data.tabs` 기준으로 내부 탭 렌더링
5. `issue_alerts`는 지도/경보 카드에 표시
6. `public_insights`는 조치 브리핑 카드에 표시
7. 상세에서 `linked_alert_ids`와 `linked_insight_ids`로 상호 이동 지원
8. 필요 시 EvidencePack endpoint로 근거 상세 표시

## 7. 완료 기준

- FE가 raw `IssueAlert`/`PublicAgencyInsight`를 직접 해석하지 않아도 카드 렌더링 가능
- 이슈 경보와 행정 인사이트를 같은 탭 안에서 분리 표시
- `linked_alert_ids`와 `linked_insight_ids`로 감지 → 판단 → 조치 흐름 연결
- PII 원문 노출 없음
- EvidencePack은 debug/admin 컨텍스트로만 표시
