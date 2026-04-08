# Week4 BE1 Issue Completion Comment Templates

아래 템플릿은 이슈 완료 시 코멘트에 그대로 붙여넣어 사용할 수 있다.
완료 규칙에 맞춰 `산출물 경로`, `실행/검증 절차`, `결과 요약` 3가지를 포함한다.

## Template for #133

```md
[#133 완료 코멘트]

완료 처리합니다. Week4 baseline 평가셋 freeze 및 품질 점검 산출물을 아래와 같이 남깁니다.

1) 산출물 파일 경로
- docs/40_delivery/week4/be1/week4_evaluation_set_freeze_manifest.json
- docs/40_delivery/week4/be1/week4_evaluation_set_quality_report.md
- docs/40_delivery/week4/be1/week4_gatea_input_readiness.md

2) 실행 커맨드 / 검증 절차
- 평가셋 해시/건수 확인
  - powershell
    - $path = "docs/40_delivery/week3/model_test_assets/evaluation_set.json"
    - (Get-FileHash -Path $path -Algorithm SHA256).Hash
    - (Get-Content $path -Raw | ConvertFrom-Json).Count
- 분포/중복/context 개수 점검
  - case_id 중복 그룹 0
  - scenario_type 분포 33~34 균형
  - context 개수 min=max=2

3) 결과 요약
- 결론: CONDITIONAL PASS
- 근거: 건수/해시/기본 품질 기준은 통과, metadata 직접 필드 부재로 Gate A 입력 판정은 조건부 사용 가능
- 후속 필요사항: request_id trace와 metadata 연계 로그를 Gate A 실행 산출물에 포함
```

## Template for #134

```md
[#134 완료 코멘트]

완료 처리합니다. 구조화/메타데이터 품질 점검표 및 Gate A 산출 가능 체크 결과를 아래와 같이 남깁니다.

1) 산출물 파일 경로
- docs/40_delivery/week4/be1/week4_structured_metadata_quality_checklist.md
- docs/40_delivery/week4/be1/week4_gatea_metric_readiness_check.md
- logs/evaluation/week4/be1/week4_metadata_quality_snapshot.json
- logs/evaluation/week4/be1/week4_gatea_metric_readiness.json

2) 실행 커맨드 / 검증 절차
- 구조화 샘플 점검 데이터
  - reports/week2_entity_audit/week2_structured_sample_10.json
- 점검 항목
  - region/category/created_at 결측 여부
  - created_at/structured_at KST(+09:00) 형식 여부
  - Gate A 4개 지표 산출 파이프라인 준비 여부(스크립트/입력/기존 실행 흔적)

3) 결과 요약
- 메타데이터 점검표: FAIL_REMEDIATION_REQUIRED
  - region/category 결측성 값(`unknown`, `-`) 존재
  - KST(+09:00) suffix 미준수
- Gate A readiness: PARTIAL_READY
  - 입력/스크립트 준비 완료
  - aihub_baseline 미설치로 최종 수치 확정은 보류
- 제외 사항: KPI 초안 문서 작성/배포는 정책에 따라 미수행
```
