# ARES-lite 기반 RAG 평가 고도화 적용 검토

## 1. 문서 목적

이 문서는 ARES 논문의 평가 관점을 현재 AI-Civil-Affairs-Systems에
어떻게 적용할지 정리한다.

ARES는 생성 답변 하나만 평가하는 루브릭이라기보다, RAG 파이프라인을
검색 근거, 생성 답변의 근거 충실성, 사용자 질의 대응성으로 나누어 평가하는
프레임워크다. 따라서 현재 프로젝트에서는 기존 LLM-Rubric을 대체하지 않고,
검색과 답변 생성 사이의 품질 신호를 보강하는 **ARES-lite 평가 레이어**로
적용하는 것이 적절하다.

참고 논문:

- ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems
- <https://arxiv.org/abs/2311.09476>

## 2. 적용 적합성 판단

현재 프로젝트에는 ARES-lite를 적용하기 좋은 기반이 이미 있다.

| 현재 자산 | ARES-lite 적용 포인트 |
| --- | --- |
| `/search` 응답 | 검색 context relevance 평가에 사용 |
| `/qa` 응답 | answer faithfulness와 answer relevance 평가에 사용 |
| `routing_trace` | topic, complexity, request segment 기반 slice 평가에 사용 |
| `citations` | 답변 문장과 검색 근거 연결성 평가에 사용 |
| LLM-Rubric Q0~Q7 | ARES 점수를 Q2, Q4, Q0/manual completeness/Q7 보조 신호로 연결 |
| Workbench | 담당자가 답변과 평가 피드백을 함께 검토하는 UI로 확장 |

결론적으로 ARES 전체 구현보다는 ARES-lite가 적합하다.

- 원 논문의 synthetic data 생성, judge fine-tuning, PPI 신뢰구간 계산은
  현재 졸업 프로젝트 범위에서는 무겁다.
- 현재 단계에서는 ARES의 세 평가 축을 규칙 기반 지표와 선택적 LLM judge로
  구현하는 것이 현실적이다.
- 사람 검토 데이터가 쌓이면 이후 ARES 원 논문 방식처럼 validation set과
  confidence interval 기반 평가로 확장할 수 있다.

## 3. ARES 핵심 개념과 프로젝트 매핑

| ARES 평가 축 | 원래 의미 | 민원 프로젝트 적용 |
| --- | --- | --- |
| Context Relevance | 검색된 passage가 query와 관련 있는가 | 검색된 유사 민원, 법령, 처리 사례가 시민 민원의 핵심 이슈와 관련 있는가 |
| Answer Faithfulness | 답변이 검색 passage에 충실한가 | 생성 답변의 조치, 일정, 담당 부서, 법령 언급이 검색 근거로 뒷받침되는가 |
| Answer Relevance | 답변이 사용자 질문에 답하는가 | 답변이 민원인의 요청, 불편, 위험 요소, 조치 요구에 직접 대응하는가 |

현재 LLM-Rubric과 연결하면 다음과 같다.

| ARES-lite 신호 | 연결되는 LLM-Rubric 항목 |
| --- | --- |
| Context Relevance | Q2 근거 충분성, retrieval 평가 |
| Answer Faithfulness | Q2 근거 충분성, Q4 인용 정확성, semantic risk flags |
| Answer Relevance | Q0 종합 품질, manual_completeness_features, Q7 답변 효율성 보조 신호 |

## 4. 목표 적용 구조

```text
[민원 입력]
    -> Analyzer / Router
    -> RetrievalService.search()
    -> GenerationService.generate_qa()
    -> ARES-lite Evaluator
       - Context Relevance
       - Answer Faithfulness
       - Answer Relevance
    -> LLM-Rubric Evaluator
    -> Evaluation Report / Workbench
```

ARES-lite는 운영 답변 생성을 막는 필수 게이트가 아니라, 초기에는 평가와
진단 레이어로 둔다. 충분히 검증되기 전까지 자동 반려나 자동 수정에 사용하지
않는다.

## 5. 평가 입력 스키마

기존 `/search`와 `/qa` 산출물을 묶어 다음 평가 입력으로 만든다.

```json
{
  "case_id": "CASE-001",
  "query": "도로가 파손되어 차량 통행이 위험하고 주변 불법 주차 때문에 보행자도 위험합니다.",
  "request_segments": [
    "도로 파손으로 인한 통행 위험",
    "불법 주정차로 인한 보행자 위험"
  ],
  "retrieved_contexts": [
    {
      "context_id": "CASE-100__chunk-0",
      "content": "도로 파손 보수 민원 처리 사례...",
      "source": "유사 민원",
      "rank": 1,
      "score": 0.87
    }
  ],
  "generated_answer": "생성된 민원 회신 본문",
  "citations": [
    {
      "doc_id": "CASE-100__chunk-0",
      "quote": "도로 파손 보수 민원 처리 사례..."
    }
  ],
  "routing_trace": {
    "topic_type": "traffic",
    "complexity_level": "high",
    "strategy_id": "..."
  }
}
```

주의:

- 프로젝트의 복잡도 값은 `low`, `medium`, `high`를 사용한다.
- `complex` 같은 별도 값은 사용하지 않는다.
- 기본 답변 평가 범위는 현재 LLM-Rubric과 동일하게 `generated_body`를 우선한다.

## 6. 세부 평가 설계

### 6.1 Context Relevance

질문:

> 검색된 context가 현재 민원의 핵심 이슈, 장소, 시설, 위험 요소, 담당 부서와
> 의미적으로 관련 있는가?

출력 예시:

```json
{
  "metric": "context_relevance",
  "score": 8.0,
  "label": "relevant",
  "context_id": "CASE-100__chunk-0",
  "reason": "도로 파손과 통행 위험이라는 핵심 이슈가 현재 민원과 직접 관련됨"
}
```

점수 기준:

| 점수 | 기준 |
| ---: | --- |
| 9~10 | 민원의 핵심 이슈와 직접 관련 있고 답변 근거로 사용 가능 |
| 7~8 | 주요 이슈와 관련 있으나 일부 세부 조건은 다름 |
| 5~6 | 넓은 주제는 같지만 구체성이 부족함 |
| 3~4 | 일부 키워드만 겹치고 실제 근거성은 약함 |
| 0~2 | 현재 민원과 거의 무관함 |

### 6.2 Answer Faithfulness

질문:

> 생성 답변의 사실 주장, 조치 내용, 처리 일정, 담당 부서, 법령 언급이
> 검색 context 또는 citation으로 뒷받침되는가?

출력 예시:

```json
{
  "metric": "answer_faithfulness",
  "score": 6.0,
  "label": "partially_grounded",
  "unsupported_claims": [
    {
      "sentence": "다음 주까지 보수 공사가 진행될 예정입니다.",
      "reason": "검색 근거에 구체적인 공사 일정이 없음"
    }
  ],
  "revision_hint": "확정 일정 대신 '현장 확인 후 처리 가능 여부를 안내드리겠습니다'로 수정"
}
```

특히 낮게 평가해야 할 표현:

| 표현 유형 | 위험 |
| --- | --- |
| 이미 완료되었습니다 | 근거 없는 처리 이력 단정 |
| 즉시 조치하겠습니다 | 권한과 일정 불명확 |
| 다음 주까지 처리됩니다 | 근거 없는 일정 단정 |
| 해당 법령에 따라 불가합니다 | 법령 citation 없으면 위험 |
| 담당 부서는 ○○과입니다 | 부서 라우팅 근거 필요 |

### 6.3 Answer Relevance

질문:

> 답변이 민원인의 핵심 요청, 불편 사항, 위험 요소, 조치 요구에 직접 대응하는가?

출력 예시:

```json
{
  "metric": "answer_relevance",
  "score": 7.0,
  "label": "mostly_relevant",
  "missing_points": [
    "불법 주정차로 인한 보행자 위험에 대한 조치 안내가 부족함"
  ],
  "revision_hint": "주차지원과 또는 교통행정과 검토 안내를 추가"
}
```

복합 민원에서는 `request_segments` 기준으로 어느 이슈가 빠졌는지를 반드시
기록한다.

## 7. 종합 출력 스키마

```json
{
  "case_id": "CASE-001",
  "ares_lite": {
    "overall_score": 7.1,
    "risk_level": "medium",
    "context_relevance": {
      "average_score": 8.0,
      "low_relevance_contexts": []
    },
    "answer_faithfulness": {
      "score": 6.0,
      "unsupported_claims": []
    },
    "answer_relevance": {
      "score": 7.0,
      "missing_segments": []
    },
    "recommended_revision": [
      "근거 없는 일정 단정 표현을 완화",
      "누락된 하위 민원 이슈에 대한 조치 안내 추가"
    ]
  }
}
```

권장 overall 계산 초안:

```text
overall_score =
  0.30 * context_relevance_average
+ 0.40 * answer_faithfulness
+ 0.30 * answer_relevance
```

민원 도메인에서는 근거 없는 행정 약속의 위험이 크므로
`answer_faithfulness`를 가장 높게 둔다.

## 8. 구현 모듈 제안

현재 프로젝트에는 `app/evaluation` 패키지가 존재한다. 여기에 ARES-lite
하위 패키지를 추가하는 방식이 자연스럽다.

```text
app/evaluation/
  ares_lite/
    __init__.py
    schemas.py
    prompts.py
    context_relevance_judge.py
    answer_faithfulness_judge.py
    answer_relevance_judge.py
    evaluator.py
    report_builder.py
```

초기 구현은 운영 API가 아니라 평가 스크립트에서 먼저 사용한다.

```text
scripts/
  evaluate_ares_lite_civil_replies.py
```

이후 Workbench 연동이 필요해지면 `/qa` 응답의 `quality_signals` 또는
`generation_metadata`에 요약 결과를 추가한다.

## 9. LLM-Rubric과의 관계

ARES-lite는 LLM-Rubric을 대체하지 않는다.

| 구분 | 역할 |
| --- | --- |
| LLM-Rubric | 최종 답변 품질을 Q0~Q7과 manual/safety feature로 평가 |
| ARES-lite | RAG 파이프라인의 검색 관련성, 근거 충실성, 답변 관련성을 별도 진단 |
| Prometheus-style feedback | LLM-Rubric 각 Q 항목의 자연어 피드백을 강화 |

초기에는 ARES-lite 결과를 다음 방식으로 연결한다.

- `answer_faithfulness` 낮음: Q2, Q4, semantic risk 검토 대상으로 표시
- `answer_relevance` 낮음: Q0 종합 품질 저하 및 `manual_completeness_features` 누락 원인으로 표시
- `context_relevance` 낮음: 검색 실패 또는 라우팅 실패로 분류

Q0 공식 점수에 바로 합산하지 않고, 별도 보조 지표로 보고한다. 사람 평가와
상관관계가 확인된 뒤 Q0 aggregation feature로 편입한다.

## 10. 평가와 수용 기준

### 10.1 초기 평가셋

- Week11 rand50 결과
- Q0 저점 사례
- 복합 민원 샘플 30~50건
- citation 오류 또는 `disposition_reversal` 사례

### 10.2 수용 기준

| 항목 | 목표 |
| --- | ---: |
| context relevance 저점 사례 탐지 precision | 0.80 이상 |
| unsupported claim 탐지 precision | 0.75 이상 |
| missing segment 탐지 precision | 0.75 이상 |
| Q0/manual completeness 저점 사유 설명 가능 비율 | 0.80 이상 |
| 평가 결과 JSON 파싱 성공률 | 0.98 이상 |

## 11. 단계별 적용 계획

1. **문서 및 스키마 확정**
   - ARES-lite 입력/출력 스키마 확정
   - LLM-Rubric 산출물과 연결 위치 결정

2. **오프라인 평가 스크립트 구현**
   - `parsed_answers.jsonl`, `raw_responses.jsonl`, 검색 context를 입력으로 사용
   - 세 평가 축 점수와 피드백 저장

3. **LLM-Rubric 리포트와 병합**
   - `rubric_report.json`에 `ares_lite_summary` 추가 검토
   - Q2/Q4/Q0/manual_completeness 저점 사유와 연결

4. **Workbench 표시**
   - 답변 옆에 근거 관련성, 근거 충실성, 답변 관련성 표시
   - 담당자 수정 제안 표시

5. **Human validation 확장**
   - 담당자 검토 결과와 ARES-lite 결과를 비교
   - 충분한 데이터가 쌓이면 학습형 judge 또는 PPI 방식 검토

## 12. 리스크와 완화

| 리스크 | 완화 |
| --- | --- |
| LLM judge 결과가 불안정함 | deterministic citation 지표와 함께 사용하고 seed/temperature를 낮춤 |
| 평가 비용 증가 | 오프라인 평가부터 시작하고 운영 API에는 요약 결과만 선택 적용 |
| ARES-lite와 LLM-Rubric 점수 충돌 | ARES-lite는 원인 진단, LLM-Rubric은 최종 점수로 역할 분리 |
| 근거 문서가 너무 길어 judge 입력 초과 | context top-k 제한, snippet 기반 평가, segment별 평가 |

## 13. 보고서용 요약 문장

본 프로젝트는 ARES의 RAG 평가 관점을 참고하여 검색 근거의 관련성,
생성 답변의 근거 충실성, 민원 요청에 대한 답변 관련성을 별도로 평가하는
ARES-lite 레이어를 설계한다. 이 레이어는 기존 LLM-Rubric을 대체하지 않고,
Q2 근거 충분성, Q4 인용 정확성, Q0/manual completeness 저점의 원인을 설명하는
보조 평가 신호로 사용한다.

초기 구현은 synthetic data 기반 judge fine-tuning과 PPI까지 포함하는
ARES 전체 구현이 아니라, 기존 `/search`, `/qa`, `routing_trace`,
`citations` 산출물을 활용한 오프라인 평가 스크립트로 시작한다. 이후 담당자
검토 데이터가 쌓이면 human validation set과 confidence interval 기반
평가로 확장한다.
