# Complaint Intelligence Local LLM 운영 정책

기준: 2026-06-21
대상 모델: `exaone3.5:7.8b`

## 1. 운영 원칙

Local LLM 기반 `PublicAgencyInsight` 생성은 요청-응답형 실시간 API로 직접 노출하지 않습니다. 현재 25개 curated scenario 평가에서 품질 지표는 안정적이지만, 평균 생성 시간이 약 147초 이상으로 사용자 클릭 직후 응답을 기다리는 UX에는 적합하지 않습니다.

따라서 운영 기본 형태는 다음과 같습니다.

```text
민원 이벤트 저장
-> scheduler/collector 기반 분석 실행
-> IssueAlert 빠른 갱신
-> PublicAgencyInsight 비동기 합성
-> SQLite/Postgres read-model 저장
-> FE는 read-model 조회
```

## 2. 역할 분리

| 구성 | 운영 역할 | 갱신 주기 제안 |
| --- | --- | --- |
| IssueAlert | 급증, 안전, 단속, 운영 병목 신호를 빠르게 감지 | 짧은 주기 |
| EvidencePack | LLM에 전달할 PII-safe 근거 묶음 | candidate 변경 시 |
| PublicAgencyInsight | 담당자용 행정 조치 브리프 | 우선순위 candidate 중심 |
| QualityGate/GroundingVerifier | 노출 전 품질/근거/PII 검증 | 매 생성 시 |
| Dashboard read-model | FE가 조회하는 최종 상태 | 분석 완료 후 |

## 3. LLM 재생성 조건

같은 `type/topic/region` 조합의 insight를 매번 재생성하지 않습니다. 다음 조건 중 하나가 충족될 때 재생성을 권장합니다.

- 신규 `IssueAlert` 생성
- `affected_count` 또는 `recent_count`가 유의미하게 증가
- priority가 `MEDIUM -> HIGH` 또는 `HIGH -> CRITICAL`로 변동
- EvidencePack 대표 민원 또는 aspect/request 구성이 크게 변경
- 기존 insight TTL 만료
- 담당자 dismiss/resolved 이후 동일 이슈가 재발

## 4. TTL/Dedupe 정책 제안

- 같은 `type + topic + region` insight는 dedupe window 안에서 하나만 유지합니다.
- 안전/급증 유형은 TTL을 짧게 두고, 정책/제도 개선 유형은 TTL을 길게 둡니다.
- LLM 실패 시 fallback template을 저장하되 `uncertainty`에 fallback 사실을 남깁니다.
- `grounding_score`, `confidence`, `avg_actionability_score`가 기준 미만이면 운영 노출 대신 내부 검토 queue로 보냅니다.

## 5. Local LLM 평가 결과

Curated 25개 scenario 기준 최종 평가:

| 지표 | 값 |
| --- | ---: |
| scenario_count_requested/evaluated | 25 / 25 |
| overall_pass_rate | 1.0000 |
| direct_llm_success_rate | 1.0000 |
| fallback_rate | 0.0000 |
| json/schema/grounding failure | 0 / 0 / 0 |
| pii_leak_rate | 0.0000 |
| forbidden_ai_ops_term_rate | 0.0000 |
| avg_llm_duration_ms | 약 146,978ms |
| p95_llm_duration_ms | 약 176,542ms |

이번 작업에서는 latency보다 인사이트 품질을 우선해 compact EvidencePack 입력을 다시 확장했습니다. 따라서 향후 latency 수치는 재평가 리포트 기준으로 확인해야 합니다.

## 6. 실패 처리 정책

| 실패 유형 | 처리 |
| --- | --- |
| JSON parse/schema 실패 | fallback template 사용, failure reason 저장 |
| GroundingVerifier 실패 | 근거 없는 action 제거, 모두 제거되면 fallback |
| QualityGate 실패 | 운영 노출 보류 또는 fallback |
| PII 감지 | 마스킹 재시도, 복구 불가 시 discard |
| forbidden AI-ops term 감지 | discard 또는 fallback |
| timeout | 해당 candidate 실패로 기록하고 다음 candidate 진행 |

## 7. FE 연동 원칙

FE는 LLM 생성을 직접 기다리지 않습니다. 다음 read-model endpoint를 조회합니다.

```http
GET /complaint-intelligence/dashboard
GET /complaint-intelligence/issue-alerts
GET /complaint-intelligence/public-insights
GET /complaint-intelligence/public-insights/{insight_id}
GET /complaint-intelligence/public-insights/{insight_id}/evidence-pack
```

EvidencePack은 관리자/검증 화면에서만 사용하고, 일반 화면에는 masked preview와 evidence count만 표시합니다.
