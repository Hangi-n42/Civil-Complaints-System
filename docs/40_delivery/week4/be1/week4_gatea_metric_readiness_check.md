# Week4 Gate A Metric Readiness Check (BE1)

- 기준: Recall@5, 4요소 F1, citation 정합성, latency
- 산출 이슈: #134
- 체크 시각: 2026-04-08T14:25:00+09:00

## 1) Execution Prerequisite Check

| 항목 | 경로 | 상태 |
| --- | --- | --- |
| 평가셋 | `docs/40_delivery/week3/model_test_assets/evaluation_set.json` | READY |
| freeze manifest(Week4) | `docs/40_delivery/week4/be1/week4_evaluation_set_freeze_manifest.json` | READY |
| 구조화 평가 스크립트 | `scripts/evaluate_structuring.py` | READY |
| 검색 평가 스크립트 | `scripts/evaluate_retrieval.py` | READY |
| QA 평가 스크립트 | `scripts/evaluate_qa.py` | READY |
| 모델 벤치마크 스크립트 | `scripts/run_week3_model_benchmark.py` | READY |
| BE1 baseline 실행 리포트 | `logs/evaluation/week3/be1_baseline/model_benchmark_report.json` | READY |

## 2) Current Blocking Factors

- `aihub_baseline` 모델 실행 상태: `not_installed`
- 기존 baseline 리포트 결과: `results_count = 0`
- 영향: Gate A 4개 지표를 "확정 수치"로 산출할 수 없음

## 3) Readiness Decision

- 판정: `PARTIAL_READY`
- 의미:
  - 실행 파이프라인/입력/스크립트는 준비됨
  - 모델 환경 미충족으로 최종 수치 산출은 보류

## 4) Release Conditions

1. Ollama에 `aihub_baseline` 설치/기동
2. 동일 조건으로 benchmark 재실행
3. GateAReport 형식으로 4개 지표 기록

## 5) Evidence

- `logs/evaluation/week3/be1_baseline/model_benchmark_report.json`
- `logs/evaluation/week4/be1/week4_gatea_metric_readiness.json`
- `logs/evaluation/week4/be1/week4_metadata_quality_snapshot.json`
