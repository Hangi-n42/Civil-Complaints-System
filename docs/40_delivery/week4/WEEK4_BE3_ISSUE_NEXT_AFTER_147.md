부모 이슈: #129  
선행 이슈: #147

Week 4 BE3에서 새로 수행한 전체 벤치마크(exaone, ax4, gemma3, gemma4:26b, gemma4:e4b) 결과를 기반으로, 운영 기본 모델과 저지연 대안, 그리고 모델군별 후속 개선 방향을 확정한다.

## 목적
- 벤치마크 기반으로 Week4 운영 기본 모델을 확정한다.
- exaone/ax4/gemma 계열의 품질-지연 트레이드오프를 함께 비교한다.
- 지연 우선 시나리오용 대체 모델 기준을 명확히 한다.
- strict 품질 취약 모델에 대한 보완 실험 항목을 정의한다.
- Week4 시연/평가에서 모델 선택 근거를 문서화한다.

## 배경 (신규 벤치마크 핵심)
- 공통 조건: temp=0.2, num_ctx=1024, num_predict=128, timeout=90s, 100 cases
- parse_success_rate: 5모델 모두 1.0
- answer_non_empty_rate_strict:
  - exaone3.5:7.8b-instruct = 0.87
  - gemma3:12b = 0.82
  - gemma4:e4b = 0.55
  - gemma4:26b = 0.15
  - ax4-light-local:latest = 0.0
- answer_non_empty_rate_repaired: 5모델 모두 1.0
- avg_latency_sec:
  - ax4-light-local:latest = 13.0711
  - exaone3.5:7.8b-instruct = 17.1425
  - gemma4:26b = 18.9228
  - gemma3:12b = 19.6311
  - gemma4:e4b = 21.4271
- p95_latency_sec:
  - ax4-light-local:latest = 14.5985
  - exaone3.5:7.8b-instruct = 18.8699
  - gemma4:26b = 20.3807
  - gemma3:12b = 20.7955
  - gemma4:e4b = 25.0768

해석 요약:
- strict 품질은 exaone3.5:7.8b-instruct가 가장 우수
- 지연은 ax4-light-local:latest가 가장 우수
- gemma3:12b는 품질과 지연의 균형이 가장 안정적이다
- gemma4:e4b는 gemma4:26b보다 strict 품질은 높지만 지연 손해가 있다

## 범위

### 1) 운영 모델 정책 확정
- 기본 운영 모델: gemma3:12b 또는 exaone3.5:7.8b-instruct 중 최종 선택
- 지연 민감 시나리오 대안: ax4-light-local:latest 또는 gemma4:26b
- 라우팅 기준 초안 정의:
  - 일반/품질 우선 요청 -> gemma3:12b 또는 exaone3.5:7.8b-instruct
  - 응답속도 우선 요청 -> ax4-light-local:latest

### 2) strict 품질 보완 실험
- 대상: gemma4:26b, gemma4:e4b
- 실험 항목:
  - prompt 압축/지시문 강화 버전 비교
  - answer 최소 품질 가드 강화
  - citation 생성 안정화 규칙 점검
- 목표:
  - strict answer_non_empty_rate 개선
  - 지연 증가 최소화

### 3) 운영 문서/리포트 정리
- 5모델 비교 리포트 기준으로 Week4 모델 선택 근거 문서화
- 발표/시연용 1페이지 요약본 생성

## 완료 기준
- Week4 BE3 운영 기본 모델/대안 모델이 명시된다.
- 모델 라우팅 기준(품질 우선 vs 지연 우선)이 문서화된다.
- gemma4 계열 strict 품질 개선 실험 계획(변수/측정지표/목표치)이 정리된다.
- 비교 리포트와 이슈의 수치/결론이 일치한다.

## 산출물
- Week4 전체 벤치마크 비교 리포트 최신본
- 모델 선택 정책 문서(운영 기준)
- strict 품질 개선 실험 계획서
- 후속 벤치마크 결과(필요 시)

## 참고 문서
- Week4 GEMMA 3모델 비교 리포트
  - docs/40_delivery/week4/WEEK4_BE3_GEMMA3_VS_GEMMA4_COMPARISON_REPORT.md
- Week4 EXAONE 비교 리포트
  - docs/40_delivery/week4/WEEK4_BE3_EXAONE_W3_VS_W4_COMPARISON_REPORT.md
- Week4 AX4 비교 리포트
  - docs/40_delivery/week4/WEEK4_BE3_AX4_W3_VS_W4_COMPARISON_REPORT.md
- GEMMA3 결과
  - logs/evaluation/week4/gemma_ctx1024/model_benchmark_candidate_candidate_gemma3_12b.md
- GEMMA4:26b 결과
  - logs/evaluation/week4/gemma4_ctx1024/model_benchmark_candidate_candidate_gemma4_26b.md
- GEMMA4:e4b 결과
  - logs/evaluation/week4/gemma4_e4b_ctx1024/model_benchmark_candidate_candidate_gemma4_e4b.md
- EXAONE 결과
  - logs/evaluation/week4/exaone_ctx1024/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md
- AX4 결과
  - logs/evaluation/week4/ax4_ctx1024/model_benchmark_candidate_candidate_ax4_light.md
