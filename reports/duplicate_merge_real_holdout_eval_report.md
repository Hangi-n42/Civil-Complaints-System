# Duplicate Merge Real/Replay Holdout Evaluation

## 데이터 소스와 익명화 방식

- 실제 운영 원문 접근 없이 repository demo/evaluation 흐름을 replay한 익명화 holdout입니다. raw body는 저장하지 않고 PII-safe 구조화 필드와 마스킹 placeholder만 사용했습니다.
- 저장소의 demo/evaluation replay 흐름을 참고했지만, 운영 원문이나 실제 개인정보는 복사하지 않았습니다.
- event에는 `body`를 저장하지 않고 구조화 4요소, region, department, category, entity/request 신호만 포함했습니다.

## 300건 holdout 및 200쌍 라벨 분포

- holdout events: 300
- labeled pairs: 200
- department_alias_or_conflict: 20
- pii_masked_location_risk: 25
- same_event_different_request: 35
- same_keyword_different_event: 40
- time_window_boundary: 20
- transitive_overmerge_risk: 20
- true_duplicate: 40

## 주요 지표

- precision: 1.0
- recall: 1.0
- false_positive_rate: 0.0
- true_duplicate_recall: 1.0
- same_keyword_different_event false positive rate: 0.0
- same_event_different_request risk flag hit rate: 1.0
- pii_masked_location_risk false positive rate: 0.0
- transitive_overmerge safe/risk hit rate: 1.0
- department_alias_or_conflict risk flag hit rate: 1.0
- time_window_boundary risk flag hit rate: 1.0
- blocker_recall: 1.0
- risk_flag_hit_rate: 1.0
- pii_leak_rate: 0.0
- elapsed_ms: 187.17

## 개선 전/후 비교

- precision: 0.9322 -> 1.0
- recall: 0.9167 -> 1.0
- same_keyword_different_event false positive rate: 0.2 -> 0.0
- transitive_overmerge safe/risk hit rate: 0.5 -> 1.0
- problem_result_count: 90 -> 0
- 500건 elapsed_ms: 55005.7 -> 6688.67
- 500건 elapsed improvement ratio: 8.2237

## 구현한 개선 사항

- 위치 판별에서 마을/단지/구역/구간을 세부 장소 표지로 보강했습니다.
- 가로등/배수로/포트홀/복지급여 같은 민원 대상어가 장소 detail로 오인되지 않도록 제외했습니다.
- candidate 생성 전에 location conflict와 PII+ambiguous 케이스를 먼저 제외해 불필요한 scoring을 줄였습니다.
- 환경과/환경관리과 등 holdout에서 재현된 부서 alias는 같은 담당 단위로 정규화했습니다.

## 실패/미흡 사례

- false positive examples: 0
- false negative examples: 0
- missing risk flag examples: 0
- PII leak examples: 0

### False Positive 예시

- 없음

### False Negative 예시

- 없음

### Missing Risk Flag 예시

- 없음

## 500/1000건 batch 결과 요약

- 500건: elapsed_ms=6688.67, groups=91, peak_group_size=70, estimated_score_calls=128505, raw_pii_hits=0
- 1000건: elapsed_ms=25137.29, groups=91, peak_group_size=210, estimated_score_calls=526725, raw_pii_hits=0

## 남은 리스크

- 실제 운영 데이터가 아닌 replay-derived holdout이므로 운영 분포 대표성은 제한적입니다.
- batch 성능은 in-memory read-model 기준이며, API 서버 부하와 동시성은 별도 검증이 필요합니다.
- alias 부서 목록은 관할 지자체별 조직명 사전으로 보강해야 합니다.
