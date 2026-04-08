# Week4 Baseline Evaluation Set Quality Report

- 대상: `docs/40_delivery/week3/model_test_assets/evaluation_set.json`
- 검증일: 2026-04-08
- 담당: BE1
- 산출 이슈: #133

## 1) Summary

- 총 건수: 500 (PASS)
- case_id 중복 그룹: 0 (PASS)
- query 중복 그룹: 90 (WARN)
- context 개수: min=2, max=2, avg=2.0 (PASS)
- 파일 해시(SHA256): `6b629cf6081eeb05de057aecd8f3c55a7c294d6538816fde819b01ba173bdfcb`

## 2) Distribution Check

### scenario_type

- accessibility: 33
- administrative_delay: 33
- construction_dust: 33
- fire_hazard: 33
- flood: 34
- multi_request: 34
- noise: 34
- public_transport: 33
- road_safety: 34
- school_zone: 33
- sinkhole: 33
- waste: 33
- water_quality: 33
- welfare: 34
- winter_road: 33

판정: 편차 1 이내로 균형 유지 (PASS)

### risk_level

- high: 200
- medium: 200
- low: 100

판정: low 비중이 낮아 strict balanced 기준에서는 비균형 (WARN)

### time_sensitivity

- high: 213
- medium: 142
- low: 145

판정: 운영 가능한 수준 (INFO)

### requires_multi_request

- true: 200
- false: 300

판정: 단일/복합 모두 포함 (PASS)

## 3) Quality Notes

- query 중복 90그룹은 템플릿 기반 생성셋 특성으로 확인됨.
- 이 데이터셋은 benchmark query/context 중심이며, `region/category/created_at`는 레코드 필드로 직접 포함하지 않음.
- Week4 공통 계약의 metadata 정합성 점검은 별도 점검표(#134)와 함께 운영해야 함.

## 4) Decision

- 결론: `CONDITIONAL PASS`
- 조건:
  1. freeze 버전은 `week4-baseline-freeze-1`로 고정
  2. metadata 품질 점검표(#134) 결과와 함께 Gate A 입력 사용 판정
  3. 평가셋 변경 시 hash 재생성 및 재승인 필수

## 5) Repro Command

```powershell
$path = "docs/40_delivery/week3/model_test_assets/evaluation_set.json"
$data = Get-Content $path -Raw | ConvertFrom-Json
(Get-FileHash -Path $path -Algorithm SHA256).Hash
$data.Count
```
