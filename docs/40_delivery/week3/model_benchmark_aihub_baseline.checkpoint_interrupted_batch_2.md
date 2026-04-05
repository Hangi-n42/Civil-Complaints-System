# Week3 모델 벤치마크 요약

- 생성 시각: 2026-04-05T21:22:11.726823+09:00
- 조건: temp=0.2, num_ctx=2048, num_predict=512, timeout=300s
- 케이스 수: 500
- 추가 지표: scenario_type/risk_level/requires_multi_request/time_sensitivity 슬라이스

| model | status | parse_success_rate | answer_non_empty_rate | citation_match_rate | avg_latency_sec | p95_latency_sec |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| aihub-openchat-local | interrupted | 0.242 | 0.242 | 1.0 | 133.7669 | 173.109 |

## 슬라이스 요약

### aihub-openchat-local
- scenario_type
  - road_safety: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - noise: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - flood: runs=3, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - welfare: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - multi_request: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - waste: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - sinkhole: runs=1, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - school_zone: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - accessibility: runs=2, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - winter_road: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - construction_dust: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - public_transport: runs=2, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - fire_hazard: runs=5, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - water_quality: runs=0, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - administrative_delay: runs=1, parse=0.0, answer=0.0, citation=0.0, latency=0.0
- risk_level
  - high: runs=9, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - medium: runs=2, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - low: runs=3, parse=0.0, answer=0.0, citation=0.0, latency=0.0
- requires_multi_request
  - false: runs=5, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - true: runs=9, parse=0.0, answer=0.0, citation=0.0, latency=0.0
- time_sensitivity
  - high: runs=10, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - medium: runs=2, parse=0.0, answer=0.0, citation=0.0, latency=0.0
  - low: runs=2, parse=0.0, answer=0.0, citation=0.0, latency=0.0

