# Week3 LLM 모델 벤치마크 프로토콜

작성일: 2026-03-26  
목적: 동일 조건에서 핵심 모델 5종을 비교해 Week4 단일 RAG baseline 모델을 선정한다.

## 1) 후보 모델 (AIHub 기존 모델 + 후보 4종)

- 기존 모델: AIHub 기반 현재 운영 모델 (프로젝트 기본값)
- 후보 1: skt/A.X-4.0-Light
- 후보 2: exaone3.5:7.8b-instruct
- 후보 3: gemma3:12b (최신 오픈소스 후보)
- 후보 4: phi4-mini:3.8b-instruct

선정 이유 요약:
- 한국어 처리 성능
- JSON 출력 안정성
- 온디바이스 추론 속도 및 메모리 효율
- 커뮤니티/실무 사용성

## 2) 동일 조건 정의 (고정)

- 호출 엔진: Ollama `/api/generate`
- 프롬프트 템플릿: scripts/run_week3_model_benchmark.py 내 고정 템플릿
- 입력 케이스: docs/40_delivery/week3/model_test_assets/evaluation_set.json (500건, 모든 모델 동일)
- 파라미터: temperature=0.2, num_ctx=2048, num_predict=256, timeout=90초
- 반복 횟수: 케이스당 1회 (필요 시 3회로 상향)

### 2.1 500건 확장 세트 생성 규칙

- 규칙 문서: docs/40_delivery/week3/benchmark_case_expansion_rules.md
- 생성 스크립트: scripts/generate_week3_benchmark_cases_500.py
- 생성 명령:

```bash
python scripts/generate_week3_benchmark_cases_500.py \
  --input data/samples/initial_sample_20.json \
  --output docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --target 500 \
  --seed 42
```

## 3) 측정 지표

- parse_success_rate: JSON 파싱 성공 비율
- answer_non_empty_rate: answer 비어있지 않은 비율
- citation_match_rate: citation chunk_id가 입력 context와 일치하는 비율
- avg_latency_sec: 평균 응답 시간
- p95_latency_sec: 95퍼센타일 응답 시간
- scenario slice metrics: scenario_type/risk_level/requires_multi_request/time_sensitivity 별 지표

## 4) 합격 기준 (Week3 1차)

- parse_success_rate >= 0.9
- citation_match_rate >= 0.8
- avg_latency_sec <= 12
- high risk 슬라이스에서 citation_match_rate >= 0.8
- multi_request=true 슬라이스에서 answer_non_empty_rate >= 0.9

## 5) 실행 커맨드

```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json
```

모델 지정 실행 예시 (설정 파일 id 기준):

```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model aihub_baseline

python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_exaone_3_5_7_8b
```

## 6) 역할 분담 (4인 팀)

- BE1 책임: 기존 AIHub baseline 모델 측정, 케이스 품질 점검, 결과 해석 기준 정리
- BE2 책임: 후보 1(`skt/A.X-4.0-Light`) 측정 및 결과 리포트
- BE3 책임: 후보 2/3/4(`exaone3.5:7.8b-instruct`, `gemma3:12b`, `phi4-mini:3.8b-instruct`) 측정 및 통합 리포트
- FE 협업: 결과 대시보드 반영 포맷 정의

### 6.1 실행 오너십 매트릭스

| 구분 | 담당 | 모델 |
| --- | --- | --- |
| Baseline | BE1 | `aihub_baseline` (`aihub-local-baseline`) |
| Candidate-1 | BE2 | `candidate_ax4_light` (`skt/A.X-4.0-Light`) |
| Candidate-2 | BE3 | `candidate_exaone_3_5_7_8b` (`exaone3.5:7.8b-instruct`) |
| Candidate-3 | BE3 | `candidate_gemma3_12b` (`gemma3:12b`) |
| Candidate-4 | BE3 | `candidate_phi4_mini` (`phi4-mini:3.8b-instruct`) |

## 7) 리스크 관리

- 징후: 특정 모델에서 timeout 급증
  - 원인: 모델 크기 대비 로컬 자원 부족
  - 예방책: num_ctx, num_predict 상한 고정
  - 대응책: 해당 모델을 `low-resource fallback` 트랙으로 이동
  - 폴백안: phi4-mini 우선 채택 (Qwen은 벤치마크 후 별도 선정)

- 징후: JSON 파싱 실패 증가
  - 원인: 모델의 출력 형식 불안정
  - 예방책: 고정 JSON 템플릿과 낮은 temperature 유지
  - 대응책: 실패 케이스 재실행 + compact prompt 버전 비교
  - 폴백안: 파싱 안정성이 높은 모델로 baseline 고정

- 징후: `skt/A.X-4.0-Light` 로컬 실행 불가(미설치/라이선스 미확정)
  - 원인: 오픈 가중치 또는 로컬 추론 경로 미확보
  - 예방책: 사전 체크리스트(가중치 공개 여부, 상업/연구 라이선스, 로컬 런타임 호환성) 운영
  - 대응책: Hugging Face 원본 태그와 로컬 서빙 태그를 매핑해 재시도
  - 폴백안: 후보 1만 임시 제외하고 나머지 4모델 비교를 먼저 완료
