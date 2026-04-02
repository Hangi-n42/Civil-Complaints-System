# Week3 BE3 작업 수행 가이드

문서 버전: 1.0  
작성일: 2026-03-30  
목적: Issue #93, #105, #106 해결을 위한 벤치마크 실행 절차

---

## 1. 개요

Week3 BE3는 다음을 담당합니다:
- **/index, /search API 안정화** (Week2 상속, 이미 완료)
- **후보 3종 모델 벤치마크** (#105)
  - exaone3.5:7.8b-instruct
  - gemma3:12b
  - phi4-mini:3.8b-instruct
- **통합 벤치마크 리포트** (#106)

---

## 2. 사전 준비

### 2.1 환경 확인

```bash
# 현재 디렉터리 확인
cd d:\동아대\4학년\1학기\실증적AI개발프로젝트Ⅰ(종합설계)\KLLK_VSCODE\AI-Civil-Affairs-Systems

# 필수 파일 확인
- configs/week3_model_benchmark.yaml (존재함)
- docs/40_delivery/week3/model_test_assets/evaluation_set.json (존재함)
- logs/evaluation/week3/ (자동 생성됨)
```

### 2.2 Ollama 모델 설치

```bash
# Ollama 실행 (http://localhost:11434)
ollama serve

# 다른 터미널에서 필수 모델 설치
ollama pull exaone3.5:7.8b-instruct
ollama pull gemma3:12b
ollama pull phi4-mini:3.8b-instruct

# 설치 확인
ollama list
```

---

## 3. 벤치마크 실행 절차

### 3.1 단계별 모델 벤치마크

각 모델을 순차 실행합니다. 각 모델당 약 10~30분 소요됩니다.

#### 모델 2: EXAONE 3.5 (7.8B)

```bash
python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_exaone_3_5_7_8b \
  --output-dir logs/evaluation/week3
```

**예상 산출물:**
- `logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json`
- `logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md`

#### 모델 3: Gemma 3 (12B)

```bash
python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_gemma3_12b \
  --output-dir logs/evaluation/week3
```

**예상 산출물:**
- `logs/evaluation/week3/model_benchmark_candidate_candidate_gemma3_12b.json`
- `logs/evaluation/week3/model_benchmark_candidate_candidate_gemma3_12b.md`

#### 모델 4: Phi 4 Mini (3.8B)

```bash
python scripts/Be3_run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_phi4_mini \
  --output-dir logs/evaluation/week3
```

**예상 산출물:**
- `logs/evaluation/week3/model_benchmark_candidate_candidate_phi4_mini.json`
- `logs/evaluation/week3/model_benchmark_candidate_candidate_phi4_mini.md`

### 3.2 결과 파일 확인

실행 후 다음 파일들이 생성되었는지 확인:

```bash
ls -la logs/evaluation/week3/model_benchmark_candidate_*.json
```

예상 결과:
```
model_benchmark_candidate_candidate_exaone_3_5_7_8b.json
model_benchmark_candidate_candidate_gemma3_12b.json
model_benchmark_candidate_candidate_phi4_mini.json
```

---

## 4. 통합 벤치마크 리포트 생성

모든 모델 벤치마크가 완료되면, 통합 리포트를 생성합니다.

```bash
python scripts/generate_week3_unified_benchmark_report.py \
  --input-dir logs/evaluation/week3 \
  --output logs/evaluation/week3/model_benchmark_report_final.json
```

**예상 산출물:**
- `logs/evaluation/week3/model_benchmark_report_final.json`

**리포트 구조:**
```json
{
  "report_name": "Week3 Unified Model Benchmark Report",
  "generated_at": "ISO-8601 타임스탐프",
  "measured_models_count": 3,
  "summary_table": [
    {
      "rank": 1,
      "model_id": "...",
      "model_name": "...",
      "composite_score": 0.85,
      "parse_success_rate": 0.95,
      "answer_non_empty_rate": 0.90,
      "citation_match_rate": 0.85,
      "avg_latency_sec": 8.5
    },
    ...
  ],
  "baseline_recommendation": {
    "status": "found|conditional|error",
    "baseline_model_id": "...",
    "baseline_model_name": "...",
    "reason": "..."
  }
}
```

---

## 5. 합격 기준

Week3 모델 벤치마크 합격 기준 (Week3 1차):

| 지표 | 기준 |
|-----|------|
| parse_success_rate | >= 0.9 (90%) |
| citation_match_rate | >= 0.8 (80%) |
| avg_latency_sec | <= 12 |

**통합 점수 계산:**
- parse_success_rate: 30%
- answer_non_empty_rate: 20%
- citation_match_rate: 30%
- latency_score (정규화): 20%

---

## 6. 트러블슈팅

### 모델 설치 안 됨
```bash
# Ollama 확인
curl http://localhost:11434/api/tags

# 모델 재설치
ollama pull exaone3.5:7.8b-instruct
```

### 타임아웃 (90초 초과)
```yaml
# configs/week3_model_benchmark.yaml 수정
timeout_sec: 120  # 90 → 120으로 증가
num_predict: 256  # 또는 더 짧게 조정 (e.g., 128)
```

### 메모리 부족
```bash
# 컨텍스트 크기 축소
num_ctx: 1024  # 2048 → 1024
```

---

## 7. 산출물 확인 체크리스트

### #105 완료 조건 (후보 3종 벤치마크)

- [ ] `logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json` 생성됨
- [ ] `logs/evaluation/week3/model_benchmark_candidate_candidate_gemma3_12b.json` 생성됨
- [ ] `logs/evaluation/week3/model_benchmark_candidate_candidate_phi4_mini.json` 생성됨
- [ ] 각 파일에 `summary.parse_success_rate` 등 필수 지표 포함
- [ ] 각 파일에 `results[]` 배열 포함 (case별 결과)

### #106 완료 조건 (통합 벤치마크 리포트)

- [ ] `logs/evaluation/week3/model_benchmark_report_final.json` 생성됨
- [ ] `summary_table[]` 3개 모델 모두 포함
- [ ] `baseline_recommendation.status` = "found" 또는 "conditional"
- [ ] `baseline_recommendation.baseline_model_name` 명시됨
- [ ] `ranked` 배열이 composite_score 순으로 정렬됨

---

## 8. 산출물 위치 정리

| 파일 | 경로 |
|-----|-----|
| 설정 | `configs/week3_model_benchmark.yaml` |
| 입력 | `docs/40_delivery/week3/model_test_assets/evaluation_set.json` |
| EXAONE 결과 | `logs/evaluation/week3/model_benchmark_candidate_candidate_exaone_3_5_7_8b.json` |
| Gemma 결과 | `logs/evaluation/week3/model_benchmark_candidate_candidate_gemma3_12b.json` |
| Phi4 결과 | `logs/evaluation/week3/model_benchmark_candidate_candidate_phi4_mini.json` |
| 통합 리포트 | `logs/evaluation/week3/model_benchmark_report_final.json` |

---

## 9. 다음 단계 (Week 4)

- 선정된 baseline 모델로 단일 RAG 구축
- citation 정합성 검증
- latency 최적화
- 성능 지표 확정


