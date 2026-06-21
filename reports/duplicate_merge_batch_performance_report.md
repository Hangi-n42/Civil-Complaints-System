# Duplicate Merge Batch Performance Report

- 데이터: 실제 운영 원문 접근 없이 repository demo/evaluation 흐름을 replay한 익명화 holdout입니다. raw body는 저장하지 않고 PII-safe 구조화 필드와 마스킹 placeholder만 사용했습니다.
- 측정 대상: DuplicateMergeService.run_analysis in-memory batch

| events | elapsed_ms | groups | blockers | peak_group_size | estimated_score_calls | score_calls_per_event | raw_pii_hits |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 500 | 6688.67 | 91 | 26 | 70 | 128505 | 257.01 | 0 |
| 1000 | 25137.29 | 91 | 26 | 210 | 526725 | 526.725 | 0 |

## Top Groups

### 500건
- size=70, confidence=0.8516, location_state=exact, risk_flags=['DEPARTMENT_MISMATCH', 'PII_RISK', 'REQUEST_TYPE_MISMATCH']
- size=20, confidence=0.9947, location_state=exact, risk_flags=['PII_RISK']
- size=20, confidence=0.9947, location_state=exact, risk_flags=[]
- size=20, confidence=0.9947, location_state=exact, risk_flags=[]
- size=20, confidence=0.9947, location_state=exact, risk_flags=[]
### 1000건
- size=210, confidence=0.8486, location_state=exact, risk_flags=['DEPARTMENT_MISMATCH', 'PII_RISK', 'REQUEST_TYPE_MISMATCH']
- size=40, confidence=0.9937, location_state=exact, risk_flags=['PII_RISK', 'TIME_WINDOW_TOO_WIDE']
- size=40, confidence=0.9937, location_state=exact, risk_flags=['TIME_WINDOW_TOO_WIDE']
- size=40, confidence=0.9937, location_state=exact, risk_flags=['TIME_WINDOW_TOO_WIDE']
- size=40, confidence=0.9937, location_state=exact, risk_flags=['TIME_WINDOW_TOO_WIDE']
