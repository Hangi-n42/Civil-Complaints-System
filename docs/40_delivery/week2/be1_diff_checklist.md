# Week2 BE1 이슈 체크리스트 Diff 점검

기준 이슈:
- #13 [Week 2][BE1][현기] 정제·PII·구조화 후처리 고도화 및 평가 파이프라인 재정렬
- #20 [Week 2][BE1][Sub] 정제/PII 규칙 고도화 및 노이즈 패턴 보강
- #21 [Week 2][BE1][Sub] 4요소 후처리 규칙 개선 및 실패 케이스 정리
- #22 [Week 2][BE1][Sub] 구조화 평가 파이프라인 재실행 및 리포트 업데이트

작성일: 2026-03-20

## 1) Parent #13 체크리스트 매핑

- [x] #20 대응 완료
  - 구현: app/ingestion/service.py
  - 반영: CSV/JSON 로더, 정제, PII 마스킹, 해시+유사도 중복 제거
- [x] #21 대응 완료
  - 구현: app/structuring/service.py
  - 반영: 4요소 후처리 규칙 강화, created_at 정규화, validation warnings
- [x] #22 대응 완료
  - 구현: scripts/evaluate_structuring.py
  - 반영: 필드별 Precision/Recall/F1, macro F1, schema pass rate, empty field rate 리포트

## 2) Parent #13 수용기준 Diff

수용기준 A: 샘플 50건+ 기준 구조화 처리/검증 재실행 가능
- 기존 상태: 부분 충족(평가 스크립트는 있으나 50건+ E2E 엔트리 부재)
- 보강 조치: scripts/run_week2_be1_e2e.py 추가
- 현재 상태: 충족

수용기준 B: 정제/후처리 규칙과 평가 결과가 문서+스크립트로 재현 가능
- 기존 상태: 일부 충족
- 보강 조치:
  - 스크립트 고도화: scripts/evaluate_structuring.py
  - 근거 문서: 본 문서 + docs/40_delivery/week2/README.md 링크 갱신
- 현재 상태: 충족

## 3) 재실행 절차 (BE1)

1. 샘플 50건 생성(없을 때)
- python scripts/generate_week2_delivery_samples.py --count 50 --output data/samples/week2_delivery_sample_50.json

2. E2E 실행
- python scripts/run_week2_be1_e2e.py --input data/samples/week2_delivery_sample_50.json --limit 50

3. (선택) Gold 기반 평가
- python scripts/run_week2_be1_e2e.py --input data/samples/week2_delivery_sample_50.json --limit 50 --gold data/annotations/gold.json

## 4) 산출 경로

- 구조화 예측: docs/40_delivery/week2/artifacts/be1_structured_pred_50.json
- 요약 리포트: docs/40_delivery/week2/artifacts/be1_structured_summary_50.json
- 평가 리포트(선택): data/annotations/week2_structuring_eval_result.json
