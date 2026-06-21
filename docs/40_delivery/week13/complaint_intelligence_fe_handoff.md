# Complaint Intelligence FE 핸드오프

## 2026-06-21 운영 품질 갱신

- FE는 Local LLM 생성을 동기적으로 기다리지 않고 저장된 관제 read-model을 조회합니다.
- 기본 진입점은 `GET /complaint-intelligence/dashboard`입니다.
- EvidencePack은 PII-safe 근거 확인용이며, 일반 사용자 화면에는 masked preview와 evidence count만 표시합니다.
- PublicAgencyInsight 카드는 `recommended_actions`, `requires_human_review`, `confidence`, `grounding_score`를 함께 보여주는 것을 권장합니다.
- Local LLM `exaone3.5:7.8b`는 품질 검증 경로를 통과했지만 평균 응답 시간이 길어 scheduler 기반 비동기 갱신이 적합합니다.

## 목적

민원 인텔리전스 탭은 실제 분석 파이프라인을 통과한 read-model을 표시합니다. FE는 mock 응답을 만들지 않고 `GET /complaint-intelligence/dashboard`만 우선 연결하면 이슈 알림과 행정 인사이트 카드를 함께 표시할 수 있습니다.

## 권장 화면 구조

하나의 "민원 인텔리전스" 탭 안에서 다음 2개 하위 탭을 사용합니다.

| 하위 탭 | 데이터 | 사용자 목적 |
| --- | --- | --- |
| 실시간 이슈 | `data.issue_alerts` | 특정 지역/주제에서 급증한 민원 핫스팟을 빠르게 확인 |
| 행정 인사이트 | `data.public_insights` | 공공기관 담당자가 실행할 조치, 근거, human review 필요 여부 확인 |

상단에는 `data.summary`를 KPI 영역으로 보여주세요.

## 기본 API

```http
GET /complaint-intelligence/dashboard
```

응답 최상위 구조:

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

## Summary 표시 필드

| 필드 | 의미 | FE 표시 제안 |
| --- | --- | --- |
| `as_of` | 관제 기준 시각 | "관제 기준" |
| `latest_event_at` | 최근 유입 민원 시각 | "마지막 관측" |
| `event_count` | 저장된 민원 이벤트 수 | 전체 관측 건수 |
| `active_alert_count` | 활성 이슈 수 | 경보 배지 |
| `critical_alert_count` | CRITICAL 경보 수 | 빨간색 강조 |
| `public_insight_count` | 행정 인사이트 수 | 인사이트 카드 수 |
| `high_priority_insight_count` | HIGH/CRITICAL 인사이트 수 | 우선 검토 배지 |
| `human_review_required_count` | 담당자 검토 필요 수 | 검토 필요 배지 |
| `linked_alert_count` | IssueAlert와 연결된 인사이트 수 | 이슈-인사이트 연결 지표 |

## IssueAlert 카드

`data.issue_alerts[]`는 지도/경보 카드에 바로 쓸 수 있게 축약되어 있습니다.

주요 필드:

| 필드 | 설명 |
| --- | --- |
| `id` | alert id |
| `severity`, `severity_label`, `color` | 심각도와 색상 |
| `title`, `summary` | 카드 제목/요약 |
| `topic`, `region` | 주제/지역 |
| `center`, `radius`, `map_focus` | 지도 표시용 위치 정보. 좌표가 없을 수 있으므로 null-safe 처리 필요 |
| `recent_count`, `baseline`, `surge_ratio` | 급증 판단 지표 |
| `confidence` | 감지 신뢰도 |
| `keywords` | 대표 키워드 |
| `representative_complaint_ids` | 대표 민원 ID |
| `linked_insight_ids` | 연결된 PublicAgencyInsight ID |
| `first_seen`, `last_seen` | 최초/마지막 관측 시각 |

표시 제안:

- `CRITICAL/HIGH`는 경보성 색상으로 강조합니다.
- `map_focus` 또는 `center`가 있으면 지도 중심 이동에 사용합니다.
- `linked_insight_ids`가 있으면 "연결 인사이트 보기" 버튼으로 행정 인사이트 탭 필터링을 붙일 수 있습니다.

## PublicAgencyInsight 카드

`data.public_insights[]`는 담당자 조치 브리핑 카드입니다.

주요 필드:

| 필드 | 설명 |
| --- | --- |
| `id` | insight id |
| `type`, `type_label` | 인사이트 유형 |
| `priority`, `priority_label`, `color` | 우선순위와 색상 |
| `title`, `summary` | 제목/요약 |
| `problem_diagnosis` | 핵심 진단 |
| `topic`, `target_area` | 주제와 행정 대상 영역 |
| `affected_count` | 근거 민원 수 |
| `affected_region`, `related_department` | 지역/담당 부서 |
| `confidence`, `grounding_score` | 신뢰도/근거성 점수 |
| `requires_human_review` | 담당자 검토 필요 여부 |
| `linked_alert_ids` | 연결된 IssueAlert ID |
| `representative_evidence_ids` | 대표 근거 민원 ID |
| `top_aspects` | 반복 불편 측면 상위 3개 |
| `citizen_requests` | 시민 요구 상위 3개 |
| `recommended_actions` | 구조화된 추천 조치 |
| `uncertainty` | 불확실성/주의점 |
| `metrics` | actionability, action rubric, LLM 관측 지표 일부 |

추천 조치 표시:

```json
{
  "action": "집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다.",
  "horizon": "SHORT_TERM",
  "action_type": "ENFORCEMENT",
  "responsible_unit_hint": "교통지도과",
  "why": "단속 공백 민원이 반복되었습니다.",
  "supporting_evidence_ids": ["..."],
  "expected_impact": "반복 위반 민원 감소 가능성이 있습니다.",
  "risk_or_dependency": "단속 권한과 인력 배치 확인이 필요합니다."
}
```

FE 표시 제안:

- `requires_human_review=true`이면 "담당자 검토 필요" 배지를 표시합니다.
- `recommended_actions[*].action_type`은 아이콘/색상 매핑에 사용할 수 있습니다.
- `supporting_evidence_ids`는 상세 근거 열람 버튼과 연결합니다.
- `uncertainty`는 접힌 영역에 표시해 과도한 단정처럼 보이지 않게 합니다.

## 상세/검증용 API

필요 시 다음 endpoint를 추가 연결합니다.

| API | 용도 |
| --- | --- |
| `GET /complaint-intelligence/issue-alerts` | IssueAlert 원본 목록 |
| `GET /complaint-intelligence/public-insights` | PublicAgencyInsight 원본 목록 |
| `GET /complaint-intelligence/public-insights/{insight_id}` | 인사이트 상세 |
| `GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack` | 관리자/개발자용 근거 패키지 확인 |
| `GET /complaint-intelligence/collector/status` | collector/checkpoint 상태 확인 |
| `POST /complaint-intelligence/scheduler/run-once` | collector 수집 후 분석 1회 실행 |
| `POST /complaint-intelligence/collector/poll-once` | 이벤트 수집/저장만 1회 실행 |
| `GET /complaint-intelligence/public-insights/llm-observability` | Local LLM 장기 관측 리포트 |

## Empty State

대시보드 응답의 `data.empty_state`를 그대로 사용합니다.

```json
{
  "issue_alerts": "현재 표시할 실시간 이슈가 없습니다.",
  "public_insights": "현재 표시할 행정 인사이트가 없습니다."
}
```

## FE 구현 시 주의점

- `center`, `radius`, `affected_region`은 null일 수 있습니다.
- `recommended_actions`는 빈 배열일 수 없도록 backend 품질 게이트를 적용하지만, FE는 방어적으로 처리합니다.
- `evidence-pack`은 관리자/개발 검증용입니다. 일반 사용자 화면에 원문처럼 노출하지 마세요.
- 표시 문구는 "과거 스냅샷"보다 "관제 기준", "최근 관측", "최근 감지된 이슈"처럼 실시간 관제 맥락을 유지합니다.
- 현재 Local LLM 생성 결과는 PII 마스킹, GroundingVerifier, QualityGate, action rubric을 통과한 값입니다.

## FE 데모 확인 순서

1. backend 서버 실행
2. 필요 시 demo seed 실행: `civil\Scripts\python.exe scripts\seed_complaint_intelligence_demo.py`
3. `GET /complaint-intelligence/dashboard` 호출
4. `data.summary.active_alert_count > 0` 또는 `data.public_insight_count > 0` 확인
5. 카드에서 `linked_alert_ids`, `recommended_actions`, `requires_human_review` 표시 확인
