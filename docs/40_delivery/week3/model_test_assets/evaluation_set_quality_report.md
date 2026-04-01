# Evaluation Set 500 Quality Validation (Week3)

- 기준 데이터: docs/40_delivery/week3/model_test_assets/evaluation_set.json
- 검증 일자: 2026-03-31
- 담당: BE1

## 1) 검증 결과 요약

- 총 건수: 500 (PASS)
- case_id 중복: 0 (PASS)
- query 공백/누락: 0 (PASS)
- 컨텍스트 개수: min=2, max=2, avg=2.0 (PASS)
- 입력셋 해시(SHA256): 6b629cf6081eeb05de057aecd8f3c55a7c294d6538816fde819b01ba173bdfcb

## 2) 분포 점검

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

### risk_level

- high: 200
- medium: 200
- low: 100

### time_sensitivity

- high: 213
- medium: 142
- low: 145

### requires_multi_request

- true: 200
- false: 300

## 3) 품질 이슈 및 해석

- 관측: context chunk_id 중복 그룹 30개 존재
- 해석: 본 데이터셋은 동일 민원 사례를 다양한 질의 템플릿으로 재질문하는 synthetic benchmark 특성이 있어, context 재사용이 일부 발생함
- 판정: 중복 case_id가 아니고 query 중복도 0이므로 freeze 차단 조건에는 해당하지 않음

## 4) Freeze 판정

- 판정: APPROVED (week3-freeze-v1)
- 근거: 건수/중복/필수 필드/분포 점검 통과
- freeze 메타: docs/40_delivery/week3/model_test_assets/evaluation_set_freeze_manifest.json

## 5) 재현 명령

```powershell
$path = "docs/40_delivery/week3/model_test_assets/evaluation_set.json"
$data = Get-Content $path -Raw | ConvertFrom-Json
(Get-FileHash -Path $path -Algorithm SHA256).Hash
$data.Count
```
