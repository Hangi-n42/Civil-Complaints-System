# Week 3 전달 인덱스

기준일: 2026-03-26  
범위: index-search E2E + LLM 핵심 5종 벤치마크

## 1) 새로 추가된 Week3 태스크

- LLM 핵심 5종(기존 AIHub 1 + 후보 4) 동일조건 벤치마크 수행
- 후보 1을 `skt/A.X-4.0-Light`로 교체 반영
- 기존 AIHub 모델 + 후보 4종의 답변 품질/지연시간/파싱 안정성 비교
- 모델별 결과를 JSON/Markdown 리포트로 산출
- 케이스 15건으로 확대하여 시나리오 슬라이스 분석 추가

## 1.1) Week3 모델 테스트 역할 분담

- BE1: 기존 AIHub baseline 모델 테스트
- BE2: 후보 1(`skt/A.X-4.0-Light`) 테스트
- BE3: 후보 2/3/4(`exaone3.5:7.8b-instruct`, `gemma3:12b`, `phi4-mini:3.8b-instruct`) 테스트
- FE: 결과 시각화 포맷 협업

## 2) 벤치마크 산출물 경로

- 프로토콜 문서: `docs/40_delivery/week3/model_benchmark_protocol.md`
- 케이스 확장 규칙: `docs/40_delivery/week3/benchmark_case_expansion_rules.md`
- 벤치마크 설정: `configs/week3_model_benchmark.yaml`
- 500건 확장 세트: `docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json`
- 확장 생성 스크립트: `scripts/generate_week3_benchmark_cases_500.py`
- 실행 스크립트: `scripts/run_week3_model_benchmark.py`
- 결과 JSON: `logs/evaluation/week3/model_benchmark_report.json`
- 결과 요약: `logs/evaluation/week3/model_benchmark_summary.md`

## 3) 실행 방법

```bash
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json

# 500건 확장 세트 생성
python scripts/generate_week3_benchmark_cases_500.py \
  --input docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
  --output docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json \
  --target 500 \
  --seed 42

# 500건 벤치마크 실행
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/week3_model_benchmark_cases_500.json
```

## 4) 운영 메모

- `configs/week3_model_benchmark.yaml`의 `aihub_baseline.model_name`은 실제 운영 중인 AIHub 모델 태그로 교체 필요
- `candidate_ax4_light`는 Hugging Face 태그(`skt/A.X-4.0-Light`)와 로컬 서빙 태그를 환경에 맞게 매핑 필요
- Ollama에 설치되지 않은 모델은 자동으로 `not_installed`로 표시하고 측정을 건너뜀
