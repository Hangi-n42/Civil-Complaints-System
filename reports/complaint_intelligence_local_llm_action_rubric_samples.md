# Local LLM PublicAgencyInsight 샘플 리뷰

- Provider: `local`
- Model: `exaone3.5:7.8b`
- Sample count: `11`

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
- title: 도로 침하/싱크홀 급증 대응
- summary: 중구 지역에서 최근 3시간 동안 도로 침하 관련 민원이 급증하여 안전 위험이 제기됨.
- problem: 도로 포트홀 및 침하 발생으로 인한 시민 안전 위협 증가

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
- title: 초등학교 앞 불법주정차 민원 대응
- summary: 초등학교 주변 불법주정차 민원이 급증, 안내 부족과 단속 공백이 주요 문제점으로 지적됨.
- problem: 출퇴근 및 등하교 시간대에 반복적인 불법주정차 민원 발생으로 인한 시민 불편 증가.

### Recommended Actions

- [None] 현장 안내 표지 설치 (evidence: demo-illegal_parking_enforcement-001, demo-illegal_parking_enforcement-002)

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
- title: 대형폐기물 배출 안내 개선 필요
- summary: 동구 지역에서 대형폐기물 배출 관련 문의가 증가하여 신청 절차 및 지원 기준에 대한 안내 부족이 확인됨.
- problem: 시민들이 대형폐기물 배출 절차와 관련된 정보 부족으로 불편을 겪고 있음.

### Recommended Actions

- [None] 대형폐기물 배출 안내 FAQ 페이지 보강 (evidence: demo-bulky_waste_guidance-001, demo-bulky_waste_guidance-002)

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
- title: 복지 지원 신청 안내 개선
- summary: 중구 지역에서 복지 지원 신청 절차와 기준에 대한 이해 어려움이 반복적으로 제기되고 있습니다.
- problem: 신청 절차와 지원 기준에 대한 명확한 안내 부족으로 인한 시민 혼란

### Recommended Actions

- [None] FAQ 페이지 보강 (evidence: demo-welfare_support_process-001, demo-welfare_support_process-002)

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
- title: 야간 악취 민원 처리 개선
- summary: 야간 시간대 악취 민원 증가로 인한 시민 불편 해소 필요
- problem: 야간 시간대 악취 민원이 집중되며, 시민들은 현장 확인과 안내 부족을 호소하고 있음

### Recommended Actions

- [None] 야간 악취 대응 프로세스 개선 (evidence: demo-odor_night_hotspot-001, demo-odor_night_hotspot-002)

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
- confidence/grounding/actionability: `0.8458` / `1.0` / `0.8`
- title: 공공자전거 앱 사용성 개선 필요
- summary: 성동구에서 공공자전거 앱의 예약 및 대여 절차에 대한 불편 신고가 반복적으로 접수되고 있습니다.
- problem: 공공자전거 앱의 복잡한 절차와 부족한 안내로 인해 시민들이 불편을 겪고 있습니다.

### Recommended Actions

- [None] 앱 인터페이스 단순화 (evidence: eval-public_bike_app_ux-001, eval-public_bike_app_ux-002)

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
- summary: 중구 도로관리과의 민원 처리 지연 문제로 시민 불만 증가.
- problem: 도로 보수 요청의 처리 지연과 안내 부족으로 인한 민원 누적.

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
- summary: 관악구에서 악취 및 하수 냄새 관련 민원이 반복적으로 접수되고 있으며, 완료 안내 후에도 문제 해결이 미흡한 것으로 나타남.
- problem: 민원 처리 후 재발 문제로 인한 안내 부족 및 현장 조치 실효성 미흡

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
- confidence/grounding/actionability: `0.8458` / `1.0` / `0.8`
- title: 야간 공사 소음 민원 대응
- summary: 마포구에서 퇴근 후 야간 시간대 공사 소음 관련 민원이 집중적으로 제기되고 있습니다.
- problem: 야간 공사 소음에 대한 명확한 기준 안내 부족과 단속 활동의 미흡으로 인한 시민 불편 증가.

### Recommended Actions

- [None] 야간 공사 소음 기준 명시 (evidence: eval-construction_noise_time_pattern-001, eval-construction_noise_time_pattern-002)

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
- title: 공공자전거 앱 접근성 개선 필요
- summary: 중구 지역에서 고령자와 장애인의 공공자전거 앱 사용 불편 지속 보고
- problem: 고령자와 장애인을 위한 앱 접근성 및 안내 부족으로 인한 이용 어려움

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
- title: 가로등 반복 고장 대응 계획
- summary: 중구 지역에서 가로등 고장 민원이 집중적으로 발생하고 있어 안전 및 서비스 품질 개선 필요.
- problem: 가로등 고장이 반복적으로 발생하여 시민 안전과 야간 보행 환경에 부정적 영향을 미침.

### Recommended Actions

- [None] 점검 절차 검토 및 개선 (evidence: eval-streetlight_failure_recurring-001, eval-streetlight_failure_recurring-002)

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

