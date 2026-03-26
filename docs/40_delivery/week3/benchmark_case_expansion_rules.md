# Week3 500건 확장 세트 생성 규칙

작성일: 2026-03-26  
목표: 15건 seed 케이스를 기반으로 동일 스키마를 유지한 500건 확장 벤치마크 세트를 재현 가능하게 생성한다.

## 1) 생성 원칙

- 스키마 유지: 기존 키 구조(case_id, scenario_type, risk_level, requires_multi_request, time_sensitivity, query, context) 유지
- 재현성: 동일 seed 사용 시 동일 출력
- 다양성: query 표현, snippet 표현, 점수(score), 시간 민감도/다중요청 분포를 확장
- 안정성: context 구조(최소 2개)와 수치 범위(score 0.5~0.99) 보장

## 2) 변형 규칙

1. query 변형
- 접두 문구, 접미 문구, 추가 제약 문구를 조합
- 일부 케이스는 출력 형식 제약(예: citations 2개 이상, limitations 분리)을 포함

2. context snippet 변형
- 근거 문장 앞뒤에 행정적 표현(prefix/suffix) 삽입
- 원문 의미를 유지하면서 표현만 변형

3. score 변형
- 기존 score에 작은 jitter(±0.03)를 적용
- 범위를 0.5~0.99로 clipping

4. 시나리오 분포 확장
- scenario_type/risk_level은 seed 분포를 유지
- time_sensitivity, requires_multi_request 일부 샘플에서 변형해 슬라이스 분석 가능한 분포 확보

5. 중복 방지
- scenario/risk/multi/time/query/context-snippet 조합 fingerprint로 중복 제거

## 3) 자동 생성 스크립트

- 스크립트: scripts/generate_week3_benchmark_cases_500.py
- 입력: docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json
- 출력: docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json

실행 예시:

```bash
python scripts/generate_week3_benchmark_cases_500.py \
  --input docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
  --output docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
  --target 500 \
  --seed 42
```

## 4) 품질 체크리스트

- generated count = 500
- JSON 파싱 성공
- scenario_type/risk_level/requires_multi_request/time_sensitivity 키 존재
- context 길이 >= 2
- score 범위 0.5~0.99

## 5) 운영 권장

- Week3 1차: 500건 세트로 모델 5종 비교
- Week4 확정: 상위 2개 모델 대상으로 추가 재실행(동일 seed + seed 변경 1회)
