# Civil Complaint LLM-Rubric 설계 및 구현 현황

이 문서는 민원 답변 생성 후 즉시 실행되는 신규 LLM-Rubric의 현재 설계와 코드 구현 상태를 정리한다.

기존 방식은 벤치마크 산출물을 별도로 평가하는 흐름에 가까웠다. 현재 설계는 실제 서비스의 `/api/v1/qa` 응답 생성 파이프라인 안에서 답변 초안을 평가하고, 낮은 점수가 나온 항목이 있으면 Prometheus-style feedback을 이용해 1회 재생성까지 시도하는 구조다.

관련 구현 파일은 다음과 같다.

| 구분 | 파일 |
| --- | --- |
| LLM-Rubric 평가기 | `app/evaluation/civil_llm_rubric.py` |
| Prometheus feedback 및 재생성 프롬프트 | `app/evaluation/prometheus_feedback.py` |
| QA 파이프라인 연결 | `app/api/routers/generation.py` |
| 설정값 | `app/core/config.py` |
| API 응답 스키마 | `app/api/schemas/generation.py` |
| 응답 정규화 | `app/generation/normalization/response_normalizer.py` |

---

## 1. 현재 런타임 파이프라인

현재 QA 서비스의 정상 RAG 경로는 아래 순서로 동작한다.

```text
1. /api/v1/qa 요청 수신
2. 검색 context 구성
3. 답변 초안 생성
4. 응답 normalize 및 QA contract validation
5. citation validation
6. Civil LLM-Rubric Q0~Q7 평가
7. Q별 1~4 점수에서 2점 이하 항목 탐지
8. 낮은 항목이 있으면 Prometheus feedback 생성
9. feedback을 반영해 답변 1회 재생성
10. 재생성 답변 validation 및 citation validation
11. 재생성 답변에 대해 LLM-Rubric 재평가
12. 최종 응답의 generation_metadata와 quality_signals에 평가 결과 첨부
```

단, 유사 근거가 없어 `no_evidence_fallback` 응답을 만드는 경로에서는 현재 LLM-Rubric 평가 결과만 붙이고 Prometheus 재생성은 실행하지 않는다. 근거가 부족한 상황에서 재생성을 반복하면 없는 근거를 꾸며낼 위험이 있기 때문이다.

---

## 2. LLM-Rubric의 핵심 원칙

신규 LLM-Rubric은 논문 LLM-Rubric의 핵심 아이디어인 다차원 rubric 평가와 점수 분포 저장 방식을 민원 답변 도메인에 맞게 변형한 것이다.

현재 구현 원칙은 다음과 같다.

| 원칙 | 현재 적용 방식 |
| --- | --- |
| Q0~Q7만 사용 | Q8~Q10은 만들지 않고, 안전성/업무 완결성은 feature와 safety layer로 분리 |
| 각 항목은 1~4 선택지 | 모든 Q는 1, 2, 3, 4 중 하나의 평가 축으로 정의 |
| 단일 점수보다 분포 저장 | `probs`, `argmax`, `expected_1_4`, `entropy` 저장 |
| 0~10 점수는 보고용 환산값 | 실제 rubric 기준은 1~4이며, 0~10은 API/비교 편의를 위한 환산 |
| Q2는 답변을 보지 않음 | Q2는 reference adequacy 평가이므로 생성 답변 없이 근거 자료만 본다 |
| rule score는 최종 점수가 아님 | citation, 반복, 길이, 위험 flag 등은 보조 feature로 사용 |
| calibration은 아직 미구현 | 현재 `calibrated_prediction.available=false`이며 향후 사람 평가 데이터로 학습 예정 |
| safety layer로 치명적 오류 상한 적용 | 내부 메타데이터 노출, citation 부재, 위험한 약속 등은 Q0 최종 점수 상한을 건다 |

---

## 3. Q0~Q7 평가 항목

| 항목 | 이름 | 평가 역할 |
| --- | --- | --- |
| Q0 | 전체 민원 답변 만족도 | 최종 품질을 대표하는 중심 항목. safety layer 적용 대상 |
| Q1 | 공공기관 답변 문체와 정중성 | 정중함, 공감, 공식 문체, 감정적 대응 여부 평가 |
| Q2 | 근거 자료 충분성 | 검색된 reference가 답변 작성에 충분한지 평가. 생성 답변은 입력하지 않음 |
| Q3 | 답변 주장 인용 포함성 | 주요 주장에 citation이 붙어 있는지 평가 |
| Q4 | 인용 근거 정확성 | citation이 실제 주장과 잘 맞는지 평가 |
| Q5 | 최적 근거 선택성 | 제공 source 중 가장 직접적이고 신뢰도 높은 근거를 썼는지 평가 |
| Q6 | 반복/불필요 요소 없음 | 반복, 동문서답, 내부 메타데이터 노출, 과도한 템플릿 문구 평가 |
| Q7 | 답변 효율성 및 간결성 | 민원 복잡도 대비 길이, 정보 밀도, 설명 부담이 적절한지 평가 |

### Q7과 업무 완결성의 분리

Q7은 답변의 길이와 정보 밀도, 간결성을 평가한다. 업무적으로 필요한 절차, 법적 근거, 후속 안내가 모두 들어갔는지는 `manual_completeness_features`에서 별도로 본다.

이렇게 분리한 이유는 간단하다.

```text
간결하지만 절차 안내가 빠진 답변
vs
업무 요소는 많지만 너무 길고 읽기 어려운 답변
```

두 경우는 서로 다른 실패 유형이다. Q7 하나에 두 의미를 같이 넣으면 평가가 흔들리므로, 현재 설계에서는 Q7을 간결성/효율성으로 두고 업무 완결성은 feature와 safety layer에서 다룬다.

---

## 4. 점수 구조

각 Q의 평가 결과는 아래 구조로 저장된다.

```json
{
  "qid": "q4",
  "name": "인용 근거 정확성",
  "probs": [0.05, 0.15, 0.60, 0.20],
  "argmax": 3,
  "expected_1_4": 2.95,
  "score_0_10": 6.5,
  "entropy": 1.0627,
  "source": "llm_judge",
  "reason": "대부분의 citation이 주장과 맞지만 일부 근거 연결이 약함",
  "error": ""
}
```

계산식은 다음과 같다.

```text
expected_1_4 = 1*p1 + 2*p2 + 3*p3 + 4*p4
score_0_10 = (expected_1_4 - 1) / 3 * 10
```

중요한 점은 Prometheus trigger가 `score_0_10`이 아니라 1~4 기준을 사용한다는 것이다.

현재 trigger 조건은 다음과 같다.

```text
expected_1_4 <= 2.0
또는
argmax <= 2
```

Q0에 safety cap이 적용된 경우에는 `final_q0_score_0_10`을 다시 1~4 범위로 환산해 2점 이하인지 확인한다.

```text
final_q0_1_4 = 1 + final_q0_score_0_10 / 10 * 3
```

---

## 5. LLM judge 동작 방식

현재 평가기는 설정에 따라 LLM judge 또는 rule fallback으로 동작한다.

| 상태 | 동작 |
| --- | --- |
| `CIVIL_LLM_RUBRIC_USE_LLM_JUDGE=true`이고 `generation_service.call_ollama` 사용 가능 | Q0~Q7에 대해 LLM judge 실행 |
| LLM judge 비활성화 또는 호출 불가 | rule fallback으로 Q별 확률 분포 생성 |
| LLM judge 호출 실패 | 해당 항목 또는 전체 평가가 fallback/error metadata로 기록 |

논문에서는 logprob 기반의 선택지 확률 분포를 사용하는 방향이 핵심이다. 그러나 현재 Ollama 호출에서는 안정적인 token logprob을 직접 받지 못하므로, 구현에서는 LLM이 반환한 `choice`와 `confidence`를 바탕으로 synthetic probability vector를 만든다.

예시는 다음과 같다.

```text
LLM 출력: choice=3, confidence=0.70
저장 분포: [0.10, 0.10, 0.70, 0.10]
```

따라서 현재 버전은 논문 구조를 반영하되, logprob 기반 확률 분포는 아직 완전 구현이 아니다. 이 부분은 향후 judge 모델 또는 inference API가 logprob을 안정적으로 제공할 때 교체할 수 있다.

---

## 6. Q2 reference-only 평가

Q2는 검색된 근거 자료가 민원 답변 작성에 충분한지를 보는 항목이다. 따라서 생성 답변을 입력하면 안 된다.

Q2 입력은 다음에 가깝다.

```text
[민원 원문]
{complaint_text}

[제공 근거 자료]
R1. ...
R2. ...
R3. ...
```

Q2에 생성 답변을 넣으면 "검색 품질"이 아니라 "답변 품질"을 같이 평가하게 되어 Q3~Q5와 의미가 겹친다. 현재 구현에서는 `reference_only=True`로 Q2를 분리한다.

---

## 7. rule_features

`rule_features`는 최종 점수를 직접 대체하지 않는다. LLM judge 결과를 보조하고, safety layer와 diagnostics의 근거로 사용한다.

대표 feature는 다음과 같다.

| feature | 목적 |
| --- | --- |
| `strict_citation_count` | 엄격히 검증된 citation 수 |
| `citation_count` | 응답에 포함된 citation 수 |
| `citation_coverage_rate` | 주요 주장 대비 citation 비율 |
| `citation_support_rate_strict` | citation이 실제 context와 맞는 비율 |
| `repetition_ratio` | 반복 문구 비율 |
| `template_ratio` | 템플릿성 문구 비율 |
| `debug_token_count` | 내부 메타데이터/디버그 토큰 노출 여부 |
| `answer_token_length` | 답변 길이 |
| `legal_anchor_count` | 법령/규정/근거 표현 수 |
| `procedure_anchor_count` | 신청, 접수, 보완, 처리 절차 표현 수 |
| `followup_anchor_count` | 후속 문의, 이의제기, 재신청 안내 표현 수 |
| `unsafe_promise_flag` | 권한 밖의 확정적 조치 약속 여부 |
| `emotional_response_flag` | 감정적 대응, 경고, 비난 표현 여부 |

---

## 8. manual_completeness_features

민원 답변 매뉴얼에서 요구하는 업무 완결성 요소는 Q7 점수에 직접 섞지 않고 별도 feature로 추출한다.

예상 구조는 다음과 같다.

```json
{
  "manual_completeness_features": {
    "complaint_issue_identified": true,
    "judgment_or_answer_present": true,
    "legal_basis_present": true,
    "procedure_guidance_present": true,
    "limitation_or_constraint_explained": false,
    "followup_guidance_present": true,
    "responsible_party_or_contact_present": false,
    "special_complaint_process_present": null
  }
}
```

| feature | 의미 |
| --- | --- |
| `complaint_issue_identified` | 민원 핵심 요구를 답변에 반영했는지 |
| `judgment_or_answer_present` | 가능/불가, 조치 여부, 검토 결과가 있는지 |
| `legal_basis_present` | 법령, 규정, 매뉴얼 근거가 제시됐는지 |
| `procedure_guidance_present` | 신청, 보완, 접수, 처리 절차가 안내됐는지 |
| `limitation_or_constraint_explained` | 처리 제한이나 어려운 사유를 설명했는지 |
| `followup_guidance_present` | 후속 문의, 이의제기, 재신청 안내가 있는지 |
| `responsible_party_or_contact_present` | 담당 부서, 기관, 연락처 안내가 필요한 경우 반영됐는지 |
| `special_complaint_process_present` | 반복 민원, 특이 민원, 언론/집단 민원 등 특별 절차가 필요한 경우 반영됐는지 |

---

## 9. safety layer

Q0~Q7만으로는 치명적 오류를 충분히 막기 어렵다. 따라서 현재 구현은 Q0 최종 점수에 safety cap을 적용한다.

개념은 다음과 같다.

```text
q0_raw_or_calibrated = Q0 기반 점수
q0_final = min(q0_raw_or_calibrated, safety_cap)
```

대표 cap 조건은 다음과 같다.

| 조건 | Q0 최종 상한 |
| --- | ---: |
| 빈 답변 또는 평가 불가 | 0.0 |
| 내부 JSON, 검색 로그, 시스템 메타데이터 노출 | 3.0 |
| 민원 요구와 반대되는 결론 | 3.5 |
| 권한 밖 직접 조치 확정 약속 | 4.0 |
| citation 전무 | 4.0 |
| 답변의 법령/규정 판단이 reference와 충돌 | 4.5 |
| 특이 민원에 감정적으로 대응 | 4.5 |
| 근거 없는 법적 처분/경고 표현 | 5.0 |
| 반복 민원 종결 안내에서 이의제기/절차 안내 누락 | 5.5 |
| strict citation은 없고 후처리 citation만 존재 | 6.5 |

API의 `quality_signals.civil_llm_rubric_q0`에는 safety cap이 반영된 `final_q0_score_0_10`이 들어간다.

---

## 10. Prometheus feedback 적용 방식

Prometheus는 공식 점수 산출기가 아니다. 현재 설계에서는 낮은 rubric 항목을 발견했을 때 재생성 방향을 제공하는 feedback 장치로 사용한다.

실행 조건은 다음과 같다.

| 조건 | 내용 |
| --- | --- |
| 기능 활성화 | `ENABLE_PROMETHEUS_RUBRIC_FEEDBACK=true` |
| 재생성 횟수 | `PROMETHEUS_RUBRIC_MAX_REGENERATION_ATTEMPTS=1` |
| trigger 기준 | `PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE=2.0` |
| 낮은 항목 존재 | Q별 `expected_1_4 <= 2.0` 또는 `argmax <= 2` |
| LLM 호출 가능 | `generation_service.call_ollama` 사용 가능 |
| 적용 경로 | 정상 RAG QA 경로 |

동작 방식은 다음과 같다.

```text
1. 초기 답변에 대해 Civil LLM-Rubric 평가
2. 1~4 기준 2점 이하 항목 탐지
3. Prometheus feedback prompt 생성
4. feedback, weakness, revision_hint 수신
5. feedback을 숨긴 채 답변 재생성 prompt 생성
6. 재생성 답변 validation
7. citation validation
8. 재생성 답변에 대해 LLM-Rubric 재평가
9. 최종 metadata에 feedback/revision 이력 저장
```

Prometheus feedback은 사용자에게 직접 노출되는 답변 본문에 들어가면 안 된다. 답변 재생성 prompt에도 다음 원칙이 들어간다.

```text
Do not mention Prometheus, rubric scores, evaluation, or internal diagnostics in the public answer.
Do not invent laws, departments, phone numbers, dates, or completed actions.
Use only the provided references and existing citations.
```

---

## 11. API 응답 metadata

최종 응답에는 다음 정보가 들어간다.

```json
{
  "generation_metadata": {
    "civil_llm_rubric": {
      "case_id": "civil_000001",
      "rubric_version": "civil_llm_rubric_q0_q7_v1.0",
      "judge_prompt_version": "judge_prompt_2026_06_18",
      "judge_status": "llm_judge",
      "probability_source": "llm_choice_confidence",
      "llm_rubric_raw": {
        "q0": {
          "probs": [0.05, 0.15, 0.60, 0.20],
          "argmax": 3,
          "expected_1_4": 2.95,
          "score_0_10": 6.5,
          "entropy": 1.0627
        }
      },
      "rule_features": {},
      "manual_completeness_features": {},
      "calibrated_prediction": {
        "available": false,
        "reason": "human calibration model is not trained yet"
      },
      "safety_layer": {
        "cap_applied": false,
        "cap_reason": null,
        "final_q0_score_0_10": 6.5
      },
      "score_summary": {},
      "diagnostics": {
        "main_failure_reasons": [],
        "recommended_fix": [],
        "human_review_required": false
      },
      "prometheus_feedback": {},
      "prometheus_revision": {}
    },
    "prometheus_revision": {
      "attempted": true,
      "applied": true,
      "attempt_count": 1,
      "trigger_threshold_1_4": 2.0,
      "initial_low_score_items": [],
      "initial_q0_final": 4.0,
      "final_q0_final": 7.0
    }
  },
  "quality_signals": {
    "civil_llm_rubric_q0": 7.0,
    "civil_llm_rubric_human_review_required": false,
    "civil_llm_rubric_judge_status": "llm_judge"
  }
}
```

`prometheus_feedback`와 `prometheus_revision`은 Prometheus가 실행되었을 때만 의미 있는 값이 들어간다. 실행되지 않으면 비어 있거나 존재하지 않을 수 있다.

---

## 12. calibration 상태

논문 LLM-Rubric의 중요한 요소는 사람 평가 데이터를 이용해 LLM judge 점수를 보정하는 calibration이다.

그러나 현재 프로젝트 구현에서는 아직 calibration model을 학습하지 않았다. 따라서 현재 상태는 다음과 같다.

```json
{
  "calibrated_prediction": {
    "available": false,
    "reason": "human calibration model is not trained yet"
  }
}
```

현재 최종 Q0는 다음 흐름으로 계산된다.

```text
Q0 raw expected score
-> 0~10 환산
-> safety layer cap 적용
-> final_q0_score_0_10
```

향후 calibration을 붙이면 아래처럼 변경할 수 있다.

```text
Q0~Q7 probability vectors
+ rule_features
+ manual_completeness_features
+ risk_flags
-> calibration model
-> calibrated Q0
-> safety layer cap
-> final Q0
```

권장 학습 순서는 다음과 같다.

| 단계 | 모델 | 이유 |
| --- | --- | --- |
| 1 | uncalibrated expected score | 현재 구현 baseline |
| 2 | ridge regression | 적은 데이터에서 안정적 |
| 3 | ordinal logistic regression | 1~4 ordinal label과 잘 맞음 |
| 4 | gradient boosting | rule feature와 상호작용 학습 가능 |
| 5 | small MLP | 논문 구조와 가장 유사하지만 데이터가 더 필요 |

---

## 13. 설정값

현재 설정값은 `app/core/config.py`에 정의되어 있다.

| 환경변수 | 기본값 | 의미 |
| --- | --- | --- |
| `ENABLE_CIVIL_LLM_RUBRIC` | `true` | QA 응답에 LLM-Rubric 평가를 붙일지 여부 |
| `CIVIL_LLM_RUBRIC_USE_LLM_JUDGE` | `true` | LLM judge 사용 여부 |
| `CIVIL_LLM_RUBRIC_VERSION` | `civil_llm_rubric_q0_q7_v1.0` | rubric 버전 |
| `CIVIL_LLM_RUBRIC_JUDGE_PROMPT_VERSION` | `judge_prompt_2026_06_18` | judge prompt 버전 |
| `CIVIL_LLM_RUBRIC_MAX_CONTEXTS` | `5` | judge와 feedback에 넣을 최대 context 수 |
| `CIVIL_LLM_RUBRIC_TEMPERATURE` | `0.0` | judge LLM temperature |
| `ENABLE_PROMETHEUS_RUBRIC_FEEDBACK` | `true` | Prometheus feedback/revision 사용 여부 |
| `PROMETHEUS_RUBRIC_TRIGGER_MAX_CHOICE` | `2.0` | Prometheus 실행 기준. 1~4 점수에서 2점 이하 |
| `PROMETHEUS_RUBRIC_MAX_REGENERATION_ATTEMPTS` | `1` | 재생성 최대 횟수 |
| `PROMETHEUS_RUBRIC_TEMPERATURE` | `0.0` | Prometheus feedback/revision LLM temperature |

---

## 14. 검증 테스트

현재 구현은 아래 테스트에서 확인한다.

| 테스트 | 확인 내용 |
| --- | --- |
| `app/tests/unit/test_civil_llm_rubric_runtime.py` | Q0~Q7 평가 구조, fallback, safety layer, 점수 구조 |
| `app/tests/unit/test_generation_week5_contract.py::test_qa_runs_prometheus_feedback_and_revises_low_score_answer` | 낮은 rubric 점수에서 Prometheus feedback 후 재생성되는지 |
| `app/tests/unit/test_qa_stream.py` | QA streaming 계약 유지 |
| `app/tests/integration/test_week6_search_to_qa_e2e_sample10.py` | 검색-생성-E2E 응답에 rubric metadata가 붙는지 |

최근 확인 기준:

```text
pytest app/tests/unit/test_generation_week5_contract.py::test_qa_runs_prometheus_feedback_and_revises_low_score_answer \
       app/tests/unit/test_civil_llm_rubric_runtime.py \
       app/tests/unit/test_qa_stream.py \
       app/tests/integration/test_week6_search_to_qa_e2e_sample10.py -q

결과: 6 passed
```

---

## 15. 현재 한계와 후속 작업

현재 구현은 서비스 적용이 가능한 1차 버전이지만, 논문 기반 LLM-Rubric 전체를 완전히 재현한 것은 아니다.

| 한계 | 설명 | 후속 작업 |
| --- | --- | --- |
| logprob 미사용 | Ollama 호출에서 안정적인 선택지 logprob을 받지 못해 `choice/confidence` 기반 synthetic probs 사용 | logprob 지원 judge API로 교체 |
| calibration 미구현 | 사람 평가 데이터가 없어 보정 모델이 없음 | Q0~Q7 사람 평가 데이터 수집 후 ridge/ordinal 모델 학습 |
| Prometheus는 rubric 자체 평가가 아님 | 낮은 항목에 대한 feedback/revision 장치일 뿐 rubric 점수의 객관성 검증기는 아님 | 사람 평가와 rubric 점수의 MAE, kappa, correlation 측정 |
| no-evidence fallback 재생성 제외 | 근거 부족 상태에서 재생성하면 hallucination 위험이 있음 | fallback 전용 안전 feedback 정책 별도 설계 |
| latency 증가 | 초기 Q0~Q7 평가, Prometheus feedback, 재생성, 재평가가 추가됨 | judge batch화 또는 rule-first gating 적용 |
| 문항 문구 encoding 점검 필요 | 일부 기존 코드/문서에서 한글 깨짐 흔적이 있음 | source 파일 UTF-8 정리 및 rubric 문항 한글 재검수 |

---

## 16. 권장 운영 기준

서비스 운영에서는 다음 기준을 우선 적용한다.

| 조건 | 처리 |
| --- | --- |
| `final_q0_score_0_10 < 5.0` | 사람 검토 권장 |
| `safety_layer.cap_applied=true` | 사람 검토 권장 |
| Q3 또는 Q4가 2점 이하 | citation/근거 검증 필요 |
| Q1이 2점 이하 | 문체 및 감정적 표현 검토 |
| Q6이 2점 이하 | 내부 메타데이터 노출, 반복 문구 제거 |
| Q7이 2점 이하 | 답변 길이와 정보 밀도 조정 |
| Prometheus 재생성 후에도 낮은 점수 유지 | 자동 재생성 반복 금지, 사람 검토 |

Prometheus 재생성은 최대 1회만 수행한다. 같은 답변을 반복 재생성하면 품질 개선보다 근거 왜곡이나 지연 시간이 커질 가능성이 높다.

---

## 17. 전체 요약

현재 LLM-Rubric은 다음 구조로 구현되어 있다.

```text
Civil LLM-Rubric
  - Q0~Q7 1~4 rubric 평가
  - Q별 probability vector, argmax, expected score 저장
  - 0~10 환산 점수 제공
  - rule_features와 manual_completeness_features 추출
  - calibration placeholder 유지
  - safety layer로 Q0 최종 점수 cap 적용
  - QA 응답 generation_metadata와 quality_signals에 첨부

Prometheus feedback
  - Q별 1~4 기준 2점 이하 항목이 있을 때만 실행
  - 공식 점수 산출기가 아니라 feedback/revision 장치
  - 정상 RAG 경로에서 최대 1회 답변 재생성
  - 재생성 답변을 다시 LLM-Rubric으로 평가
```

즉, 현재 구조는 "벤치마크 후처리 평가기"가 아니라 "서비스 답변 생성 직후 품질 평가 및 조건부 재생성 루프"다.

---

## 18. 참고 논문 및 자료

- LLM-Rubric: A Multidimensional, Calibrated Approach to Automated Evaluation of Natural Language Texts: https://arxiv.org/abs/2501.00274

- Prometheus: Inducing Fine-grained Evaluation Capability in Language Models: https://arxiv.org/abs/2310.08491
