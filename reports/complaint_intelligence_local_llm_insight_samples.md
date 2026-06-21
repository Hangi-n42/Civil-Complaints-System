# Local LLM PublicAgencyInsight 샘플 리뷰

- Provider: `local`
- Model: `exaone3.5:7.8b`
- Sample count: `23`

## 도로 침하/싱크홀 급증

- scenario_id: `sinkhole_hotspot`
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
- title: 도로 싱크홀 위험 대응
- summary: 중구 지역에서 최근 싱크홀 관련 민원이 급증하여 현장 안전과 이용 안전에 대한 우려가 제기됨.
- problem: 도로 포트홀 및 침하 발생으로 인한 안전 위험 증가

### Recommended Actions

- [None] 긴급 현장 점검 (evidence: demo-sinkhole_hotspot-001, demo-sinkhole_hotspot-002)

### Evidence Preview

- `demo-sinkhole_hotspot-001`: 도로 포트홀 및 침하 발생시 대처방법 도로 포트홀 및 침하 발생시 대처방법
- `demo-sinkhole_hotspot-002`: 도로의 아스팔트 포장 언제부터 도로점용허가가 가능한지? 도로의 아스팔트 포장 언제부터 도로점용허가가 가능한지?
- `demo-sinkhole_hotspot-003`: 도로를 주행하다가 포트홀로 인해 차량이 파손되었습니다. 보상 가능할까요? 도로를 주행하다가 포트홀로 인해 차량이 파손되었습니다. 보상 가능할까요?
- `demo-sinkhole_hotspot-004`: (경기북부청)싱크홀(땅꺼짐) 발생 시 어떻게 해야하나요? (경기북부청)싱크홀(땅꺼짐) 발생 시 어떻게 해야하나요?
- `demo-sinkhole_hotspot-005`: 도로위에 물이 누수현상 및 땅꺼짐 도로위에 물이 누수현상 및 땅꺼짐

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 불법주정차 특정 시간대 반복

- scenario_id: `illegal_parking_enforcement`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `HOTSPOT_RESPONSE_REQUIRED`
- priority: `MEDIUM`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 초등학교 앞 불법주정차 단속 강화 필요
- summary: 초등학교 주변에서 출퇴근 및 등하교 시간대 불법주정차 민원이 급증하여 안전 및 불편 문제 제기.
- problem: 출퇴근 시간대 단속 공백 및 현장 안내 부족으로 인한 민원 증가

### Recommended Actions

- [None] 초등학교 앞 불법주정차 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: demo-illegal_parking_enforcement-001, demo-illegal_parking_enforcement-002)

### Evidence Preview

- `demo-illegal_parking_enforcement-001`: 불법주정차 단속 및 거주자우선주차 지역 확대 요청 불법주정차 단속 및 거주자우선주차 지역 확대 요청
- `demo-illegal_parking_enforcement-002`: 고가도로 밑에 매일 매일 불법주정차 차량 단속 좀 해주세요 고가도로 밑에 매일 매일 불법주정차 차량 단속 좀 해주세요
- `demo-illegal_parking_enforcement-003`: 불법주차한 차량으로 인한 불편 및 위험 불법주차한 차량으로 인한 불편 및 위험
- `demo-illegal_parking_enforcement-004`: 불법주정차 차량 신고 방법을 알고 싶습니다. 불법주정차 차량 신고 방법을 알고 싶습니다.
- `demo-illegal_parking_enforcement-005`: 불법주정차위반 단속 의견제출 방법 문의 불법주정차위반 단속 의견제출 방법 문의

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 대형폐기물 배출 방법 문의 반복

- scenario_id: `bulky_waste_guidance`
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
- title: 대형폐기물 배출 안내 강화 필요
- summary: 동구 지역에서 대형폐기물 배출 관련 문의가 증가하여 신청 절차 및 배출 기준에 대한 안내 부족이 확인됨.
- problem: 시민들이 대형폐기물 배출 절차와 기준에 대한 명확한 안내 부족으로 불편을 겪고 있음.

### Recommended Actions

- [None] 대형폐기물 배출 안내 페이지 보강 (evidence: demo-bulky_waste_guidance-001, demo-bulky_waste_guidance-002)

### Evidence Preview

- `demo-bulky_waste_guidance-001`: 진북면 대형폐기물 수거 일정 및 스티커 발부 방법 진북면 대형폐기물 수거 일정 및 스티커 발부 방법
- `demo-bulky_waste_guidance-002`: 강동구 대형폐기물 배출 신고방법이 궁금합니다. 강동구 대형폐기물 배출 신고방법이 궁금합니다.
- `demo-bulky_waste_guidance-003`: 대구 남구 대형폐기물 및 폐가전제품 배출 신고 안내 대구 남구 대형폐기물 및 폐가전제품 배출 신고 안내
- `demo-bulky_waste_guidance-004`: 대형폐기물 수거신청(서울특별시 강동구 암사동) 대형폐기물 수거신청(서울특별시 강동구 암사동)
- `demo-bulky_waste_guidance-005`: 대형폐기물 배출신고에 대하여 절차가 궁금해요 대형폐기물 배출신고에 대하여 절차가 궁금해요

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 복지 지원 기준/신청 절차 불편 반복

- scenario_id: `welfare_support_process`
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
- title: 복지 지원 안내 개선 필요
- summary: 중구 지역에서 복지 지원 신청 절차와 기준에 대한 이해 어려움이 반복적으로 제기되고 있습니다.
- problem: 신청 절차와 지원 기준에 대한 명확한 안내 부족으로 인한 시민 혼란

### Recommended Actions

- [None] FAQ/안내 페이지 보강 (evidence: demo-welfare_support_process-001, demo-welfare_support_process-002)

### Evidence Preview

- `demo-welfare_support_process-001`: 학생 마음바우처 지원대상, 신청방법, 치료비 청구 절차 학생 마음바우처 지원대상, 신청방법, 치료비 청구 절차
- `demo-welfare_support_process-002`: 긴급복지지원은 어떤 대상이 신청할수 있나요? 긴급복지지원은 어떤 대상이 신청할수 있나요?
- `demo-welfare_support_process-003`: 긴급복지 지원 대상 및 기준 문의 긴급복지 지원 대상 및 기준 문의
- `demo-welfare_support_process-004`: 주택관리사 자격증 신청절차 및 구비서류 주택관리사 자격증 신청절차 및 구비서류
- `demo-welfare_support_process-005`: 2026년 기초연금 대상 및 지원 기준, 신청방법 2026년 기초연금 대상 및 지원 기준, 신청방법

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 악취/냄새/하수 민원 야간 집중

- scenario_id: `odor_night_hotspot`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `HOTSPOT_RESPONSE_REQUIRED`
- priority: `MEDIUM`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 야간 하수 악취 민원 대응
- summary: 야간 시간대에 남구에서 하수 악취 관련 민원이 집중적으로 발생하고 있습니다.
- problem: 야간 시간대에 생활환경 불편과 배수 불량이 주요 원인으로 추정됩니다.

### Recommended Actions

- [None] 야간 유지보수 점검 프로세스 개선 (evidence: demo-odor_night_hotspot-006)

### Evidence Preview

- `demo-odor_night_hotspot-001`: ▲▲▲공장 하수구 냄새 때문에 너무 불편합니다. ▲▲▲공장 하수구 냄새 때문에 너무 불편합니다.
- `demo-odor_night_hotspot-002`: 길가에 쓰레기가 무단방치 되어있어서 냄새가 나요. 처리 가능할까요? 길가에 쓰레기가 무단방치 되어있어서 냄새가 나요. 처리 가능할까요?
- `demo-odor_night_hotspot-003`: 개인하수처리시설(정화조, 오수처리시설) 폐쇄 개인하수처리시설(정화조, 오수처리시설) 폐쇄
- `demo-odor_night_hotspot-004`: 개인하수처리시설(정화조, 오수처리시설) 설치 개인하수처리시설(정화조, 오수처리시설) 설치
- `demo-odor_night_hotspot-005`: 개인하수처리시설(정화조, 오수처리시설) 설치/변경신고 개인하수처리시설(정화조, 오수처리시설) 설치/변경신고

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 공공자전거/앱 예약·대여 UX 불편

- scenario_id: `public_bike_app_ux`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `ACCESSIBILITY_OR_USABILITY_ISSUE`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 공공자전거 앱 사용성 개선 필요
- summary: 성동구에서 공공자전거 앱의 복잡한 예약 및 대여 절차로 인한 민원이 증가하고 있습니다.
- problem: 반복적인 앱 사용 불편과 오류로 인한 시민 불만 증가

### Recommended Actions

- [None] 접근성/사용성 반복 불편 이용 절차의 오류·복잡 단계를 확인하고 안내 문구를 보강합니다. (evidence: eval-public_bike_app_ux-001, eval-public_bike_app_ux-002)

### Evidence Preview

- `eval-public_bike_app_ux-001`: 공공자전거 앱 예약 절차가 불편하고 대여 단계가 너무 복잡합니다. 공공자전거 앱 예약 절차가 불편하고 대여 단계가 너무 복잡합니다.
- `eval-public_bike_app_ux-002`: 대여 신청 중 결제 오류가 반복되어 자전거를 빌리지 못했습니다. 대여 신청 중 결제 오류가 반복되어 자전거를 빌리지 못했습니다.
- `eval-public_bike_app_ux-003`: 앱 로그인 후 예약 기준을 이해하기 어려워 현장에서 계속 문의합니다. 앱 로그인 후 예약 기준을 이해하기 어려워 현장에서 계속 문의합니다.
- `eval-public_bike_app_ux-004`: 공공자전거 대여 화면 안내가 부족해서 결제와 예약을 다시 해야 합니다. 공공자전거 대여 화면 안내가 부족해서 결제와 예약을 다시 해야 합니다.
- `eval-public_bike_app_ux-005`: 예약 취소와 재대여 절차가 복잡해 이용이 중단됩니다. 예약 취소와 재대여 절차가 복잡해 이용이 중단됩니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 부서 처리 지연/미처리 누적

- scenario_id: `department_delay_backlog`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `PROCESS_DELAY_RISK`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 도로관리과 처리 지연 개선
- summary: 중구 도로관리과의 민원 처리 지연이 누적되어 시민 불만 증가.
- problem: 도로 보수 및 유지보수 민원의 처리 지연과 소통 부족으로 인한 시민 불편 증가.

### Recommended Actions

- [None] 도로관리과 처리 지연/미처리 누적 처리 흐름을 점검하고 반복 민원 원인별 개선 과제를 정리합니다. (evidence: eval-department_delay_backlog-001, eval-department_delay_backlog-002)

### Evidence Preview

- `eval-department_delay_backlog-001`: 도로 보수 요청이 접수된 지 오래됐는데 처리되지 않았습니다. 도로 보수 요청이 접수된 지 오래됐는데 처리되지 않았습니다.
- `eval-department_delay_backlog-002`: 같은 부서 담당 민원이 계속 pending 상태로 남아 있습니다. 같은 부서 담당 민원이 계속 pending 상태로 남아 있습니다.
- `eval-department_delay_backlog-003`: 처리 기간 안내 없이 미처리 상태가 길어져 불편합니다. 처리 기간 안내 없이 미처리 상태가 길어져 불편합니다.
- `eval-department_delay_backlog-004`: 보수 요청 답변이 없어 진행 상황을 확인하고 싶습니다. 보수 요청 답변이 없어 진행 상황을 확인하고 싶습니다.
- `eval-department_delay_backlog-005`: 담당 부서에서 아직 조치 일정을 알려주지 않았습니다. 담당 부서에서 아직 조치 일정을 알려주지 않았습니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

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
- summary: 관악구에서 악취 및 하수 냄새 관련 반복 민원 증가로 시민 불만 고조.
- problem: 처리 완료 후에도 동일 민원 재발로 인한 불만 증가.

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
- title: 야간 공사 소음 민원 집중 대응
- summary: 마포구에서 퇴근 이후 야간 시간대 공사 소음 민원이 집중적으로 제기되고 있습니다.
- problem: 야간 및 퇴근 이후 시간대에 공사 소음 관련 민원이 지속적으로 발생하여 시민 불편이 증가하고 있습니다.

### Recommended Actions

- [None] 공사 소음 시간대 집중 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: eval-construction_noise_time_pattern-005, eval-construction_noise_time_pattern-004)

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

## 접근성/고령자·장애인 이용 어려움

- scenario_id: `accessibility_usage_barrier`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `SERVICE_DESIGN_IMPROVEMENT`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 공공자전거 예약 불편 개선
- summary: 중구 지역에서 고령자와 장애인의 공공자전거 예약 과정에서 접근성 문제로 인한 민원 증가.
- problem: 신청 절차와 안내 부족으로 디지털 취약계층의 이용 불편 지속.

### Recommended Actions

- [None] 공공자전거 예약/대여 불편 이용 절차의 오류·복잡 단계를 확인하고 안내 문구를 보강합니다. (evidence: eval-accessibility_usage_barrier-001, eval-accessibility_usage_barrier-002)

### Evidence Preview

- `eval-accessibility_usage_barrier-001`: 고령자가 복지 신청 앱을 쓰기 어렵고 글씨와 단계 안내가 부족합니다. 고령자가 복지 신청 앱을 쓰기 어렵고 글씨와 단계 안내가 부족합니다.
- `eval-accessibility_usage_barrier-002`: 장애인 이용자가 예약 화면에서 필요한 버튼을 찾기 어렵습니다. 장애인 이용자가 예약 화면에서 필요한 버튼을 찾기 어렵습니다.
- `eval-accessibility_usage_barrier-004`: 디지털 취약계층이 로그인과 본인 확인 단계에서 계속 막힙니다. 디지털 취약계층이 로그인과 본인 확인 단계에서 계속 막힙니다.
- `eval-accessibility_usage_barrier-005`: 앱 화면 접근성이 낮아 상담창구 문의가 반복됩니다. 앱 화면 접근성이 낮아 상담창구 문의가 반복됩니다.
- `eval-accessibility_usage_barrier-001`: 고령자가 복지 신청 앱을 쓰기 어렵고 글씨와 단계 안내가 부족합니다. 접근성 부족으로 신청 중단과 반복 문의가 발생합니다. 고령자와 장애인을 위한 쉬운 안내와 대체 신청 경로를 요청합니다. 디지털 취약계층 관련 이용

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 가로등/보안등 고장 반복

- scenario_id: `streetlight_failure_recurring`
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
- title: 가로등 반복 고장 대응
- summary: 중구 지역에서 가로등 고장 민원이 반복적으로 접수되어 야간 보행 안전에 문제 발생.
- problem: 가로등 고장이 특정 지역에서 지속적으로 발생하여 시민 안전에 위협을 주고 있음.

### Recommended Actions

- [None] 현장 점검 실시 (evidence: eval-streetlight_failure_recurring-001, eval-streetlight_failure_recurring-002)

### Evidence Preview

- `eval-streetlight_failure_recurring-001`: 공원 입구 가로등이 며칠째 꺼져 있어 밤길이 위험합니다. 공원 입구 가로등이 며칠째 꺼져 있어 밤길이 위험합니다.
- `eval-streetlight_failure_recurring-002`: 보안등 고장으로 골목이 어둡고 안전이 걱정됩니다. 보안등 고장으로 골목이 어둡고 안전이 걱정됩니다.
- `eval-streetlight_failure_recurring-003`: 같은 위치 가로등이 반복적으로 고장 납니다. 같은 위치 가로등이 반복적으로 고장 납니다.
- `eval-streetlight_failure_recurring-004`: 가로등 수리를 요청했지만 다시 꺼졌습니다. 가로등 수리를 요청했지만 다시 꺼졌습니다.
- `eval-streetlight_failure_recurring-005`: 야간 보행 안전을 위해 조명 점검이 필요합니다. 야간 보행 안전을 위해 조명 점검이 필요합니다.

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
- summary: 영등포구에서 침수 및 배수 불량 관련 민원이 급증하여 현장 안전 위험이 확인됨.
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
- summary: 동작구에서 무단투기 민원이 반복적으로 제기되고 있어, 안내 부족과 현장 조치 실효성에 대한 우려가 제기됨.
- problem: 무단투기와 쓰레기 적치 관련 민원이 지속적으로 발생하며, 특히 안내 부족과 단속 강화 요청이 높음.

### Recommended Actions

- [None] 무단투기 반복 FAQ와 신청 절차 안내를 보강하고 문의 응대 기준을 정리합니다. (evidence: eval-illegal_dumping_recurring-001, eval-illegal_dumping_recurring-002)

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

## 공원/놀이터 시설 파손 및 이용 안전

- scenario_id: `park_playground_facility_safety`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `SAFETY_RISK_SIGNAL`
- priority: `MEDIUM`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 공원 시설 파손 안전 점검 필요
- summary: 서초구 공원 시설에서 파손 신고가 집중적으로 발생하여 이용자 안전 위협이 확인됨.
- problem: 공원 내 놀이터 및 시설물의 파손으로 인한 안전 위험 증가

### Recommended Actions

- [None] 긴급 현장 점검 (evidence: eval-park_playground_facility_safety-001, eval-park_playground_facility_safety-002)

### Evidence Preview

- `eval-park_playground_facility_safety-001`: 놀이터 미끄럼틀이 파손되어 아이들이 다칠 위험이 있습니다. 놀이터 미끄럼틀이 파손되어 아이들이 다칠 위험이 있습니다.
- `eval-park_playground_facility_safety-002`: 공원 벤치가 깨져 있고 보수 일정 안내가 없습니다. 공원 벤치가 깨져 있고 보수 일정 안내가 없습니다.
- `eval-park_playground_facility_safety-003`: 산책로 바닥이 들떠 야간 이용 시 넘어질까 불안합니다. 산책로 바닥이 들떠 야간 이용 시 넘어질까 불안합니다.
- `eval-park_playground_facility_safety-004`: 공원 시설 고장이 반복되는데 임시 안전 조치가 필요합니다. 공원 시설 고장이 반복되는데 임시 안전 조치가 필요합니다.
- `eval-park_playground_facility_safety-005`: 놀이터 시설 점검과 보수 일정을 알려 주세요. 놀이터 시설 점검과 보수 일정을 알려 주세요.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 가로등/보안등 고장 반복 확장

- scenario_id: `security_light_dark_walkway`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `HOTSPOT_RESPONSE_REQUIRED`
- priority: `MEDIUM`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 야간 보행 안전 개선
- summary: 도봉구에서 가로등 및 보안등 고장으로 인한 야간 보행 안전 문제 발생.
- problem: 반복적인 가로등/보안등 고장으로 인한 야간 보행 안전 위협 및 시민 불편 증가.

### Recommended Actions

- [None] 즉시 현장 점검 (evidence: eval-security_light_dark_walkway-001, eval-security_light_dark_walkway-002)

### Evidence Preview

- `eval-security_light_dark_walkway-001`: 골목 보안등이 계속 꺼져 밤길 보행이 불안합니다. 골목 보안등이 계속 꺼져 밤길 보행이 불안합니다.
- `eval-security_light_dark_walkway-002`: 가로등 고장이 반복되어 야간에 시야 확보가 어렵습니다. 가로등 고장이 반복되어 야간에 시야 확보가 어렵습니다.
- `eval-security_light_dark_walkway-003`: 어두운 보행 구간에 임시 조명이나 안전 안내가 필요합니다. 어두운 보행 구간에 임시 조명이나 안전 안내가 필요합니다.
- `eval-security_light_dark_walkway-004`: 같은 위치 조명 고장 신고를 여러 번 했습니다. 같은 위치 조명 고장 신고를 여러 번 했습니다.
- `eval-security_light_dark_walkway-005`: 야간 보행 안전을 위해 보안등 교체와 현장 점검을 요청합니다. 야간 보행 안전을 위해 보안등 교체와 현장 점검을 요청합니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 버스 정류장/노선·배차 불편

- scenario_id: `bus_route_headway_discomfort`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `SERVICE_DESIGN_IMPROVEMENT`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 버스 노선 불편 개선
- summary: 강서구 교통행정과에서 버스 배차 간격, 정류장 접근성, 노선 안내 부족으로 인한 민원 증가.
- problem: 반복적인 버스 이용 불편 민원으로 인한 시민 불편 확인.

### Recommended Actions

- [None] 버스 노선 및 배차 시스템 개선 검토 (evidence: eval-bus_route_headway_discomfort-001, eval-bus_route_headway_discomfort-002)

### Evidence Preview

- `eval-bus_route_headway_discomfort-001`: 버스 배차 간격이 길어 출근 시간마다 정류장에서 오래 기다립니다. 버스 배차 간격이 길어 출근 시간마다 정류장에서 오래 기다립니다.
- `eval-bus_route_headway_discomfort-002`: 정류장 위치가 멀고 노선 안내가 부족해 환승이 어렵습니다. 정류장 위치가 멀고 노선 안내가 부족해 환승이 어렵습니다.
- `eval-bus_route_headway_discomfort-003`: 버스 도착 안내가 맞지 않아 이용 불편이 반복됩니다. 버스 도착 안내가 맞지 않아 이용 불편이 반복됩니다.
- `eval-bus_route_headway_discomfort-004`: 이 지역 노선 조정 검토와 배차 안내 개선이 필요합니다. 이 지역 노선 조정 검토와 배차 안내 개선이 필요합니다.
- `eval-bus_route_headway_discomfort-005`: 정류장 접근성이 낮아 대중교통 이용이 어렵습니다. 정류장 접근성이 낮아 대중교통 이용이 어렵습니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## CCTV/방범 안전 설치 요청

- scenario_id: `cctv_security_request`
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
- title: 야간 안전 민원 증가
- summary: 구로구에서 야간 보행 불안 및 방범 취약 관련 민원이 급증하여 안전 개선 요구 증가.
- problem: 조명 부족과 방범 취약 구간으로 인한 시민 안전 불만 증가.

### Recommended Actions

- [None] 긴급 조명 점검 (evidence: eval-cctv_security_request-001, eval-cctv_security_request-002)

### Evidence Preview

- `eval-cctv_security_request-001`: 골목이 밤에 너무 어두워 CCTV 설치와 방범 순찰이 필요합니다. 골목이 밤에 너무 어두워 CCTV 설치와 방범 순찰이 필요합니다.
- `eval-cctv_security_request-002`: 사각지대가 있어 야간 안전이 불안하니 현장 확인 바랍니다. 사각지대가 있어 야간 안전이 불안하니 현장 확인 바랍니다.
- `eval-cctv_security_request-003`: 방범 취약 구간인데 안내와 순찰이 부족합니다. 방범 취약 구간인데 안내와 순찰이 부족합니다.
- `eval-cctv_security_request-004`: CCTV 설치 검토와 조명 보강을 요청합니다. CCTV 설치 검토와 조명 보강을 요청합니다.
- `eval-cctv_security_request-005`: 늦은 시간 보행자가 불안해하는 구간을 점검해 주세요. 늦은 시간 보행자가 불안해하는 구간을 점검해 주세요.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 흡연/금연구역 단속 반복

- scenario_id: `smoking_enforcement_recurring`
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
- title: 금연구역 흡연 단속 및 안내 강화 필요
- summary: 종로구 금연구역에서 흡연과 담배꽁초 문제로 인한 민원이 지속적으로 제기되고 있습니다.
- problem: 금연구역 내 흡연 단속 부족과 안내 표지판 부족으로 인한 시민 불편이 반복적으로 발생하고 있습니다.

### Recommended Actions

- [None] 금연 안내 표지판 보강 (evidence: eval-smoking_enforcement_recurring-001, eval-smoking_enforcement_recurring-002)

### Evidence Preview

- `eval-smoking_enforcement_recurring-001`: 금연구역에서 흡연이 반복되어 간접흡연 피해가 큽니다. 금연구역에서 흡연이 반복되어 간접흡연 피해가 큽니다.
- `eval-smoking_enforcement_recurring-002`: 담배꽁초가 계속 쌓여 청소와 단속이 필요합니다. 담배꽁초가 계속 쌓여 청소와 단속이 필요합니다.
- `eval-smoking_enforcement_recurring-003`: 금연 안내 표지가 부족해 같은 장소에서 흡연이 계속됩니다. 금연 안내 표지가 부족해 같은 장소에서 흡연이 계속됩니다.
- `eval-smoking_enforcement_recurring-004`: 점심시간마다 흡연 단속을 강화해 주세요. 점심시간마다 흡연 단속을 강화해 주세요.
- `eval-smoking_enforcement_recurring-005`: 간접흡연 민원이 반복되니 안내문과 현장 점검이 필요합니다. 간접흡연 민원이 반복되니 안내문과 현장 점검이 필요합니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 불법 광고물/현수막 정비

- scenario_id: `illegal_banner_cleanup`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `FACILITY_MAINTENANCE_PRIORITY`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 불법 현수막 보행 안전 및 미관 개선
- summary: 송파구에서 불법 현수막으로 인한 보행 안전 위협과 도시 미관 저해 민원이 집중적으로 제기됨.
- problem: 보행로 주변 불법 현수막으로 인한 안전 위협과 도시 미관 저해가 반복적으로 발생하고 있음.

### Recommended Actions

- [None] 불법 현수막 정비 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: eval-illegal_banner_cleanup-001, eval-illegal_banner_cleanup-002)

### Evidence Preview

- `eval-illegal_banner_cleanup-001`: 불법 현수막이 횡단보도 시야를 가려 보행이 위험합니다. 불법 현수막이 횡단보도 시야를 가려 보행이 위험합니다.
- `eval-illegal_banner_cleanup-002`: 같은 사거리 광고물이 반복 설치되어 도시 미관을 해칩니다. 같은 사거리 광고물이 반복 설치되어 도시 미관을 해칩니다.
- `eval-illegal_banner_cleanup-003`: 보행로에 불법 광고물이 많아 현장 정비가 필요합니다. 보행로에 불법 광고물이 많아 현장 정비가 필요합니다.
- `eval-illegal_banner_cleanup-004`: 현수막 단속과 반복 위치 관리를 요청합니다. 현수막 단속과 반복 위치 관리를 요청합니다.
- `eval-illegal_banner_cleanup-005`: 도로 시야를 방해하는 광고물을 정비해 주세요. 도로 시야를 방해하는 광고물을 정비해 주세요.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 반려동물 배설물/목줄/유기동물 민원

- scenario_id: `pet_waste_leash_complaints`
- direct_llm_success: `True`
- fallback_used: `False`
- fallback_reason: `None`
- invalid_evidence_ids: `-`
- removed_actions: `0`
- repaired_actions: `0`
- retry_used/retry_success: `False` / `False`

### Final Insight

- type: `REGIONAL_SERVICE_GAP`
- priority: `LOW`
- confidence/grounding/actionability: `0.8458` / `1.0` / `1.0`
- title: 노원구 반려동물 관리 민원 강화
- summary: 노원구 공원 산책로에서 반려동물 배설물 및 목줄 관련 민원이 집중적으로 발생하고 있습니다.
- problem: 공원 내 반려동물 관리 부족으로 인한 위생 문제와 안전 우려가 시민들로부터 제기되고 있습니다.

### Recommended Actions

- [None] 반려동물 배설물/목줄 민원 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: eval-pet_waste_leash_complaints-001, eval-pet_waste_leash_complaints-002)

### Evidence Preview

- `eval-pet_waste_leash_complaints-001`: 공원 산책로에 반려동물 배설물이 방치되어 위생이 걱정됩니다. 공원 산책로에 반려동물 배설물이 방치되어 위생이 걱정됩니다.
- `eval-pet_waste_leash_complaints-002`: 목줄 미착용 개 때문에 아이들이 무서워합니다. 목줄 미착용 개 때문에 아이들이 무서워합니다.
- `eval-pet_waste_leash_complaints-003`: 반려동물 배설물 안내문과 단속이 부족합니다. 반려동물 배설물 안내문과 단속이 부족합니다.
- `eval-pet_waste_leash_complaints-004`: 같은 시간대 목줄 없이 산책하는 사례가 반복됩니다. 같은 시간대 목줄 없이 산책하는 사례가 반복됩니다.
- `eval-pet_waste_leash_complaints-005`: 유기동물 신고와 현장 순찰을 요청합니다. 유기동물 신고와 현장 순찰을 요청합니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

## 인허가/자격·서류 기준 안내 혼선

- scenario_id: `licensing_docs_guidance_confusion`
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
- title: 인허가 기준 안내 명확화 필요
- summary: 중랑구 민원여권과에서 인허가 기준과 제출 서류 안내 혼선으로 인한 민원 증가.
- problem: 신청자들이 인허가 기준과 필요 서류에 대한 명확한 안내 부족으로 혼란을 겪고 있음.

### Recommended Actions

- [None] FAQ/안내 페이지 보강 (evidence: eval-licensing_docs_guidance_confusion-001, eval-licensing_docs_guidance_confusion-002)

### Evidence Preview

- `eval-licensing_docs_guidance_confusion-001`: 인허가 신청 기준과 제출 서류가 헷갈려 상담이 필요합니다. 인허가 신청 기준과 제출 서류가 헷갈려 상담이 필요합니다.
- `eval-licensing_docs_guidance_confusion-002`: 자격 요건 안내가 어려워 어느 부서에 문의해야 할지 모르겠습니다. 자격 요건 안내가 어려워 어느 부서에 문의해야 할지 모르겠습니다.
- `eval-licensing_docs_guidance_confusion-003`: 면허 기준과 필요서류 체크리스트를 제공해 주세요. 면허 기준과 필요서류 체크리스트를 제공해 주세요.
- `eval-licensing_docs_guidance_confusion-004`: 담당 부서 안내가 부족해 신청 절차를 반복해서 문의합니다. 담당 부서 안내가 부족해 신청 절차를 반복해서 문의합니다.
- `eval-licensing_docs_guidance_confusion-005`: 인허가 기준 설명이 서로 달라 시민이 혼란스럽습니다. 인허가 기준 설명이 서로 달라 시민이 혼란스럽습니다.

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
- summary: 은평구 고령자 및 장애인의 온라인 민원 신청 절차 이해 어려움으로 인한 민원 증가.
- problem: 고령자와 장애인을 위한 온라인 서비스 접근성 및 안내 부족으로 인한 불편 반복.

### Recommended Actions

- [None] 고령자 및 장애인 친화적 안내 페이지 보강 (evidence: eval-accessibility_vulnerable_groups-001, eval-accessibility_vulnerable_groups-002)

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

## 어린이보호구역/통학 안전

- scenario_id: `school_zone_commute_safety`
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
- title: 어린이보호구역 통학 안전 강화 필요
- summary: 양천구 어린이보호구역에서 통학 시간대 불법 주정차와 과속으로 인한 안전 위험 민원 증가.
- problem: 등하교 시간대 단속 부족과 안전 안내 부족으로 인한 통학 안전 위협

### Recommended Actions

- [None] 어린이보호구역 통학 안전 집중 시간대 단속 동선을 조정하고 현장 안내를 병행합니다. (evidence: eval-school_zone_commute_safety-001, eval-school_zone_commute_safety-002)

### Evidence Preview

- `eval-school_zone_commute_safety-001`: 어린이보호구역에 등교 시간 불법주정차가 많아 통학 안전이 걱정됩니다. 어린이보호구역에 등교 시간 불법주정차가 많아 통학 안전이 걱정됩니다.
- `eval-school_zone_commute_safety-002`: 학교 앞 차량 속도가 빠르고 교통 위험이 반복됩니다. 학교 앞 차량 속도가 빠르고 교통 위험이 반복됩니다.
- `eval-school_zone_commute_safety-003`: 하교 시간대 단속과 안전 안내 표지를 보강해 주세요. 하교 시간대 단속과 안전 안내 표지를 보강해 주세요.
- `eval-school_zone_commute_safety-004`: 통학로 주변 현장 점검과 교통지도 요청합니다. 통학로 주변 현장 점검과 교통지도 요청합니다.
- `eval-school_zone_commute_safety-005`: 등하교 시간마다 차량 혼잡으로 아이들이 위험합니다. 등하교 시간마다 차량 혼잡으로 아이들이 위험합니다.

### Objective Review

- Strength: 최종 인사이트가 QualityGate와 GroundingVerifier 경로를 통과했습니다.
- Strength: 추천 조치가 evidence id와 연결되어 추적 가능합니다.
- Weakness: 자동 리뷰 기준에서는 큰 약점이 확인되지 않았습니다.
- Readiness: 데모 노출은 가능하지만 실제 운영 전 담당자 검토가 필요합니다.

