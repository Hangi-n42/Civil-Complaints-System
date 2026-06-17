# Prometheus-style LLM-Rubric 강화 적용 검토

## 1. 문서 목적

이 문서는 Prometheus 논문의 평가 방식을 현재 프로젝트의 LLM-Rubric에
어떻게 적용할지 정리한다.

현재 프로젝트의 LLM-Rubric은 Q0~Q8 다차원 기준, 0.0~10.0 점수,
`generated_body` 평가 범위, 실제 `consultant_answer` 기준 참조 정렬,
semantic risk cap을 사용하는 deterministic proxy다.

Prometheus는 이 구조를 대체하는 용도가 아니라, 기존 LLM-Rubric을
**세분화된 피드백 평가자**로 강화하는 근거로 사용한다.

참고 논문:

- Prometheus: Inducing Fine-grained Evaluation Capability in Language Models
- <https://arxiv.org/abs/2310.08491>

## 2. 적용 적합성 판단

Prometheus는 현재 프로젝트에 잘 맞는다. 이유는 다음과 같다.

| Prometheus 핵심 | 현재 프로젝트 자산 | 적용 방식 |
| --- | --- | --- |
| customized score rubric | Q0~Q8 루브릭 | 각 Q 항목에 0~10점 기준과 피드백 기준을 명시 |
| reference material | `consultant_answer`, 검색 context, citation snippet | reference-aware 평가 입력으로 사용 |
| language feedback | 현재 reason 목록 | 자연어 피드백, 약점, 수정 제안으로 확장 |
| evaluator LLM | 현재 deterministic proxy 이후 단계 | 선택적 LLM judge로 항목별 피드백 생성 |

단, Prometheus 전체 모델 학습을 지금 구현하는 것은 범위가 크다.
MVP에서는 Prometheus-style prompt와 JSON 출력 스키마만 적용하고, 공식
점수는 기존 deterministic LLM-Rubric을 유지한다.

## 3. 적용 원칙

1. **기존 Q0~Q8을 유지한다.**
   - 평가 항목을 Prometheus 기준으로 갈아엎지 않는다.
   - Q0 가중 평균과 fatal cap 구조를 유지한다.

2. **Prometheus-style judge는 보조 피드백 계층이다.**
   - 공식 점수는 deterministic proxy가 산출한다.
   - LLM judge 점수는 사람 검증 전까지 advisory score로 둔다.

3. **reference-aware 평가를 강화한다.**
   - `consultant_answer`
   - `generated_body`
   - retrieved context
   - strict/repaired citation
   - semantic risk flag
   를 함께 judge 입력으로 사용한다.

4. **출력은 반드시 구조화 JSON으로 제한한다.**
   - 자유로운 장문 평가는 재현성이 낮다.
   - `score`, `feedback`, `strengths`, `weaknesses`, `revision_hint`,
     `risk_flags`를 고정 필드로 둔다.

5. **chain-of-thought는 저장하지 않는다.**
   - 필요한 것은 reasoning 원문이 아니라 담당자가 검토 가능한 평가 사유다.

## 4. 현재 LLM-Rubric과 Prometheus 역할 분리

| 구분 | 역할 |
| --- | --- |
| Deterministic LLM-Rubric | 공식 Q0~Q8 점수, cap 적용, 재현 가능한 지표 |
| Prometheus-style feedback | 항목별 자연어 평가 사유, 누락 이슈, 수정 제안 |
| ARES-lite | RAG 검색 관련성, 답변 근거 충실성, 답변 관련성 별도 진단 |
| Human validation | 향후 judge 점수와 피드백 품질 검증 |

초기 구현에서는 Prometheus-style feedback을 Q0 계산에 직접 넣지 않는다.
사람 평가 데이터로 상관관계가 확인된 뒤에만 calibration feature로 편입한다.

## 5. Q0~Q8 적용 방식

| ID | 현재 평가 항목 | Prometheus-style 강화 방향 |
| --- | --- | --- |
| Q0 | 종합 만족도 | Q1~Q8 결과와 cap 사유를 요약한 최종 피드백 생성 |
| Q1 | 생성 본문 품질 | 공공기관 문체, 내부 라벨, 이스케이프, 디버그 노출에 대한 자연어 피드백 |
| Q2 | 근거 충분성 | 핵심 주장별 근거 있음/부족/없음 설명 |
| Q3 | 인용 포함 | citation이 존재하는지뿐 아니라 답변에서 의미 있게 쓰였는지 설명 |
| Q4 | 인용 정확성 | citation ID, case, snippet이 답변 문장을 실제 지지하는지 설명 |
| Q5 | 최적 출처성 | 선택한 근거가 적절한지, 더 나은 근거가 누락됐는지 설명 |
| Q6 | 중복 없음 | 반복, 템플릿 남용, 구조 문자열 노출을 구체적으로 지적 |
| Q7 | 길이·밀도 | 짧음/장황함이 아니라 정보 밀도와 실질 본문 길이를 평가 |
| Q8 | 업무 완결성 | 민원 요지, 판단, 조치, 제약, 후속 안내, 복합 이슈 누락을 설명 |

## 6. 항목별 루브릭 예시

### Q8 업무 완결성

| 점수 | 기준 |
| ---: | --- |
| 9~10 | 민원 요지, 담당 주체, 처리 가능성, 조치 절차, 제약 사항, 추가 안내가 모두 구체적임 |
| 7~8 | 핵심 요지와 조치 방향은 충분하나 일부 절차나 제약 설명이 약함 |
| 5~6 | 기본 답변은 가능하지만 담당 부서, 처리 기준, 조치 절차 중 일부가 빠짐 |
| 3~4 | 일반 안내는 있으나 민원별 핵심 요구에 대한 직접 대응이 부족함 |
| 0~2 | 답변이 없거나 민원 내용과 거의 무관함 |

### Q2 근거 충분성

| 점수 | 기준 |
| ---: | --- |
| 9~10 | 핵심 주장 대부분이 검색 근거 또는 참조 답안과 잘 정렬됨 |
| 7~8 | 주요 방향은 근거와 일치하나 일부 세부 조치나 표현이 약함 |
| 5~6 | 근거가 일부 있으나 일정, 부서, 조치 가능성 등에서 불확실함 |
| 3~4 | 일반론 위주이며 검색 근거와의 연결이 약함 |
| 0~2 | 근거가 없거나 참조 답안과 충돌함 |

## 7. Prometheus-style 평가 입력

```json
{
  "case_id": "CASE-001",
  "metric_id": "Q8",
  "metric_name": "업무 완결성",
  "instruction": "민원 원문에 대한 공공기관 회신 답변을 평가하라.",
  "query": "도로가 파손되어 차량 통행이 위험하고 주변 불법 주차도 위험합니다.",
  "generated_body": "모델이 생성한 3번 검토 의견 본문",
  "reference_answer": "실제 consultant_answer의 실질 본문",
  "retrieved_contexts": [
    "검색된 유사 민원 또는 법령 snippet"
  ],
  "citations": [
    {
      "doc_id": "CASE-100__chunk-0",
      "quote": "..."
    }
  ],
  "deterministic_score": 6.0,
  "deterministic_reasons": [
    "reference_alignment_score=6.0",
    "semantic_risks=none"
  ],
  "score_rubric": "Q8 0~10점 판단 기준"
}
```

## 8. Prometheus-style 출력 스키마

`rubric_scores.jsonl`의 각 Q 항목에 다음 보조 필드를 추가하는 방식을 권장한다.

```json
{
  "case_id": "CASE-001",
  "rubric": {
    "Q8": {
      "score": 6.0,
      "label": "업무 완결성",
      "reasons": [
        "summary=True",
        "constraint=False"
      ],
      "prometheus_feedback": {
        "advisory_score": 6.0,
        "confidence": "medium",
        "feedback": "도로 파손 문제는 다루었으나 불법 주정차로 인한 보행자 위험 안내가 부족합니다.",
        "strengths": [
          "도로 파손 위험이라는 핵심 민원 요지를 반영함"
        ],
        "weaknesses": [
          "불법 주정차 관련 조치 안내가 부족함",
          "현장 확인 이후 절차가 구체적이지 않음"
        ],
        "revision_hint": "주차지원과 또는 교통행정과 검토 안내를 추가하고, 현장 확인 후 처리 가능 여부를 설명하는 문장을 보강합니다.",
        "risk_flags": []
      }
    }
  }
}
```

Q0에는 항목별 피드백을 종합한 `final_feedback`을 추가한다.

```json
{
  "Q0": {
    "score": 5.5,
    "reasons": [
      "weighted_proxy=7.10",
      "cap=5.5:unverified_current_fact"
    ],
    "prometheus_feedback": {
      "final_feedback": "형식은 갖췄지만 확인되지 않은 현재 상태를 단정해 최종 점수가 제한되었습니다.",
      "revision_priorities": [
        "확정 일정 표현 완화",
        "누락된 민원 이슈 보강",
        "citation 없는 조치 문장 삭제"
      ]
    }
  }
}
```

## 9. 목표 파이프라인

```text
[1] 기존 LLM-Rubric 실행
    - generated_body 추출
    - Q1~Q8 deterministic score
    - Q0 cap 적용

        +

[2] Prometheus-style feedback 실행
    - 항목별 customized score rubric
    - reference answer / retrieved context 입력
    - 항목별 feedback JSON 생성

        ↓

[3] 리포트 병합
    - rubric_scores.jsonl에 prometheus_feedback 추가
    - rubric_report.json에 feedback summary 추가
    - rubric_summary.md에 주요 개선 제안 요약
```

## 10. 구현 모듈 제안

기존 평가 코드와 분리해 선택 실행 가능하게 만든다.

```text
app/evaluation/
  prometheus_rubric/
    __init__.py
    schemas.py
    prompts.py
    judge.py
    feedback_merger.py
    report_builder.py

scripts/
  evaluate_llm_rubric_prometheus_feedback.py
```

초기에는 다음처럼 별도 스크립트로 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_llm_rubric_prometheus_feedback.py `
  --rubric-scores logs\evaluation\...\rubric_scores.jsonl `
  --answers logs\evaluation\...\parsed_answers.jsonl `
  --reference-data data\processed\processed_consulting_data.json `
  --output-dir logs\evaluation\...\prometheus_feedback
```

이후 안정화되면 기존 `evaluate_llm_rubric_civil_replies.py`에
`--with-prometheus-feedback` 옵션으로 붙일 수 있다.

## 11. 현재 프로젝트에서 수정해야 할 설계 포인트

기존 Prometheus 적용 초안에서 다음 부분은 조정이 필요하다.

| 기존 초안 표현 | 수정 방향 |
| --- | --- |
| Prometheus로 Q1~Q8 독립 judge를 만든다 | 공식 점수는 deterministic 유지, judge는 feedback/advisory로 시작 |
| `rubric_scores.jsonl` 구조를 완전히 새 scores 구조로 변경 | 기존 `rubric[QID]` 구조 안에 `prometheus_feedback` 추가 |
| Prometheus식 점수를 바로 Q0에 반영 | 사람 평가 검증 전까지 Q0에는 미반영 |
| LLM judge가 citation 정확성을 직접 판정 | Q3/Q4의 deterministic citation 지표를 우선하고, LLM은 설명 보조 |
| 자유 형식 피드백 생성 | 고정 JSON schema와 낮은 temperature 사용 |

## 12. 평가와 수용 기준

### 12.1 초기 수용 기준

| 항목 | 목표 |
| --- | ---: |
| feedback JSON 파싱 성공률 | 0.98 이상 |
| Q0 cap 사유 설명 포함률 | 0.95 이상 |
| Q8 저점 케이스의 누락 이슈 설명 precision | 0.75 이상 |
| unsupported claim 지적 precision | 0.75 이상 |
| 담당자 수정에 바로 쓸 수 있는 revision hint 비율 | 0.80 이상 |

### 12.2 비교 대상

- 기존 deterministic LLM-Rubric only
- deterministic LLM-Rubric + Prometheus-style feedback
- Direct LLM judge 단독

비교 기준은 공식 점수 정확도보다 피드백 유용성을 우선한다.

## 13. 리스크와 완화

| 리스크 | 완화 |
| --- | --- |
| LLM judge가 점수를 흔들 수 있음 | advisory score로만 두고 공식 Q0에는 미반영 |
| 피드백이 장황해짐 | JSON 필드별 길이 제한과 bullet 수 제한 |
| citation을 잘못 해석함 | deterministic citation 지표를 우선하고 LLM은 설명만 담당 |
| 비용과 지연 증가 | 오프라인 평가에서 시작, 운영 UI에는 필요 시만 실행 |
| reference answer를 정답처럼 과신 | reference는 기준 자료일 뿐 완전 정답이 아님을 prompt에 명시 |

## 14. 보고서용 요약 문장

본 프로젝트는 Prometheus의 fine-grained rubric-based evaluation 방식을
참고하여 기존 LLM-Rubric을 강화한다. Prometheus는 사용자가 제공한
customized score rubric과 reference material을 바탕으로 긴 생성 답변을
세밀하게 평가하고, 점수뿐 아니라 자연어 피드백을 생성하는 evaluator LLM
구조를 제안한다.

본 시스템에서는 이를 민원 회신 평가에 맞게 적용하여 Q1~Q8별 세부 점수
기준을 명시하고, `consultant_answer`, 검색 context, citation snippet을
reference material로 활용한다. 기존 deterministic proxy의 공식 점수와
치명적 오류 상한 규칙은 유지하되, Prometheus-style feedback을 추가하여
항목별 평가 사유, 근거 부족 문장, 누락된 민원 이슈, 수정 제안을 구조화된
JSON으로 출력한다.

따라서 Prometheus는 현재 LLM-Rubric을 대체하는 평가기가 아니라,
점수 중심 평가를 담당자가 실제로 수정에 활용할 수 있는 피드백 기반 평가
체계로 확장하는 보강 계층이다.
