# Week 5 BE1 인터페이스 문서

문서 버전: v1.0-week5-draft  
작성일: 2026-04-10  
책임: BE1  
협업: BE2, BE3

---

## 1) 책임 범위

Week 5에서 BE1은 Router가 즉시 사용할 수 있는 complexity 기반 분석 출력 계약을 고정한다.

주요 작업:
1. `LengthAnalyzer.analyze(text)` 구현
2. `MultiRequestDetector.detect(text)` 1차 구현
3. BE2 라우터 연동용 analyzer output 어댑터 고정

---

## 2) 입력 계약

### 2.1 Analyzer 입력
- `text: string` (required, trim 후 빈 문자열 금지)
- `topic_type: string` (optional, 미지정 시 `general` 처리)

### 2.2 입력 검증 규칙
- 공백 제거 후 길이 1 미만이면 `ANALYZER_INPUT_EMPTY`
- 길이 8000 초과 시 `ANALYZER_INPUT_TOO_LONG` 경고 로그 기록

---

## 3) 출력 계약 (BE1 -> BE2/BE3)

### 3.1 AnalyzerOutput 표준

```json
{
  "topic_type": "welfare",
  "complexity_level": "high",
  "complexity_score": 0.81,
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

필수 필드:
- `topic_type`
- `complexity_level`
- `complexity_score`
- `complexity_trace`
- `request_segments`

보조 필드:
- `length_bucket`
- `is_multi`

### 3.2 값 범위 규칙
- `complexity_level in [low, medium, high]`
- `0.0 <= complexity_score <= 1.0`
- `request_segments.length >= 1`

---

## 4) 함수 시그니처 계약

```python
def build_analyzer_output(text: str, topic_type: str = "general") -> dict: ...

def analyze_length(text: str) -> dict: ...

def detect_multi_request(text: str) -> dict: ...
```

라우터 연동 규칙:
- BE2 호출 입력은 다음 3개로 고정한다.
  - `topic_type`
  - `complexity_level`
  - `complexity_score`

---

## 5) 에러/로그 계약

Week5 BE1 에러 코드:
- `ANALYZER_INPUT_EMPTY` (400)
- `ANALYZER_INPUT_INVALID` (400)
- `ANALYZER_INTERNAL_ERROR` (500)

필수 로그 키:
- `request_id`
- `topic_type`
- `complexity_level`
- `complexity_score`
- `segment_count`
- `analyzer_latency_ms`

---

## 6) 핸드오프

BE2로 전달:
- AnalyzerOutput 샘플 20건
- complexity 구간별 분포 리포트

BE3로 전달:
- `complexity_trace` 필드 정의서
- `request_segments` 생성 규칙

완료 체크:
- 동일 입력 재실행 시 complexity 결과 재현 가능
- 필수 키 누락 없이 Router 입력 생성
