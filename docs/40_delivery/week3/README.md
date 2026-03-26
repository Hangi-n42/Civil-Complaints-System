# Week 3 전달 인덱스

기준일: 2026-03-27  
범위: index-search E2E + LLM 핵심 5종 벤치마크  
상태: 🚀 계획 수립 완료, 구현 시작 단계

## 📌 Week 3 미션

### 핵심 목표
1. **인덱싱/검색 E2E 완성**: 500+ 케이스 임베딩 후 시맨틱 검색 가능
2. **메타필터 안정화**: 지역/카테고리/기간 필터 동작
3. **LLM 벤치마크**: 5종 모델 QA 생성 성능 비교 (500건 평가셋)
4. **성능 기준선 확보**: Recall@5, latency 등 측정 완료

### 팀 역할 분담
| 담당 | 주요 작업 | 산출물 |
|-----|---------|--------|
| **FE** | 검색 UI 연결, 벤치마크 대시보드 | `ui/pages/2_Search_and_QA.py`, `logs/evaluation/week3/model_benchmark_report_final.json` 시각화 |
| **BE1** | 평가셋 500건 준비, baseline 모델 벤치마크 | `docs/40_delivery/week3/model_test_assets/evaluation_set.json`, `logs/evaluation/week3/model_benchmark_*.json` |
| **BE2** | 임베딩/인덱싱/검색 구현, A.X 벤치마크 | `app/retrieval/service.py`, `logs/evaluation/week3/retrieval_metrics.json`, `--model candidate_ax4_light` 결과 |
| **BE3** | API `/index`,`/search` 안정화, 3종 모델 벤치마크 + 통합 리포트 | `app/api/routers/`, `--model candidate_exaone_3_5_7_8b`, `--model candidate_gemma3_12b`, `--model candidate_phi4_mini`, `logs/evaluation/week3/model_benchmark_report_final.json` |

---

## 📂 산출물 경로 (업데이트 2026-03-27)

### 계약/설계 문서
| 항목 | 경로 | 상태 |
|-----|------|------|
| 공통 인터페이스 | `docs/10_contracts/interfaces/week3/week3_common_interface.md` | ✅ 완료 |
| BE1 인터페이스 | `docs/10_contracts/interfaces/week3/week3_be1_interface.md` | ✅ 완료 |
| BE2 인터페이스 | `docs/10_contracts/interfaces/week3/week3_be2_interface.md` | ✅ 완료 |
| BE3 인터페이스 | `docs/10_contracts/interfaces/week3/week3_be3_interface.md` | ✅ 완료 |
| FE 인터페이스 | `docs/10_contracts/interfaces/week3/week3_fe_interface.md` | ✅ 완료 |
| 검색 전략 | `docs/20_domains/retrieval/retrieval_strategy.md` | ✅ 완료 |
| 인덱싱 계획 | `docs/20_domains/retrieval/indexing_plan.md` | ✅ 완료 |

### 기존 벤치마크 산출물
| 항목 | 경로 | 용도 |
|-----|------|------|
| 프로토콜 | `docs/40_delivery/week3/model_benchmark_protocol.md` | 벤치마크 실행 규격 |
| 확장 규칙 | `docs/40_delivery/week3/benchmark_case_expansion_rules.md` | 평가셋 생성 규칙 |
| 설정 파일 | `configs/week3_model_benchmark.yaml` | Ollama 환경 설정 |
| 실행 스크립트 | `scripts/run_week3_model_benchmark.py` | 모델 테스트 실행 |

### 예상 산출물 (Week 3 구현 중)
| 항목 | 경로 | 기준 |
|-----|------|------|
| 평가셋 (500건) | `docs/40_delivery/week3/model_test_assets/evaluation_set.json` | ⏳ 우선순위 |
| 인덱싱 리포트 | `logs/evaluation/week3/indexing_report.json` | 500건 100% 인덱싱 |
| 검색 성능 | `logs/evaluation/week3/retrieval_metrics.json` | Recall@5 ≥ 75% |
| 모델 리포트 | `logs/evaluation/week3/model_benchmark_*.json` | 5개 모델 |
| 통합 리포트 | `logs/evaluation/week3/model_benchmark_report_final.json` | 비교 + 권장사항 |

## 🔧 실행 방법 (Week 3 업데이트)

### 1단계: 환경 설정
```bash
# BGE-m3 임베딩 모델 다운로드
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

# Ollama 모델 설치
ollama pull aihub-local-baseline  # 기존 AIHub 모델 태그(week3_model_benchmark.yaml)
ollama pull exaone3.5:7.8b-instruct
ollama pull gemma3:12b
ollama pull phi4-mini:3.8b-instruct
```

### 2단계: 평가셋 준비
```bash
# 500건 평가셋 생성
python scripts/generate_week3_benchmark_cases_500.py \
  --input data/samples/initial_sample_20.json \
  --output docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --target 500 \
  --seed 42
```

### 3단계: 인덱싱
```bash
# 500건 임베딩 + ChromaDB 인덱싱
python -m app.api.main index \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json
```

### 4단계: 모델 벤치마크 (병렬 실행 권장)
```bash
# BE1: AIHub baseline
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model aihub_baseline

# BE2: A.X 후보
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_ax4_light

# BE3: exaone3.5, gemma3, phi4-mini
python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_exaone_3_5_7_8b

python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_gemma3_12b

python scripts/run_week3_model_benchmark.py \
  --config configs/week3_model_benchmark.yaml \
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
  --model candidate_phi4_mini
```

### 5단계: 리포트 생성
```bash
python scripts/generate_week3_benchmark_report.py \
  --results logs/evaluation/week3/ \
  --output logs/evaluation/week3/model_benchmark_report_final.json
```

---

## ✅ Week 3 완료 기준 (M2 Gate A)

| 항목 | 완료 조건 | 상태 |
|-----|---------|------|
| 인덱싱 E2E | 500건 100% ChromaDB 인덱싱 | ⏳ 진행중 |
| 기본 검색 | Top-K 자유문 검색 동작 | ⏳ 진행중 |
| 메타필터 | 지역/카테고리/기간 필터 2종 이상 안정 | ⏳ 진행중 |
| 성능 측정 | Recall@5, latency 기초값 산출 | ⏳ 진행중 |
| 모델 벤치마크 | 5종 모델 평가 완료 | ⏳ 우선순위 |
| 검색 성능 리포트 | 지표 및 분석 완료 | ⏳ 진행중 |
| 모델 비교 리포트 | 1차본 산출 | ⏳ 진행중 |

---

## 📝 Week 3 주간 마일스톤

### 1주차 (2026-03-27 ~ 04-02)
- 평가셋 500건 생성
- 임베딩 모델 다운로드 및 테스트
- 500건 인덱싱 완료
- 기본 검색 functionality 구현

### 2주차 (2026-04-03 ~ 04-09)
- 메타필터 안정성 테스트
- 5종 모델 벤치마크 병렬 실행
- 성능 지표 수집 및 정리
- 1차 리포트 생성 및 검토

---

## 🚨 Week 3 리스크 및 대응

| 리스크 | 징후 | 대응 |
|-------|-----|------|
| OOM | 임베딩 시 메모리 error | 배치 크기 50→25로 축소 |
| 모델 미설치 | `ollama list`에 없음 | 자동으로 `not_installed` 표시 |
| 검색 성능 저조 | Recall@5 < 60% | 임베딩 모델 재선정 또는 청킹 전략 변경 |
| API 타임아웃 | 검색 >2초 | 쿼리 간단히 하거나 top_k 축소 |

---

## 📞 Week 3 체크포인트

### 매주 월요일
- 목표 확인, 진행률 체크
- 블로커 식별 및 해결안 논의

### 매주 수요일
- 중간 점검: 검색/인덱싱 E2E 상태
- 모델 벤치마크 진행률

### 매주 금요일
- 주간 산출물 리뷰
- 다음 주 계획 확정

---

## 👥 담당자 및 협업

| 역할 | 담당자 | 주요 연락처 |
|-----|--------|---------|
| **BE1** (데이터/평가) | 현기 | 평가셋 생성(`evaluation_set.json`), `aihub_baseline` 실행 |
| **BE2** (검색/인덱싱) | 민건 | 인덱싱/검색 + `candidate_ax4_light` 실행 |
| **BE3** (API/LLM) | 현석 | `/index`,`/search` API + `candidate_exaone_3_5_7_8b`/`candidate_gemma3_12b`/`candidate_phi4_mini` 실행 |
| **FE** (UI) | 도훈 | 검색 UI + `model_benchmark_report_final.json` 대시보드 반영 |

---

**마지막 업데이트**: 2026-03-27 15:00 (KST)  
**다음 갱신**: 주간 체크포인트 후 (금요일)
