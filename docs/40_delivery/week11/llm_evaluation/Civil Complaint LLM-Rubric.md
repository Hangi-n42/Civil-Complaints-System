아래처럼 **논문식 LLM-Rubric 평가 파이프라인 전체**를 민원 회신 도메인에 맞게 재설계하는 것입니다.

핵심은 이 구조입니다.

```text
민원 회신 생성
→ 평가 입력 패키지 구성
→ Q0~Q7 LLM judge 평가
→ 선택지별 probability vector 저장
→ rule feature 추출
→ calibration model로 사람 평가 예측
→ safety layer 적용
→ 최종 리포트 및 실패 원인 기록
```

논문 기준에서 가장 중요한 점은 LLM이 각 rubric 질문에 대해 단일 점수만 내는 것이 아니라 **선택지별 확률분포를 만들고**, 그 여러 분포를 calibration network가 결합해 사람 judge의 평가를 예측한다는 점입니다. 논문은 manually constructed rubric을 사용해 여러 평가 차원을 묻고, 각 질문의 LLM response distribution을 작은 feed-forward network로 보정해 human annotation을 예측하는 방식으로 설명합니다. ([arXiv][1])

---

# 1. 전체 설계 원칙

이번 LLM-Rubric은 이렇게 정의하면 됩니다.

```text
Civil Complaint LLM-Rubric Q0-Q7

논문 LLM-Rubric의 다차원 LLM 확률 평가 및 calibration 구조를 유지하되,
공직자 민원응대 핵심 매뉴얼의 정중성, 공감·경청, 명확한 근거규정,
절차 안내, 반복·동문서답 방지, 특이민원 안전성 기준을
한국어 민원 회신 평가에 맞게 반영한 평가 파이프라인이다.
```

여기서 중요한 설계 원칙은 6가지입니다.

| 원칙                   | 적용 방식                                                |
| -------------------- | ---------------------------------------------------- |
| Q0는 가중평균이 아님         | Q0도 LLM judge가 독립 평가하고, 최종 Q0는 calibration으로 예측      |
| Q0~Q7만 사용            | Q8, Q9, Q10은 만들지 않고 안전성·완결성은 Q0~Q7과 safety layer에 분산 |
| 내부 점수는 1~4           | 논문처럼 각 Q는 1~4 선택지 평가                                 |
| 저장은 label이 아니라 확률분포  | `probs=[p1,p2,p3,p4]` 저장                             |
| rule score는 최종 점수 아님 | citation count, 반복률, risk flag는 calibration feature  |
| 민원 매뉴얼은 평가 앵커        | 정중성, 근거규정, 절차 안내, 담당자 보호 기준을 각 Q와 safety layer에 반영   |

민원 매뉴얼은 민원응대 기본 방향으로 신속·공정·친절·적법한 처리, 민원인의 눈높이에 맞춘 정중하고 정확한 설명, 공감·경청을 통한 문제 해결 노력을 제시합니다. 또한 일반 민원에서는 정중한 어투, 민원사항 정확한 파악, 이해하기 쉬운 설명, 절차 안내, 해결 방안 또는 어려운 상황 설명, 명확한 근거규정 제시를 요구합니다.

---

# 2. 최종 Q0~Q7 역할

Q 내용 자체는 앞서 정한 것을 유지하되, 전체 로직 안에서는 각각의 역할을 명확히 나눠야 합니다.

| 항목 | 이름              | 파이프라인상 역할                                  |
| -- | --------------- | ------------------------------------------ |
| Q0 | 전체 민원 회신 만족도    | 최종 사람 만족도 예측의 중심 target                    |
| Q1 | 공공기관 회신 문체와 정중성 | tone, 공감, 눈높이 설명, 감정적 대응 여부 평가             |
| Q2 | 근거 자료 충분성       | retrieval/reference adequacy 평가, 생성 답변과 분리 |
| Q3 | 핵심 주장 인용 포함성    | claim-citation coverage 평가                 |
| Q4 | 인용 근거 정확성       | citation이 claim을 실제로 support하는지 평가         |
| Q5 | 최적 근거 선택성       | 제공 source 중 가장 직접적인 근거를 골랐는지 평가            |
| Q6 | 반복·불필요 요소 없음    | 반복, 복붙, 동문서답, 내부 메타데이터 노출 평가               |
| Q7 | 간결성과 업무 완결성     | 필요한 요지·판단·근거·절차·후속 안내를 간결하게 포함했는지 평가       |

Q0~Q7만 쓸 때는 **업무 완결성은 Q7**, **행정 안전성은 Q0·Q1·Q4·Q5·Q7과 safety layer**로 분산시키는 게 좋습니다.

---

# 3. 평가 파이프라인 전체 구조

전체 파이프라인은 9단계로 나누는 게 좋습니다.

```text
1. 입력 수집
2. 답변 생성
3. 평가 패키지 구성
4. 사전 진단 pre-check
5. Q0~Q7 LLM judge 실행
6. rule feature 추출
7. calibration 적용
8. safety layer 적용
9. 평가 리포트 및 로그 저장
```

각 단계를 자세히 보면 다음과 같습니다.

---

# 4. 1단계: 입력 수집

평가기는 단순히 `generated_answer`만 받으면 안 됩니다. 논문에 더 가깝게 만들려면 평가 대상과 근거를 하나의 패키지로 만들어야 합니다.

필수 입력은 다음입니다.

```json
{
  "case_id": "civil_000001",
  "complaint_text": "...",
  "complaint_summary": "...",
  "generated_answer": "...",
  "references": [
    {
      "source_id": "R1",
      "title": "...",
      "text": "...",
      "source_type": "law|manual|guideline|homepage|faq|other",
      "priority": 1
    }
  ],
  "citations": [
    {
      "claim_id": "C1",
      "claim_text": "...",
      "source_id": "R1",
      "span": "..."
    }
  ],
  "consultant_answer": "... optional ..."
}
```

여기서 중요한 건 `source_type`과 `priority`입니다. Q5에서 “가장 적절한 근거를 골랐는가”를 평가하려면 source 우선순위가 있어야 합니다.

추천 source 우선순위는 다음입니다.

| 우선순위 | source type               |
| ---: | ------------------------- |
|    1 | 법령, 시행령, 조례, 고시           |
|    2 | 공식 행정 지침, 민원처리 기준, 업무 매뉴얼 |
|    3 | 기관 홈페이지 안내, 공식 FAQ        |
|    4 | 일반 안내문, 보도자료, 설명자료        |
|    5 | 비공식 또는 약한 근거              |

민원 응대 매뉴얼은 이 구조에서 보통 `manual` 또는 `official_guideline`에 해당합니다.

---

# 5. 2단계: 답변 생성

생성 모델은 기존처럼 민원 회신을 만듭니다. 다만 평가를 제대로 하려면 생성 단계부터 다음 정보를 남겨야 합니다.

```json
{
  "generated_body": "...",
  "reply_shell": {
    "opening": "...",
    "body": "...",
    "closing": "..."
  },
  "model_citations_raw": [],
  "postprocessed_citations": [],
  "retrieval_context_ids": [],
  "generation_model": "...",
  "prompt_version": "..."
}
```

여기서 `model_citations_raw`와 `postprocessed_citations`를 분리해야 합니다.

이유는 간단합니다.

```text
모델이 실제로 근거를 붙인 것
≠
후처리기가 나중에 붙인 citation
```

Q3, Q4에서 이 둘을 구분해야 점수가 왜곡되지 않습니다.

---

# 6. 3단계: 평가 패키지 구성

LLM judge에게는 원문 데이터를 그대로 던지는 것보다, 일관된 포맷으로 구성한 평가 패키지를 넣어야 합니다.

## 일반 Q 평가용 패키지

```text
[민원 원문]
{complaint_text}

[민원 요약]
{complaint_summary}

[생성 답변]
{generated_answer}

[제공된 근거 자료]
R1. {reference_1}
R2. {reference_2}
R3. {reference_3}

[구조화 citation]
C1. "{claim_text}" → R1
C2. "{claim_text}" → R2

[참조 답안]
{consultant_answer, optional}
```

단, Q2는 다릅니다.

## Q2 전용 패키지

```text
[민원 원문]
{complaint_text}

[민원 요약]
{complaint_summary}

[제공된 근거 자료]
R1. {reference_1}
R2. {reference_2}
R3. {reference_3}
```

Q2는 논문 원형에 맞게 **생성 답변을 보지 않고 reference adequacy만 평가**해야 합니다. 이 분리를 하지 않으면 Q2가 “검색 품질”이 아니라 “답변 품질” 평가로 섞입니다.

---

# 7. 4단계: 사전 진단 pre-check

LLM judge를 호출하기 전에 규칙 기반 pre-check를 먼저 돌리는 게 좋습니다. 단, 이 단계는 점수 계산용이 아니라 **평가 가능성 확인과 risk flag 생성용**입니다.

## Pre-check 항목

| 항목                          | 목적                       |
| --------------------------- | ------------------------ |
| empty answer check          | 빈 답변이면 평가 불가             |
| language check              | 한국어 민원 회신으로 작성됐는지        |
| shell check                 | 회신 형식이 심하게 깨졌는지          |
| citation parse check        | citation 구조가 파싱 가능한지     |
| reference availability      | reference가 존재하는지         |
| debug leakage check         | JSON, 로그, 검색 메타데이터 노출 여부 |
| personal data leakage check | 불필요한 개인정보 노출 여부          |
| unsafe promise check        | 권한 밖 직접 조치 약속 여부         |
| emotional response check    | 감정적 맞대응, 비난, 위협 표현 여부    |

특히 매뉴얼은 특이민원 대응에서 감정적 맞대응 금지, 개인 견해나 언쟁 회피, 법령 및 규정에 근거한 원칙 대응, 증거자료 확보, 담당자 보호와 부서 차원 대응을 강조합니다. 따라서 감정적 맞대응, 근거 없는 법적 경고, 개인적 판단 표현은 pre-check에서 risk flag로 잡는 게 좋습니다.

---

# 8. 5단계: Q0~Q7 LLM judge 실행

각 Q는 독립적으로 평가해야 합니다. 한 번에 JSON으로 Q0~Q7을 모두 묻는 방식은 편하지만, 논문 방식과는 조금 멀어집니다.

권장 방식은 다음입니다.

```text
for q in [Q0, Q1, ..., Q7]:
    prompt = build_prompt(q, evaluation_package)
    probs = judge_model.get_logprobs(["1", "2", "3", "4"])
    save probs
```

## Judge prompt 기본형

```text
You are evaluating a Korean public-sector civil complaint response.

Use the given rubric question and choose exactly one option.
Do not explain your answer.
Only output one of: 1, 2, 3, 4.

[Input]
{evaluation_package}

[Question]
{question}

[Options]
1. {option_1}
2. {option_2}
3. {option_3}
4. {option_4}

Answer:
```

중요한 것은 출력 label만 저장하지 않는 것입니다.

나쁜 저장 방식:

```json
{
  "q4": 3
}
```

좋은 저장 방식:

```json
{
  "q4": {
    "probs": [0.03, 0.12, 0.61, 0.24],
    "argmax": 3,
    "expected_1_4": 3.06,
    "entropy": 0.98
  }
}
```

논문식 구조에서는 이 `probs`가 calibration model의 핵심 입력입니다.

---

# 9. 6단계: rule feature 추출

현재 프로젝트의 규칙 기반 점수는 버리는 게 아니라 역할을 바꿔야 합니다.

기존:

```text
rule score → Q 점수 → Q0 가중평균
```

새 구조:

```text
rule feature → calibration feature + safety flag + diagnostic report
```

## 추출할 rule feature

| feature                        | 관련 Q         | 용도                         |
| ------------------------------ | ------------ | -------------------------- |
| `strict_citation_count`        | Q3           | 핵심 claim에 citation이 있는지 보조 |
| `claim_count`                  | Q3           | citation coverage 계산       |
| `citation_coverage_rate`       | Q3           | claim-citation 비율          |
| `citation_support_rate_strict` | Q4           | 인용 정확성 보조                  |
| `source_priority_mean`         | Q5           | 좋은 source 사용 여부            |
| `best_source_missed_count`     | Q5           | 더 좋은 source 누락 여부          |
| `repetition_ratio`             | Q6           | 반복 탐지                      |
| `template_ratio`               | Q6           | 상투적 문구 비율                  |
| `debug_token_count`            | Q6           | 내부 메타데이터 노출                |
| `answer_token_length`          | Q7           | 길이 평가                      |
| `consultant_length_ratio`      | Q7           | 참조 답안 대비 과소·과대 답변          |
| `procedure_anchor_count`       | Q7           | 절차 안내 포함 여부                |
| `legal_anchor_count`           | Q4/Q5/Q7     | 법령·규정 근거 포함 여부             |
| `followup_anchor_count`        | Q7           | 후속 안내 포함 여부                |
| `unsafe_promise_flag`          | Q0/Q7/safety | 권한 밖 약속                    |
| `emotional_response_flag`      | Q1/safety    | 감정적 맞대응                    |
| `special_complaint_flag`       | Q0/Q7/safety | 반복·폭언·협박 등 특이민원 여부         |

민원 매뉴얼이 일반 민원에서 요구하는 “민원사항 정확한 파악, 이해하기 쉬운 설명, 절차 안내, 해결 방안 또는 어려운 상황 설명, 명확한 근거규정 제시, 담당자 소속·성명·연락처 안내”는 `procedure_anchor`, `legal_anchor`, `followup_anchor`, `contact_anchor` 같은 feature로 만들 수 있습니다.

---

# 10. 7단계: calibration model 적용

논문 기준으로 가장 중요한 단계입니다.

LLM judge raw score를 그대로 최종 점수로 쓰지 말고, 사람 평가 데이터에 맞게 보정해야 합니다.

## 입력

```text
x = [
  q0_probs[4],
  q1_probs[4],
  ...
  q7_probs[4],
  rule_features,
  case_metadata
]
```

Q0~Q7만 쓰면 LLM probability feature는 총 32개입니다.

```text
8 questions × 4 choices = 32 probability features
```

여기에 rule feature를 붙입니다.

```text
x = 32 LLM probability features
  + citation features
  + source priority features
  + repetition features
  + length features
  + risk flags
```

## 출력

처음에는 Q0만 예측해도 됩니다.

```json
{
  "calibrated_q0_distribution": [0.02, 0.13, 0.45, 0.40],
  "calibrated_q0_expected_1_4": 3.23
}
```

나중에는 Q0~Q7 전체를 예측하게 확장할 수 있습니다.

```json
{
  "calibrated": {
    "q0": [0.02, 0.13, 0.45, 0.40],
    "q1": [0.01, 0.08, 0.44, 0.47],
    "...": "..."
  }
}
```

## 모델 선택 순서

처음부터 neural network로 가기보다 단계적으로 가는 게 좋습니다.

| 단계 | 모델                          | 추천 이유                 |
| -- | --------------------------- | --------------------- |
| 1  | uncalibrated expected score | baseline              |
| 2  | ridge regression            | 데이터 적을 때 안정적          |
| 3  | ordinal logistic regression | 1~4 ordinal label에 적합 |
| 4  | gradient boosting           | rule feature와 잘 맞음    |
| 5  | small MLP                   | 논문 구조와 가장 유사          |

데이터가 100~300건이면 ridge나 ordinal logistic부터 시작하는 게 안정적입니다. 500~1000건 이상 쌓이면 small MLP로 가는 게 좋습니다.

---

# 11. 8단계: safety layer 적용

Q0~Q7만 사용하면 별도 Q10 행정 안전성 문항이 없기 때문에, **safety layer는 반드시 따로 둬야 합니다.**

이 layer는 점수를 만드는 단계가 아니라, 최종 점수의 상한을 제한하는 단계입니다.

```text
q0_calibrated = calibration_model(...)
q0_final = min(q0_calibrated, safety_cap)
```

## Safety cap 예시

| 조건                                   | Q0 최종 상한 |
| ------------------------------------ | -------: |
| 빈 답변 또는 평가 불가                        |      0.0 |
| 내부 JSON, 검색 로그, 시스템 메타데이터 노출         |      3.0 |
| 민원 요지와 반대 결론                         |      3.5 |
| 권한 밖 직접 조치 약속                        |      4.0 |
| citation 전무                          |      4.0 |
| 핵심 법령·규정 판단이 reference와 충돌           |      4.5 |
| 특이민원에 감정적 맞대응                        |      4.5 |
| 근거 없는 법적 처벌 경고                       |      5.0 |
| 반복민원 종결 안내에서 이의제기·절차 누락              |      5.5 |
| strict citation은 없고 후처리 citation만 존재 |      6.5 |

매뉴얼은 온라인·문서민원에서 폭언 등이 있는 경우 부서장 보고, 경고공문 통지, 법적 조치 관련 전담부서 협의 등을 제시하고, 반복민원은 민원조정위원회 심의, 결정근거 및 이의제기 절차 안내 등을 요구합니다. 따라서 이런 절차가 필요한 상황에서 답변이 개인적 경고만 하거나, 종결만 통보하고 절차 안내를 누락하면 safety risk로 잡는 것이 좋습니다.

---

# 12. 9단계: 최종 리포트 생성

최종 결과는 단순 점수 하나가 아니라, 아래처럼 여러 층으로 저장해야 합니다.

```json
{
  "case_id": "civil_000001",
  "rubric_version": "civil_llm_rubric_q0_q7_v1",
  "judge_model": "judge-model-name",
  "llm_rubric_raw": {
    "q0": {
      "probs": [0.02, 0.10, 0.38, 0.50],
      "argmax": 4,
      "expected_1_4": 3.36,
      "score_0_10": 7.87
    },
    "q1": {
      "probs": [0.01, 0.08, 0.41, 0.50],
      "argmax": 4,
      "expected_1_4": 3.40,
      "score_0_10": 8.00
    }
  },
  "rule_features": {
    "strict_citation_count": 3,
    "citation_coverage_rate": 0.75,
    "citation_support_rate_strict": 0.82,
    "repetition_ratio": 0.03,
    "answer_token_length": 420,
    "procedure_anchor_count": 2,
    "legal_anchor_count": 3,
    "followup_anchor_count": 1,
    "risk_flags": []
  },
  "calibrated_prediction": {
    "q0_expected_1_4": 3.21,
    "q0_score_0_10": 7.37
  },
  "safety_layer": {
    "cap_applied": false,
    "cap_reason": null,
    "final_q0_score_0_10": 7.37
  },
  "diagnostics": {
    "main_failure_reasons": [],
    "recommended_fix": []
  }
}
```

0~10 환산은 다음 공식을 쓰면 됩니다.

```text
score_0_10 = (expected_1_4 - 1) / 3 * 10
```

다만 최종 보고서에서는 최소한 네 가지 점수를 분리해서 보여주는 게 좋습니다.

| 점수                 | 의미                    |
| ------------------ | --------------------- |
| `q0_llm_raw`       | LLM judge가 직접 본 Q0    |
| `q0_rule_baseline` | 기존 규칙 기반 baseline     |
| `q0_calibrated`    | 사람 평가에 맞춘 예측값         |
| `q0_final`         | safety cap 적용 후 최종 점수 |

이렇게 분리해야 모델 개선 원인을 추적할 수 있습니다.

---

# 13. Human annotation 파이프라인

논문식 LLM-Rubric을 제대로 만들려면 사람 평가 데이터가 필요합니다.

## 샘플링

민원 답변 샘플은 유형별로 균형 있게 뽑는 게 좋습니다.

| 유형               | 포함 이유                    |
| ---------------- | ------------------------ |
| 일반 질의형 민원        | 기본 응대 품질 평가              |
| 처리 불가·제한 민원      | 근거규정과 제약 설명 평가           |
| 절차 안내 민원         | Q7 업무 완결성 평가             |
| 반복민원             | 반복·종결·이의제기 안내 평가         |
| 폭언·협박 포함 온라인 민원  | 안전성, 감정적 대응 방지 평가        |
| 근거 부족 case       | Q2 retrieval adequacy 평가 |
| citation 오류 case | Q3~Q5 평가                 |
| 지나치게 짧거나 긴 답변    | Q6~Q7 평가                 |

## 평가자 구성

최소:

```text
샘플 200건 × 평가자 2명
```

권장:

```text
샘플 500~1000건 × 평가자 3명
```

평가자는 각 case에 대해 Q0~Q7을 1~4로 채점합니다. 가능하면 짧은 사유도 남기게 하는 게 좋습니다.

```json
{
  "human_judge_id": "J1",
  "case_id": "civil_000001",
  "labels": {
    "q0": 3,
    "q1": 4,
    "q2": 3,
    "q3": 2,
    "q4": 3,
    "q5": 3,
    "q6": 4,
    "q7": 3
  },
  "comment": "답변은 정중하지만 반복민원 처리 절차와 이의제기 안내가 부족함."
}
```

## 평가자 가이드

사람 평가자에게도 Q별 기준을 줘야 합니다. 특히 다음을 강조해야 합니다.

```text
Q2는 생성 답변을 보지 말고 reference만 평가한다.
Q3는 citation 존재 여부만 본다.
Q4는 citation support를 본다.
Q5는 더 좋은 source가 있었는지 본다.
Q7은 짧음만 보지 말고 민원 회신의 필요 요소가 포함됐는지 본다.
```

---

# 14. Calibration 학습 및 검증 지표

Calibration model을 학습한 뒤에는 다음 지표로 평가합니다.

| 지표                | 의미                         |
| ----------------- | -------------------------- |
| MAE               | 사람 점수와 평균 절대 오차            |
| RMSE              | 큰 오차에 더 민감한 평가             |
| Pearson           | 선형 상관                      |
| Spearman          | 순위 상관                      |
| Weighted kappa    | 1~4 ordinal label 일치도      |
| Calibration curve | 예측 확률이 실제 빈도와 맞는지          |
| ECE               | expected calibration error |

논문은 LLM-Rubric이 9개 질문을 사용해 전체 사용자 만족도 예측에서 uncalibrated baseline보다 좋은 성능을 보였다고 보고합니다. 따라서 프로젝트에서도 비교 기준은 최소 세 개를 둬야 합니다. ([arXiv][1])

```text
Baseline A: 기존 rule-based Q0
Baseline B: LLM direct Q0 expected
Proposed: Q0~Q7 probability vectors + calibration + safety layer
```

---

# 15. 운영 환경에서의 평가 흐름

실제 프로젝트에 붙일 때는 두 가지 모드로 나누는 게 좋습니다.

## 개발·실험 모드

모든 정보를 자세히 저장합니다.

```text
LLM judge raw probs
rule features
prompt
reference
citation mapping
calibration input vector
safety cap reason
diagnostic explanation
```

이 모드는 디버깅과 논문·보고서 작성에 필요합니다.

## 운영·배치 평가 모드

필요한 결과만 저장합니다.

```text
case_id
final_q0
q0~q7 score
cap reason
top failure reasons
model version
rubric version
```

---

# 16. 실패 원인 taxonomy

평가 결과가 낮을 때 단순히 “점수 낮음”으로 끝내면 개선이 어렵습니다. 실패 원인을 구조화해야 합니다.

추천 taxonomy는 다음입니다.

```text
R1. retrieval_insufficient
R2. missing_citation
R3. weak_citation_support
R4. suboptimal_source
R5. tone_inappropriate
R6. redundant_or_template_answer
R7. incomplete_procedure_guidance
R8. missing_legal_basis
R9. unsafe_promise
R10. emotional_response
R11. repeated_complaint_process_missing
R12. special_complaint_safety_missing
R13. debug_or_metadata_leakage
```

이 taxonomy는 Q별로 연결됩니다.

| 실패 원인                              | 연결 Q         |
| ---------------------------------- | ------------ |
| retrieval_insufficient             | Q2           |
| missing_citation                   | Q3           |
| weak_citation_support              | Q4           |
| suboptimal_source                  | Q5           |
| tone_inappropriate                 | Q1           |
| redundant_or_template_answer       | Q6           |
| incomplete_procedure_guidance      | Q7           |
| missing_legal_basis                | Q4/Q7        |
| unsafe_promise                     | Q0/Q7/safety |
| emotional_response                 | Q1/safety    |
| repeated_complaint_process_missing | Q7/safety    |
| special_complaint_safety_missing   | Q0/Q7/safety |

---

# 17. 민원 매뉴얼 반영 규칙

매뉴얼을 코드 로직으로 반영할 때는 “문항 내용”뿐 아니라 risk detector에도 넣어야 합니다.

## 매뉴얼 → 로직 변환

| 매뉴얼 기준             | 적용 로직                                   |
| ------------------ | --------------------------------------- |
| 정중하고 정확한 응대        | Q1 tone judge, rude expression detector |
| 공감·경청              | Q1 empathy anchor                       |
| 민원사항 정확한 파악        | complaint-answer alignment feature      |
| 이해하기 쉬운 설명         | Q1/Q7 judge                             |
| 절차 안내              | procedure anchor extractor              |
| 해결 방안 또는 어려운 상황 설명 | resolution/constraint extractor         |
| 명확한 근거규정 제시        | legal basis extractor, Q4/Q7            |
| 담당자 소속·성명·연락처 안내   | contact anchor, 상황별 optional feature    |
| 감정적 맞대응 금지         | emotional response detector             |
| 법령·규정 근거 대응        | Q4/Q5, legal grounding feature          |
| 반복민원 절차            | repeated complaint detector + Q7/safety |
| 온라인 폭언 경고공문        | special complaint detector + safety     |
| 담당자 보호             | unsafe instruction detector             |

특히 매뉴얼은 특이민원을 일반 민원과 분리하고, 위법민원과 부당민원을 구분해 대응하도록 합니다. 반복 전화·반복민원, 폭언·협박, 온라인 문서민원 등은 일반적인 친절 응대만으로 평가하면 안 되고, 안전성 및 절차 준수까지 봐야 합니다.

---

# 18. Answer generation 개선에 평가 결과를 연결하는 방법

평가기는 점수만 내는 용도가 아니라, 다음 생성 개선으로 이어져야 합니다.

## 개선 루프

```text
낮은 Q 탐지
→ 실패 원인 taxonomy 매핑
→ prompt 또는 retrieval 개선
→ 재생성
→ 재평가
```

예를 들어:

| 낮은 점수         | 개선 조치                                    |
| ------------- | ---------------------------------------- |
| Q1 낮음         | 공공기관 문체 prompt 강화                        |
| Q2 낮음         | retrieval query reformulation, source 추가 |
| Q3 낮음         | claim-citation insertion 강화              |
| Q4 낮음         | citation verifier 추가                     |
| Q5 낮음         | source reranker 개선                       |
| Q6 낮음         | template repetition penalty              |
| Q7 낮음         | 민원 회신 체크리스트 기반 보완 생성                     |
| safety cap 적용 | 답변 재생성 또는 human review queue             |

실무적으로는 `final_q0 < 6.0` 또는 `safety_cap_applied=true`이면 자동 재생성하거나 사람 검토 큐로 보내는 정책을 둘 수 있습니다.

---

# 19. Human review queue 기준

자동 평가 후 다음 case는 사람 검토로 보내는 것이 좋습니다.

| 조건                                             | 처리           |
| ---------------------------------------------- | ------------ |
| `q0_final < 5.0`                               | human review |
| `safety_cap_applied = true`                    | human review |
| `Q4 < 2.5`                                     | citation 검토  |
| `Q7 < 2.5`                                     | 업무 완결성 검토    |
| `unsafe_promise_flag = true`                   | 필수 검토        |
| `special_complaint_flag = true` and `Q7 < 3.0` | 필수 검토        |
| `judge_entropy_high = true`                    | 불확실 case 검토  |

`entropy`가 높은 case는 LLM judge가 확신하지 못하는 case입니다. 이런 case는 calibration 데이터로도 가치가 높습니다.

---

# 20. 버전 관리

Rubric은 반드시 버전 관리해야 합니다.

```json
{
  "rubric_version": "civil_llm_rubric_q0_q7_v1.0",
  "judge_prompt_version": "judge_prompt_2026_06_18",
  "calibration_model_version": "calib_mlp_v0.1",
  "safety_policy_version": "safety_cap_v0.2",
  "manual_reference_version": "civil_service_response_manual_uploaded_2026_06_17"
}
```

나중에 Q 선택지 문구가 바뀌면 과거 점수와 비교가 어려워지기 때문에, prompt와 rubric version은 반드시 저장해야 합니다.

---

# 21. 최종 구현 우선순위

현석님 프로젝트에서 바로 적용한다면 순서는 이렇게 가는 게 가장 좋습니다.

```text
1. Q0~Q7 rubric 문항과 선택지 확정
2. 평가 입력 패키지 스키마 확정
3. Q별 judge prompt 작성
4. Q2 전용 ref-only 입력 분리
5. LLM logprob 기반 probs 저장 구현
6. 기존 rule evaluator를 feature extractor로 변경
7. safety cap layer 분리
8. raw LLM score와 rule baseline 병렬 출력
9. 사람 평가 데이터 수집
10. ridge/ordinal calibration 학습
11. final report schema 고정
12. 낮은 Q별 자동 개선 루프 연결
```

처음부터 calibration까지 완성하지 않아도 됩니다. 1차 버전은 다음만 구현해도 충분합니다.

```text
Q0~Q7 LLM judge raw probability
+ rule feature
+ safety cap
+ diagnostic report
```

그 다음 사람 평가 데이터가 쌓이면 calibration을 붙이면 됩니다.

---

# 22. 전체 요약

현석님이 만들 LLM-Rubric은 단순히 Q0~Q7을 정의하는 수준이 아니라, 아래 구조로 가야 합니다.

```text
[논문식 핵심]
Q별 독립 LLM 평가
선택지별 probability vector 저장
calibration으로 사람 평가 예측

[민원 매뉴얼 반영]
정중성, 공감·경청, 명확한 근거규정, 절차 안내,
반복·동문서답 방지, 특이민원 안전성 반영

[프로젝트 파이프라인]
pre-check
→ LLM judge
→ rule feature
→ calibration
→ safety layer
→ diagnostic report
→ 재생성/사람검토 큐
```

따라서 최종 구조는 이렇게 잡으면 됩니다.

```text
Q0~Q7 = 논문식 평가 문항
rule features = 보조 신호
calibration = 최종 사람 평가 예측
safety layer = 행정상 치명 오류 제한
diagnostics = 모델 개선을 위한 실패 원인 기록
```

이 방식이면 “민원 매뉴얼을 참고한 규칙 기반 점수표”가 아니라, **논문 LLM-Rubric을 기준으로 삼고 민원 응대 매뉴얼을 도메인 기준으로 결합한 평가 시스템**이라고 설명할 수 있습니다.

[1]: https://arxiv.org/abs/2501.00274?utm_source=chatgpt.com "LLM-Rubric: A Multidimensional, Calibrated Approach to Automated Evaluation of Natural Language Texts"
