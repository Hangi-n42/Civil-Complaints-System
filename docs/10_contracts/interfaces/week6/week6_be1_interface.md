# Week 6 BE1 인터페이스 문서

문서 버전: v1.0-week6-draft  
작성일: 2026-04-10  
책임: BE1  
협업: BE2, BE3

---

## 1) 책임 범위

Week 6에서 BE1은 TopicAnalyzer와 ComplexityAnalyzer 출력을 단일 계약으로 통합하고, 복합 요청 분할 결과를 표준 키로 제공한다.

주요 작업:
1. `TopicAnalyzer.classify(text, category, entity_labels)` 구현
2. `ComplexityAnalyzer.analyze(text, topic_type)` 정렬
3. `AnalyzerOutput` 통합 출력 확정

---

## 2) 입력 계약

### 2.1 classify 입력
- `text: string` (required)
- `category: string | null` (optional)
- `entity_labels: string[] | null` (optional)

### 2.2 analyze 입력
- `text: string` (required)
- `topic_type: string` (required)

입력 유효성:
- text 비어있으면 `TOPIC_INPUT_EMPTY`
- topic_type 미정의면 `general` fallback

---

## 3) 출력 계약 (BE1 -> BE2/BE3)

### 3.1 TopicAnalysis

```json
{
  "topic_type": "welfare",
  "topic_confidence": 0.93
}
```

### 3.2 ComplexityAnalysis

```json
{
  "complexity_score": 0.81,
  "complexity_level": "high",
  "intent_count": 3,
  "constraint_count": 4,
  "entity_diversity": 3,
  "policy_reference_count": 1,
  "cross_sentence_dependency": true,
  "complexity_trace": {
    "intent_count": 3,
    "constraint_count": 4,
    "entity_diversity": 3,
    "policy_reference_count": 1,
    "cross_sentence_dependency": true
  }
}
```

### 3.3 Unified AnalyzerOutput

```json
{
  "topic_type": "welfare",
  "complexity_level": "high",
  "complexity_score": 0.81,
  "intent_count": 3,
  "constraint_count": 4,
  "entity_diversity": 3,
  "policy_reference_count": 1,
  "cross_sentence_dependency": true,
  "complexity_trace": {
    "intent_count": 3,
    "constraint_count": 4,
    "entity_diversity": 3,
    "policy_reference_count": 1,
    "cross_sentence_dependency": true
  },
  "request_segments": [
    "보수 지연",
    "관리비 이의제기"
  ],
  "length_bucket": "long",
  "is_multi": true
}
```

필수 5키:
- `topic_type`
- `complexity_level`
- `complexity_score`
- `complexity_trace`
- `request_segments`

---

## 4) 세그먼트 분할 계약

규칙:
- 출력은 반드시 문자열 배열
- 최소 길이 1 보장
- 각 segment는 trim 후 빈 문자열 금지
- 각 segment는 사용자가 실제로 요구한 독립 처리 요청 단위여야 한다.
- 문장 경계는 `COMPLEXITY_ANALYZER_USE_KSS=true`로 활성화되었거나 프로세스에 `kss`가 이미 로딩된 경우 `kss` 한국어 문장 분리기를 사용하고, 기본값은 지연을 줄이기 위해 regex fallback을 사용한다.
- 단, `kss`는 문장 경계 탐지만 담당하며 요청 단위 분리 판단은 BE1 의미 규칙이 담당한다.
- 접속사(`및`, `그리고`)나 쉼표만으로 분리하지 않는다.
- 분리된 각 segment는 원문에서 확인 가능한 요청 동사 또는 질의 의도를 포함해야 한다.
- 배경 설명, 피해 서술, 인사말, 행정기관의 예상 조치는 segment로 생성하지 않는다.
- 중복 segment와 다른 segment에 부분 포함되는 segment는 제거한다.
- `intent_count == len(request_segments)`이고 `is_multi == (len(request_segments) >= 2)`를 보장한다.
- segment 순서는 원문 등장 순서를 유지한다.
- `도로 보수와 불법주정차 단속을 요청합니다`처럼 서로 다른 대상/처리 행위가 공유 요청 동사를 쓰는 경우에는 독립 요청으로 분리할 수 있다.
- Multi-Agent Routing 활성화 여부는 `is_multi`만으로 확정하지 않고, 후속 단계에서 segment별 담당부서 다양성과 confidence를 함께 검토한다.

예시:
- 단일: `["도로와 인도, 가로등 및 보안등이 파손되어 통행이 위험하니 현장 점검 및 보수를 요청드립니다."]`
- 복합: `["포트홀 주변 임시 안전 조치를 해주시고", "도로 보수 일정도 알려주세요."]`

---

## 5) 로그/에러 계약

필수 로그 키:
- `request_id`
- `topic_type`
- `topic_confidence`
- `complexity_level`
- `complexity_score`
- `segment_count`
- `analyzer_latency_ms`

Week6 BE1 에러 코드:
- `TOPIC_INPUT_EMPTY` (400)
- `TOPIC_CLASSIFY_ERROR` (500)
- `COMPLEXITY_ANALYZE_ERROR` (500)
- `SEGMENT_BUILD_ERROR` (500)

---

## 6) 핸드오프

BE2로 전달:
- route_key 조합 검증용 AnalyzerOutput 샘플

BE3로 전달:
- generation 프롬프트 반영용 request_segments 샘플

완료 체크:
- 통합 출력이 매 요청 동일 스키마로 생성
- 필수 5키 누락 0건
