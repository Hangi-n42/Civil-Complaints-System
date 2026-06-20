# Local LLM PublicAgencyInsight 샘플 리뷰

- Provider: `local`
- Model: `exaone3.5:7.8b`
- Sample count: `5`

## 재민원/반복 민원 증가

- scenario_id: `repeat_reopen_growth`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `REOPEN_OR_REPEAT_RISK`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 반복 민원 처리 개선 필요
- summary: 관악구에서 악취 및 하수 냄새 관련 반복 민원이 증가하고 있으며, 처리 후에도 동일 문제 재발로 인한 시민 불만이 높습니다.
- problem: 동일 위치 및 주제의 민원이 반복 접수되고 처리 후에도 문제 해결이 미흡하여 재민원 발생률이 높습니다.

### Recommended Actions

- [None] 재민원/반복 민원 증가 처리 흐름을 점검하고 반복 민원 원인별 개선 과제를 정리합니다. (evidence: eval-repeat_reopen_growth-001, eval-repeat_reopen_growth-002)

### Evidence Preview

- `eval-repeat_reopen_growth-001`: 악취 민원을 처리했다고 했지만 같은 냄새가 다시 납니다. 악취 민원을 처리했다고 했지만 같은 냄새가 다시 납니다.
- `eval-repeat_reopen_growth-002`: 하수 냄새 신고를 여러 번 했는데 재발해서 다시 접수합니다. 하수 냄새 신고를 여러 번 했는데 재발해서 다시 접수합니다.
- `eval-repeat_reopen_growth-003`: 반복 민원인데 완료 안내 후에도 현장 상태가 바뀌지 않았습니다. 반복 민원인데 완료 안내 후에도 현장 상태가 바뀌지 않았습니다.
- `eval-repeat_reopen_growth-004`: 같은 위치 악취가 계속 반복되어 재점검이 필요합니다. 같은 위치 악취가 계속 반복되어 재점검이 필요합니다.
- `eval-repeat_reopen_growth-005`: 처리 완료라고 안내받았지만 냄새 문제가 다시 발생했습니다. 처리 완료라고 안내받았지만 냄새 문제가 다시 발생했습니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 소음/공사 민원 특정 시간대 집중

- scenario_id: `construction_noise_time_pattern`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `RECURRING_COMPLAINT_PATTERN`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 야간 공사 소음 단속 강화 필요
- summary: 마포구에서 퇴근 이후 야간 시간대 공사 소음 민원이 집중적으로 발생하고 있습니다.
- problem: 야간 및 퇴근 이후 시간대에 공사 소음 관련 민원이 반복적으로 제기되어 단속 체계의 공백이 의심됩니다.

### Recommended Actions

- [None] 야간 공사 소음 단속 지침 검토 및 강화 (evidence: eval-construction_noise_time_pattern-001, eval-construction_noise_time_pattern-002)

### Evidence Preview

- `eval-construction_noise_time_pattern-005`: 퇴근 이후 공사 소음이 집중되어 생활 불편이 큽니다. 퇴근 이후 공사 소음이 집중되어 생활 불편이 큽니다.
- `eval-construction_noise_time_pattern-004`: 같은 시간대 공사 차량 소음이 계속 발생합니다. 같은 시간대 공사 차량 소음이 계속 발생합니다.
- `eval-construction_noise_time_pattern-003`: 야간 작업 소음 기준 안내와 현장 점검을 요청합니다. 야간 작업 소음 기준 안내와 현장 점검을 요청합니다.
- `eval-construction_noise_time_pattern-002`: 밤마다 공사장 소음이 반복되어 단속이 필요합니다. 밤마다 공사장 소음이 반복되어 단속이 필요합니다.
- `eval-construction_noise_time_pattern-001`: 새벽 공사 소음과 진동 때문에 잠을 잘 수 없습니다. 새벽 공사 소음과 진동 때문에 잠을 잘 수 없습니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 침수/배수 불량 위험

- scenario_id: `flood_drainage_risk`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `SAFETY_RISK_SIGNAL`
- priority: `HIGH`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 배수 시스템 안전 점검 필요
- summary: 영등포구에서 침수 및 배수 불량 관련 민원이 집중적으로 제기되고 있어 안전 점검이 필요합니다.
- problem: 우천 시 맨홀 주변 역류와 배수 불량으로 인한 침수 위험 증가

### Recommended Actions

- [None] 긴급 현장 점검 (evidence: eval-flood_drainage_risk-001, eval-flood_drainage_risk-002)

### Evidence Preview

- `eval-flood_drainage_risk-001`: 비가 오면 맨홀 주변 물이 역류해 보도 침수 위험이 큽니다. 비가 오면 맨홀 주변 물이 역류해 보도 침수 위험이 큽니다.
- `eval-flood_drainage_risk-002`: 우수관 배수 불량으로 빗물받이가 막혀 도로에 물이 고입니다. 우수관 배수 불량으로 빗물받이가 막혀 도로에 물이 고입니다.
- `eval-flood_drainage_risk-003`: 하수도 역류 냄새와 침수 우려가 반복되어 사전 점검이 필요합니다. 하수도 역류 냄새와 침수 우려가 반복되어 사전 점검이 필요합니다.
- `eval-flood_drainage_risk-004`: 집중호우 전에 배수로와 맨홀을 정비해 주세요. 집중호우 전에 배수로와 맨홀을 정비해 주세요.
- `eval-flood_drainage_risk-005`: 저지대 골목 배수가 안 돼 차량과 보행자 안전이 걱정됩니다. 저지대 골목 배수가 안 돼 차량과 보행자 안전이 걱정됩니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 무단투기/쓰레기 적치 반복

- scenario_id: `illegal_dumping_recurring`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `PUBLIC_GUIDANCE_NEEDED`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 무단투기 반복 민원 대응
- summary: 동작구에서 무단투기 민원이 반복적으로 제기되고 있으며, 특히 야간에 집중되어 있어 악취와 환경 불편이 보고됨.
- problem: 무단투기와 관련된 안내 부족 및 현장 조치의 실효성 부족이 주요 원인으로 추정됨.

### Recommended Actions

- [None] 무단투기 반복 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: eval-illegal_dumping_recurring-001, eval-illegal_dumping_recurring-002)

### Evidence Preview

- `eval-illegal_dumping_recurring-001`: 골목 입구에 쓰레기 무단투기가 반복되어 악취가 납니다. 골목 입구에 쓰레기 무단투기가 반복되어 악취가 납니다.
- `eval-illegal_dumping_recurring-002`: 생활폐기물이 계속 적치되어 정기 청소와 단속이 필요합니다. 생활폐기물이 계속 적치되어 정기 청소와 단속이 필요합니다.
- `eval-illegal_dumping_recurring-003`: 무단투기 금지 안내문이 부족하고 같은 위치에 쓰레기가 쌓입니다. 무단투기 금지 안내문이 부족하고 같은 위치에 쓰레기가 쌓입니다.
- `eval-illegal_dumping_recurring-004`: 밤마다 폐기물을 몰래 버려 주변이 지저분합니다. 밤마다 폐기물을 몰래 버려 주변이 지저분합니다.
- `eval-illegal_dumping_recurring-005`: 쓰레기 방치로 보행이 불편하니 청소와 단속을 강화해 주세요. 쓰레기 방치로 보행이 불편하니 청소와 단속을 강화해 주세요.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 장애인·고령자·외국인 접근성/이용 어려움

- scenario_id: `accessibility_vulnerable_groups`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `PUBLIC_GUIDANCE_NEEDED`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 접근성 개선을 위한 온라인 서비스 안내 강화
- summary: 고령자, 장애인, 외국인 등 취약계층의 온라인 신청 및 현장 이용 불편 지속
- problem: 신청 절차와 안내 부족으로 인한 사용자 경험 저하

### Recommended Actions

- [None] 온라인 안내 체크리스트 추가 (evidence: eval-accessibility_vulnerable_groups-001, eval-accessibility_vulnerable_groups-002)

### Evidence Preview

- `eval-accessibility_vulnerable_groups-001`: 고령자가 온라인 신청 절차를 이해하기 어려워 도움을 요청합니다. 고령자가 온라인 신청 절차를 이해하기 어려워 도움을 요청합니다.
- `eval-accessibility_vulnerable_groups-002`: 장애인 이용자가 예약 화면에서 접근성 버튼을 찾기 어렵습니다. 장애인 이용자가 예약 화면에서 접근성 버튼을 찾기 어렵습니다.
- `eval-accessibility_vulnerable_groups-003`: 외국어 안내가 부족해 외국인이 신청 방법을 이해하지 못합니다. 외국어 안내가 부족해 외국인이 신청 방법을 이해하지 못합니다.
- `eval-accessibility_vulnerable_groups-004`: 휠체어 이용자가 현장 안내 동선을 알기 어렵습니다. 휠체어 이용자가 현장 안내 동선을 알기 어렵습니다.
- `eval-accessibility_vulnerable_groups-005`: 취약계층을 위한 쉬운 안내와 대체 신청 경로가 필요합니다. 취약계층을 위한 쉬운 안내와 대체 신청 경로가 필요합니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

