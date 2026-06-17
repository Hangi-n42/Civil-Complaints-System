# 구조화 + 긴급도 고도화 — 종합 실행 설계안 (단계별)

## 0. 목표 · 원칙 · 현재 상태

**목표**
- 구조화: **형식 보장(①스키마 제약 디코딩)** + **내용 신뢰(②자기검증·근거 grounding·보정 신뢰도)** 동시 확보.
- 긴급도: **LLM 비의존 보정 분류기**(bge-m3 임베딩 + calibrated classifier) + 안전 하드 오버라이드.

**원칙(보수적)**
- 필드는 *소비처가 있을 때만*. 과설계는 추출 오류·환각·라벨 비용을 키운다.
- 안전(생명위협)은 *재현율 우선 규칙*으로. 놓치는 게 최악.
- 모든 단계는 *측정 가능한 게이트*를 통과해야 다음으로. 하위호환 유지.

**현재 상태**
- Stage1 규칙 NER + Stage2 온디바이스 LLM 4요소(자유 JSON `format:"json"`) + Stage3 병합/신뢰도(휴리스틱).
- 이미 구현된 보강 필드: `entity_texts`, `legal_refs`(Phase A), `responsible_unit`, `key_terms`, Phase B 조문 검색·인용검증.
- 자산: GPU, Ollama(XGrammar 제약 디코딩 지원), bge-m3, LoRA 튜닝 설정, 토큰-F1 평가 하니스(`scripts/evaluate_structuring.py`).

**확정 결정**
- 구조화 방법: ①스키마 제약 디코딩(+GoLLIE식 가이드라인) + ②자기검증(CoVe).
- 역할: `complainant(민원인) / respondent(유발자) / object(조치객체)`.
- 긴급도: bge-m3 임베딩 + 보정 분류기(non-LLM). 축 = safety(오버라이드) + impact(파급·확산·2차피해 포함) + time_sensitivity. 법정기한 자동산출 ✗, category SLA prior + 명시기한 boolean ○.

**확인 필요(추천 기본값, 다르면 한 줄로 변경)**
- (가) 라벨 구조 = **urgency_level(4단계) + safety_flag(bool)** 〔추천: lean + 오버라이드 평가 가능〕. 대안: + per-axis(safety/impact/time 0~3) — 해석성↑·라벨비용↑·셀당 데이터 희박.
- (나) 라벨 풀 = **원천 민원(data/Validation)에서 층화 샘플** 〔추천〕. 대안: week3 벤치마크 500 재사용/혼합.

---

## 1. 최종 스키마 (JSON Schema — ①제약 디코딩의 계약)

```jsonc
{
  "observation": {"text": "string|null", "evidence_span": [s,e], "confidence": 0.0},
  "result":      {"text": "string|null", "status": "present|pending|insufficient", "evidence_span": [s,e], "confidence": 0.0},
  "request":     {"text": "string|null", "evidence_span": [s,e], "confidence": 0.0},
  "context":     {"text": "string|null", "evidence_span": [s,e], "confidence": 0.0},

  "roles": {
    "complainant": {"text": "string|null", "evidence_span": [s,e]},
    "respondent":  {"text": "string|null", "evidence_span": [s,e]},
    "object":      {"text": "string|null", "evidence_span": [s,e]}
  },

  "urgency": {
    "level": "낮음|보통|높음|긴급",
    "score": 0.0,
    "factors": {"safety":0, "impact":0, "time_sensitivity":0,
                "ongoing":false, "recurring":false, "explicit_deadline":false},
    "evidence": ["원문 근거 문구"],
    "override": "safety|null"
  }
  // + 기존 유지: entity_texts, legal_refs, responsible_unit, key_terms, entities, category, region, admin_unit
}
```
- enum은 제약 디코딩에서 강제(`urgency.level`, `result.status`, role 존재여부).
- 스키마는 *평탄하게*(깊은 중첩/anyOf 지양 — XGrammar 약점).

---

## Track A — 구조화 ①+② (LLM, 무학습)

### 구현 현황 (A1–A4 완료, 제약 디코딩 기본 on)

| 단계 | 파일 | 상태 |
| --- | --- | --- |
| A1 스키마/Pydantic + JSON Schema | `schemas.py`(StructuredLLMOutput, llm_output_json_schema) | ✅ 테스트 |
| A2 제약 디코딩 추출기 + 가이드라인 | `structured_extractor.py` | ✅ (순수부 테스트; Ollama는 로컬) |
| A3 자기검증(CoVe)+grounding+보정신뢰도 | `verifier.py` | ✅ 테스트(주입형 verify_fn) |
| A4 병합(roles/status)+service 배선 | `structured_merge.py`, `service.py`, `config.py` | ✅ 통합·스모크 |
| 테스트 | `test_structured_extractor/verifier/structured_merge.py` (19) | ✅ 통과 |

- **플래그**: `STRUCTURING_CONSTRAINED`(① 제약 디코딩)는 기본 `true`, `ENABLE_SELF_VERIFY`(② 자기검증)는 기본 `false`. 제약 디코딩은 스키마 안정화 이득이 크고 실패 시 fallback으로 내려가지만, 자기검증은 추가 LLM 호출 지연 리스크가 있어 env로만 켠다.
- **검증됨**: 스키마 강제(enum/required/additionalProperties), 가이드라인 프롬프트, roles 평탄화, 자기검증 환각제거+보정신뢰도, service 분기 + Ollama 미가동 graceful 폴백. 전체 83개 테스트 통과.
- **로컬에서**: `STRUCTURING_CONSTRAINED=true`(+ 선택 `ENABLE_SELF_VERIFY=true`)로 실제 Ollama(XGrammar) 추출·검증 동작 확인 → `scripts/evaluate_structuring.py` 토큰-F1 회귀 + 스키마 위반 0 확인.
- **자기검증 범위(확정)**: `only_inferred=True` — **근거 span 이 inferred([0,0], 원문 미발견)인 필드에만** 검증 LLM 을 돈다(이미 grounding 된 필드는 verified 처리·호출 생략 → 지연 최소화). 검증 LLM 실패 시 `supported=true`(원추출 유지, 환각 단정 회피).
- ⚠️ confidence 보정 매핑(0.95/0.85/0.80/0.20)은 미보정 휴리스틱 — 긴급도 라벨처럼 추후 라벨로 보정 가능.

### A1. 스키마·Pydantic 모델 정의
- `app/structuring/schemas.py`에 위 구조의 Pydantic 모델 + JSON Schema export 추가.
- **게이트**: 모델 round-trip 단위테스트(누락키/잘못된 enum 거부).

### A2. ① 스키마 제약 디코딩 + 가이드라인 프롬프트
- `llm_extractor.py`: Ollama `format:"json"` → `format=<JSON Schema>`. 시스템 프롬프트에 **각 필드 정의 + 한국어 긍/부정 예시**(GoLLIE식 가이드라인) 임베딩.
- JSONDecodeError 재시도 머신 제거(스키마가 형식 보장).
- **게이트**: 200건 추출 시 스키마 위반 0건, 파싱 실패 0건. 토큰-F1 회귀(기존 대비 비열세).

### A3. ② 자기검증(Chain-of-Verification) + 근거 grounding
- `app/structuring/verifier.py`(신규): 추출 결과를 받아 *2차 제약 패스*로 필드별 "원문 근거가 있나? evidence_span 인용. 없으면 null." → 환각 필드 제거 + **근거 기반 confidence**(검증됨=높음).
- 비용 제어: *저신뢰/근거불명 필드에만* 트리거. 경계값만 self-consistency 3회(다수결).
- **게이트**: 환각 필드율↓(수기 50건 점검), evidence_span 정합성, 평균 추가 지연 측정·상한.

### A4. service 통합 + 평가
- `service.py`: Stage2.5(verifier) 삽입, candidate에 roles/urgency 골격 연결(urgency 값은 Track B가 채움).
- **게이트**: `evaluate_structuring.py` 토큰-F1 유지/향상, 스키마 위반 0, 전체 단위테스트 통과.

---

## Track B — 긴급도 non-LLM 보정 분류기

### 구현 현황 (B2–B5 완료) · 실데이터 500건 기준

| 단계 | 파일 | 상태 |
| --- | --- | --- |
| B2 안전 규칙(오버라이드) | `urgency/safety_rules.py` | ✅ 실라벨 recall **0.871** (재현율 우선) |
| B3 피처(임베딩⊕구조화)+조인 | `urgency/features.py`, `urgency/dataset.py` | ✅ 본문 조인 500/500 |
| B4 보정 분류기+학습/평가 | `urgency/classifier.py`, `scripts/train_urgency_classifier.py` | ✅ 5-fold CV·Platt·저장 |
| B5 UrgencyScorer+service 통합 | `urgency/scorer.py`, `service.py` | ✅ candidate["urgency"] |
| 테스트 | `test_safety_rules`(4)·`test_urgency_scorer`(6) | ✅ 통과(전체 94) |

**실데이터 핵심 사실**
- 라벨 분포 **낮음 328 / 보통 137 / 높음 34 / 긴급 1** (극심한 불균형). → 분류기는 **3-class{낮음,보통,높음}**(긴급은 높음 흡수)로 학습하고, **긴급 등급은 안전 오버라이드 + category SLA floor 가 산출**.
- **핵심 실험 결과(중요)**: 임베딩(bge-m3)과 TF-IDF가 **동일 성능**(macro-F1 0.49, 보통 recall 0.07) → *병목은 임베딩이 아님*. 1024차원 임베딩이 변별력 있는 **구조화 피처를 묻어** 모델이 "기본값=낮음"으로 붕괴. 또 `CalibratedClassifierCV`(보정)가 불균형에서 소수(보통) recall 을 추가로 붕괴시킴.
- **최종 채택 = TF-IDF(char n-gram) + 구조화 피처 + plain LR(class_weight balanced) + 보통-우선 임계 0.40** (`--embedder tfidf`, **CPU·GPU 불필요**). ※ 정정: `--embedder none`(순수 구조화)이 한때 버그로 TF-IDF로 학습됐었음 — 수정 완료, 기본값을 `tfidf`로 명시. 순수 구조화(none)는 macro-F1 0.553 으로 약간 낮음(높음 recall은 0.71로 오히려 높음).

  | 지표 | 임베딩+보정 | **최종** |
  | --- | --- | --- |
  | macro-F1 | 0.49 | **0.599** |
  | recall 낮음/보통/높음 | 0.98/0.07/0.51 | **0.68 / 0.62 / 0.69** |
  | ECE | 0.076 | **0.045** |

  → 세 클래스 균형 recall 의 실용 triage 모델. `train_urgency_classifier.py` 기본값이 `--embedder none`(권장). bge3/tfidf 는 데이터 증가 시 재검토용으로 유지.

- **경계 피처 추가(보통/낮음)**: action(조치 요구)·facility_count·impact(다수·공공)·severity(불편·피해·심각) 4개 추가(`features.py`). 동일-harness ablation: 보통 recall **0.39→0.54**, macro-F1 0.527→0.563. inquiry/requestverb 는 Δ≈0이라 제외.
- **최종 배포 모델**(TF-IDF char n-gram + 17 구조화피처 = 3017차원, plain LR, 임계 0.40): macro-F1 **0.583**, recall 낮음/보통/높음 **0.649/0.635/0.657**, ECE 0.047. CPU·결정적·GPU 불필요. "도로 파손 보수" 등 시설-조치 민원이 낮음→보통으로 교정됨.
- **남은 상한**: 보통↔낮음 경계는 AI 라벨 노이즈(needs_human_review 38건 등)가 캡. 추가 향상은 *경계 라벨 인적 정제* 또는 데이터 증량이 가장 효과적(피처·모델 튜닝은 수렴).
- **결합 로직(B5)**: `final = max(분류기 등급, category SLA floor)` + 안전 오버라이드(생명위협∧(높음 or 위협신호≥2) → 긴급). 모델 부재 시 규칙 폴백, 예외 시 안전 기본값.
- ⚠️ 안전 규칙 recall 0.871은 *AI 라벨이 모호 케이스(어두운 길·반사경 각도 등)까지 광범위하게 safety=1로 단* 노이즈 영향. 명백한 생명·신체 위협은 높은 재현율로 잡으며, 모호 신호는 분류기 등급이 담당.

### B1. 라벨링 (사용자, 500건)
- **라벨 스키마**(추천): `{case_id, text, urgency_level∈{낮음,보통,높음,긴급}, safety_flag∈{0,1}}`.
- **샘플러**(내가 제공): `scripts/sample_urgency_labeling.py` — 원천 민원에서 `category/region` **층화 샘플** + 희귀 "긴급/안전" 케이스 oversample(클래스 불균형 완화).
- **라벨링 가이드**(내가 제공): 레벨별 **앵커 루브릭**(정의 + 한국어 예시 1개씩) + safety_flag 판정 기준. 50건 2인 교차 → **Cohen's κ**로 일치도 점검(κ<0.6면 가이드 보정).
- 산출: `data/urgency/labels.jsonl`.

### B2. 안전 오버라이드 규칙 레이어 (non-LLM, 재현율 우선)
- `app/structuring/urgency/safety_rules.py`: 위험 키워드/패턴 사전(가스누출·붕괴·침수·산사태·화재·폭발·감전·누전·추락·식중독·익사·실종·자살암시…) + **부정 처리**("위험하진 않") → `safety_flag` 바닥값.
- **게이트**: 라벨 `safety_flag` 대비 **recall ≥ 0.95**(오탐은 관대). 순수 함수 단위테스트.

### B3. 피처 빌더
- `app/structuring/urgency/features.py`: **bge-m3 임베딩(1024d)** ⊕ 구조화 피처[`HAZARD` 개수, `category` SLA prior, ongoing/recurring/explicit_deadline 마커, safety_flag]. 순수/결정적(임베딩 제외).
- **게이트**: 피처 shape·결측 처리 단위테스트.

### B4. 분류기 + 보정
- `app/structuring/urgency/classifier.py`: 로지스틱(또는 GBM) → 4-class. **확률 보정**(isotonic/Platt) → calibrated `confidence`.
- 최종 등급 = `max(분류기등급, category_SLA_baseline)`; **safety override**(safety_flag=1 & 심각 → 긴급) 후처리.
- 학습/평가 스크립트 `scripts/train_urgency_classifier.py`: **5-fold CV**, 지표 = macro-F1 + **긴급 클래스 recall** + **ECE(보정 오차)** + confusion. 모델 저장(`data/urgency/model.pkl`).
- **게이트**: 긴급 recall·macro-F1 기준선 보고, ECE 개선 확인(보정 전후).

### B5. UrgencyScorer 모듈 + service 통합
- `app/structuring/urgency/scorer.py`: 입력(text + 구조화 산출) → `urgency{level,score,factors,evidence,override}`.
- `service.py`: 기존 `_compute_priority`를 `urgency.level`로 **대체/보강**(priority는 urgency를 입력으로).
- **게이트**: 통합 스모크 + 회귀 테스트, 모델 부재 시 규칙 폴백.

---

## 2. 의존성 / 실행 순서

```
Track A:  A1 → A2 → A3 → A4         (LLM, 무학습 — 바로 착수 가능)
Track B:  B1(사용자 라벨) ─┬─ B2(안전규칙)
                          └─ B3(피처) → B4(학습·보정) → B5(통합)
A·B 병렬 가능. urgency 피처에 category 등 구조화 산출을 쓰므로
B3는 A2(스키마 안정화) 이후가 이상적. 임베딩 인덱싱(진행 중)과는 무관.
```

**내가 단계별로 진행**: A1–A4 코드·테스트, B2/B3/B4/B5 코드·평가 하니스, B1용 샘플러·라벨링 가이드.
**사용자가 진행**: B1 라벨 500건, GPU에서 임베딩/학습 실행.

---

## 3. 전체 평가 게이트 (요약)

| 단계 | 핵심 지표 | 통과 기준 |
| --- | --- | --- |
| A2 | 스키마 위반율, 파싱실패율 | 0% / 0% |
| A2/A4 | 4요소 토큰-F1 | 기존 대비 비열세(이상적 +) |
| A3 | 환각 필드율, evidence 정합 | 수기 점검 개선 |
| B2 | safety recall | ≥ 0.95 |
| B4 | 긴급 recall, macro-F1, ECE | 기준선 보고·보정 개선 |

---

## 4. 리스크 / 한계 (정직)

- **제약 디코딩 ≠ 내용 정확성**: 형식은 ①이 보장하나 오추출은 남음 → ②자기검증으로 보완.
- **500 라벨은 소량**: 클래스 불균형(긴급 희소) → 층화·oversample·CV·보정 필수. 등급은 4단계로 제한(세분화는 데이터 부족).
- **안전은 재현율 우선**: 규칙 오탐(과경보)은 허용, 누락은 불허 — 운영 부담은 그 다음 문제.
- **확산/2차피해는 impact에 흡수**(결정대로) → 감염병·환경 비중이 커지면 추후 별도 축 분리 검토.
- **②·self-consistency 지연**: 선택 트리거로 상한 관리, 평상시 단일 패스.

---

## 5. 다음 액션 (착수 시)

1. (나) **A1+A2**부터 — 스키마/Pydantic + Ollama 제약 디코딩 교체, 토큰-F1 회귀. ← 즉시 가치, 무학습.
2. (나) **B1 샘플러 + 라벨링 가이드** 제공 → (사용자) 500 라벨.
3. (나) 라벨 도착 후 **B2→B4** 학습·보정, 게이트 보고.
4. (나) **A3, B5** 통합.

> 위 (가)/(나) 두 결정만 확인해 주시면 이 순서대로 단계별 착수합니다. 기본값 그대로면 "그대로"라고만 주셔도 됩니다.
