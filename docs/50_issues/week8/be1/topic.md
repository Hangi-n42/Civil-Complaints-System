# TopicAnalyzer 설계 문서

> **대상 브랜치**: `feature/TopicAnalyzer-fix`
> **관련 파일**: `app/api/routers/retrieval.py:122`, `app/retrieval/analyzers/complexity_analyzer.py`
> **작성일**: 2026-05-07

---

## 1. 현황 분석

### 1.1 현재 구현

```python
# app/api/routers/retrieval.py:122
def _detect_topic_type(query: str) -> str:
    query_lower = query.lower()
    topic_keywords = {
        "welfare":      ["복지", "급여", "기초생활", "수급", "임대주택"],
        "traffic":      ["도로", "교통", "신호", "불법주정차", "가로등"],
        "environment":  ["환경", "소음", "악취", "미세먼지", "폐기물"],
        "construction": ["공사", "건축", "안전", "보수", "시설"],
    }
    for topic, keywords in topic_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            return topic
    return "general"
```

### 1.2 아키텍처 내 역할

```
Query
  └─► _detect_topic_type()          ← 현재 위치 (라우터 private 함수)
         │ topic_type
         ▼
      build_analyzer_output()        ← complexity_analyzer.py
         │ topic_type + complexity_level + complexity_score
         ▼
      route_adaptive()               ← adaptive_router.py
         │ retrieval_policy (admin_policy / field_ops / general)
         ▼
      RetrievalService
```

`topic_type`은 라우팅 정책(`retrieval_policy`) 결정의 1차 입력이므로,
오분류 시 검색 전략 전체가 틀어지는 고위험 컴포넌트다.

---

## 2. 문제점 상세

### 2.1 아키텍처: 라우터 내 private 함수로 매몰

- `_detect_topic_type`은 `app/api/routers/retrieval.py` 내부에 위치해 단독 import/호출 불가.
- 단위 테스트 작성 시 라우터 전체를 mock해야 하며, 테스트 대상에서 사실상 제외됨.
- `ComplexityAnalyzer`처럼 독립 클래스+파일로 분리되지 않아 교체·확장이 어렵다.
- `complexity_analyzer.py`가 `topic_type`을 매개변수로 받아 사용하는 구조이므로,
  주제 분류 로직이 두 모듈에 걸쳐 암묵적으로 결합되어 있다.

### 2.2 First-match 편향

Python 3.7+ dict는 삽입 순서를 보장한다. 현재 순서: `welfare → traffic → environment → construction`.

```
쿼리: "복지시설 건축 허가 민원"
 → "복지" 매칭 → topic="welfare"  ← 실제 의도: construction
```

첫 번째로 매칭된 카테고리가 무조건 선택되어, 복합 맥락 쿼리에서 오분류 발생.

### 2.3 키워드 희소성 (카테고리당 5개, 총 25개)

| 카테고리 | 현재 키워드 | 누락 주요 키워드 예시 |
|---|---|---|
| welfare | 복지, 급여, 기초생활, 수급, 임대주택 | 노인, 장애인, 보조금, 지원금, 돌봄, 아동, 청소년, 의료급여, 생계비 |
| traffic | 도로, 교통, 신호, 불법주정차, 가로등 | 주차, 횡단보도, 과속, 속도위반, 버스, 자전거도로, 노면 |
| environment | 환경, 소음, 악취, 미세먼지, 폐기물 | 쓰레기, 폐수, 수질, 대기, 분진, 진동, 토양오염, 수해 |
| construction | 공사, 건축, 안전, 보수, 시설 | 철거, 토목, 도시계획, 용도변경, 인허가, 착공, 준공 |

분류 가능 어휘가 한국어 행정 민원 도메인 전체의 극히 일부만 커버.

### 2.4 문자열 부분 일치의 false positive

```
"안전" → construction  ← "안전교육", "안전벨트", "안전핀" 등과 구분 불가
"시설" → construction  ← "복지시설", "의료시설" 등 welfare 문맥에서도 매칭
"환경부" → environment ← 정부 기관명이 토픽을 오염
"교통공단" → traffic   ← 기관명 포함 시 오분류
```

단순 substring 매칭이므로 단어 경계나 맥락을 전혀 고려하지 않음.

### 2.5 한국어 띄어쓰기 변형 미처리

```
"기초생활"  → 매칭 O
"기초 생활" → 매칭 X  (공백이 포함된 사용자 입력)

"불법주정차"  → 매칭 O
"불법 주정차" → 매칭 X
```

`query.lower()`만 적용하고 띄어쓰기 정규화를 하지 않아 동일 의미 표현에서 누락 발생.

### 2.6 복합 주제(multi-topic) 쿼리 지원 없음

```
"도로변 건축 공사 소음 피해 민원"
 → 주제: traffic + construction + environment 혼재
 → 현재: "traffic" 단일 반환 (도로 첫 매칭)
```

단일 `str` 반환이라 복합 주제 정보가 소실되며, 라우터도 이를 활용할 수 없음.

### 2.7 신뢰도(confidence) 없음

- 키워드 1개 매칭 vs 8개 매칭이 동일하게 단일 토픽으로 반환됨.
- "general" 반환이 "아무것도 매칭 안 됨"인지 "낮은 신뢰도 일반"인지 구별 불가.
- 라우터가 신뢰도를 활용해 routing 파라미터를 보수적으로 설정하는 것이 불가능.

---

## 3. 고도화 방향

### 방향 A — 즉시 적용 가능: 독립 클래스 분리 + 점수 기반 분류

**원칙**: 현재 키워드 방식을 유지하되, 클래스 분리 + 스코어 집계로 품질 개선.

#### 3.A-1 클래스 분리

```python
# app/retrieval/analyzers/topic_analyzer.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

TopicType = Literal["welfare", "traffic", "environment", "construction", "general"]

CONFIDENCE_AMBIGUITY_MARGIN = 0.15  # top-1과 top-2 점수 차이가 이 이하면 ambiguous

@dataclass(frozen=True)
class TopicAnalysis:
    topic_type: TopicType
    confidence: float            # 0.0–1.0, 정규화된 최고 점수
    all_scores: dict[str, float] # 전체 카테고리별 원점수
    matched_keywords: list[str]  # 실제로 매칭된 키워드
    is_ambiguous: bool           # top-2 간 점수 차이 < CONFIDENCE_AMBIGUITY_MARGIN
    secondary_topic: TopicType | None  # ambiguous 시 2위 토픽

class TopicAnalyzer:
    def __init__(self, keyword_map: dict[str, list[tuple[str, float]]] | None = None):
        self._keyword_map = keyword_map or _DEFAULT_KEYWORD_MAP

    def analyze(self, text: str) -> TopicAnalysis: ...
    def detect(self, text: str) -> TopicType:
        return self.analyze(text).topic_type
```

#### 3.A-2 점수 기반 집계

```python
def analyze(self, text: str) -> TopicAnalysis:
    normalized = _normalize_text(text)   # 소문자 + 공백 제거
    scores: dict[str, float] = {}
    matched: list[str] = []

    for topic, weighted_keywords in self._keyword_map.items():
        topic_score = 0.0
        for keyword, weight in weighted_keywords:
            kw_norm = keyword.replace(" ", "")
            if kw_norm in normalized:
                topic_score += weight
                matched.append(keyword)
        scores[topic] = topic_score

    return _build_topic_analysis(scores, matched)
```

각 키워드에 가중치를 부여해, 고유성 높은 키워드(예: `미세먼지`, `폐기물`)에 가중치 증가.

#### 3.A-3 키워드 대폭 확장 (초안)

```python
_DEFAULT_KEYWORD_MAP: dict[str, list[tuple[str, float]]] = {
    "welfare": [
        ("복지", 1.0), ("급여", 1.2), ("기초생활", 1.5), ("수급", 1.3), ("임대주택", 1.3),
        ("노인", 1.0), ("장애인", 1.2), ("보조금", 1.1), ("지원금", 1.0), ("돌봄", 1.1),
        ("아동", 0.9), ("청소년", 0.9), ("의료급여", 1.4), ("생계비", 1.3), ("저소득", 1.2),
        ("긴급복지", 1.5), ("주거급여", 1.4), ("차상위", 1.3), ("자활", 1.1), ("사회보험", 1.0),
    ],
    "traffic": [
        ("도로", 0.9), ("교통", 0.9), ("신호", 1.1), ("불법주정차", 1.5), ("가로등", 1.2),
        ("주차", 1.0), ("횡단보도", 1.3), ("과속", 1.2), ("속도위반", 1.3), ("버스노선", 1.4),
        ("자전거도로", 1.3), ("노면", 1.1), ("포트홀", 1.5), ("차선", 1.1), ("교차로", 1.1),
        ("보행자", 0.9), ("통행", 0.8), ("도로파손", 1.4), ("교통사고", 1.3), ("불법유턴", 1.4),
    ],
    "environment": [
        ("환경", 0.8), ("소음", 1.2), ("악취", 1.4), ("미세먼지", 1.5), ("폐기물", 1.4),
        ("쓰레기", 1.1), ("폐수", 1.5), ("수질", 1.3), ("대기오염", 1.4), ("분진", 1.3),
        ("진동", 1.1), ("토양오염", 1.5), ("수해", 1.0), ("불법투기", 1.4), ("매연", 1.3),
        ("음식물쓰레기", 1.3), ("재활용", 0.9), ("하수", 1.1), ("오염", 1.0), ("방역", 1.0),
    ],
    "construction": [
        ("공사", 1.1), ("건축", 1.1), ("안전", 0.7), ("보수", 1.0), ("시설", 0.7),
        ("철거", 1.4), ("토목", 1.3), ("도시계획", 1.3), ("용도변경", 1.4), ("인허가", 1.4),
        ("착공", 1.4), ("준공", 1.4), ("리모델링", 1.3), ("증개축", 1.5), ("비계", 1.5),
        ("굴착", 1.4), ("터파기", 1.5), ("건설현장", 1.3), ("지하공사", 1.4), ("도로공사", 1.3),
    ],
}
```

#### 3.A-4 false positive 방지: 기관명 필터

```python
_NEGATIVE_PATTERNS: list[str] = [
    "환경부", "환경공단", "교통공단", "교통안전공단",
    "건설교통부", "안전처", "재난안전",
]

def _normalize_text(text: str) -> str:
    cleaned = str(text or "").strip()
    for pattern in _NEGATIVE_PATTERNS:
        cleaned = cleaned.replace(pattern, "")  # 기관명 제거 후 분류
    return cleaned.lower().replace(" ", "")
```

#### 3.A-5 신뢰도 및 모호성 판단

```python
def _build_topic_analysis(
    scores: dict[str, float], matched: list[str]
) -> TopicAnalysis:
    if not any(v > 0 for v in scores.values()):
        return TopicAnalysis(
            topic_type="general", confidence=0.0,
            all_scores=scores, matched_keywords=[],
            is_ambiguous=False, secondary_topic=None,
        )

    sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_topic, top_score = sorted_topics[0]
    second_topic, second_score = sorted_topics[1]

    total = sum(scores.values())
    confidence = round(top_score / total, 3) if total > 0 else 0.0
    is_ambiguous = (top_score - second_score) < CONFIDENCE_AMBIGUITY_MARGIN * top_score

    # confidence 하한치 미달 시 general 강등
    if confidence < 0.35:
        top_topic = "general"

    return TopicAnalysis(
        topic_type=top_topic,  # type: ignore[arg-type]
        confidence=confidence,
        all_scores=scores,
        matched_keywords=matched,
        is_ambiguous=is_ambiguous,
        secondary_topic=second_topic if is_ambiguous else None,  # type: ignore[arg-type]
    )
```

---

### 방향 B — 중기: 임베딩 기반 주제 분류 (토픽 센트로이드 유사도)

기존 `app/retrieval/embeddings/` 인프라를 재사용해 벡터 유사도로 분류.

```
사전 준비:
  각 토픽 대표 문장(20개) → embedding → 평균 벡터 = topic centroid

실시간 분류:
  query → embedding → cosine similarity to each centroid → argmax
```

**장점**: 키워드에 없는 표현도 의미적으로 가까우면 분류 가능, 변형(오타·약어)에 강인.

**단점**: 임베딩 모델 호출 레이턴시 추가 (현재 파이프라인에 이미 embedding 단계가 있으므로 캐시 활용 여부 검토 필요).

**권장 조건**:
- 키워드 기반 confidence < 0.4 인 경우에만 임베딩 분류로 fallback (hybrid 방식)
- 토픽 센트로이드를 startup 시점에 한 번만 계산해 메모리에 캐시

```python
class EmbeddingTopicClassifier:
    def __init__(self, embedder, centroids: dict[str, list[float]]):
        self._embedder = embedder
        self._centroids = centroids  # 사전 계산된 centroid 벡터

    def classify(self, text: str) -> tuple[TopicType, float]:
        query_vec = self._embedder.embed(text)
        similarities = {
            topic: cosine_similarity(query_vec, centroid)
            for topic, centroid in self._centroids.items()
        }
        best = max(similarities, key=similarities.get)
        return best, similarities[best]
```

---

### 방향 C — 장기: LLM 기반 분류 (오프라인 배치 또는 저빈도 경로)

Claude API를 통한 structured output 분류. 실시간 경로보다 민원 데이터 레이블링,
평가셋 구축, 키워드 사전 자동 확장 등 **오프라인 워크플로우**에 적합.

```python
# 오프라인 레이블링 예시
response = client.messages.create(
    model="claude-sonnet-4-6",
    system="민원 쿼리를 welfare/traffic/environment/construction/general 중 하나로 분류하라.",
    messages=[{"role": "user", "content": query}],
)
```

실시간 API 경로에는 레이턴시(~500ms+)와 비용 문제로 부적합.

---

## 4. 권장 설계안

### 4.1 파일 구조

```
app/retrieval/analyzers/
├── __init__.py
├── complexity_analyzer.py    # 기존 유지
└── topic_analyzer.py         # 신규 (독립 클래스)
```

`_detect_topic_type` 함수는 `retrieval.py`에서 제거하고, 라우터에서 `TopicAnalyzer` 인스턴스를 직접 사용.

### 4.2 공개 인터페이스

```python
# app/retrieval/analyzers/topic_analyzer.py

TopicType = Literal["welfare", "traffic", "environment", "construction", "general"]

@dataclass(frozen=True)
class TopicAnalysis:
    topic_type: TopicType
    confidence: float
    all_scores: dict[str, float]
    matched_keywords: list[str]
    is_ambiguous: bool
    secondary_topic: TopicType | None

class TopicAnalyzer:
    def analyze(self, text: str) -> TopicAnalysis: ...
    def detect(self, text: str) -> TopicType: ...

# 모듈 레벨 편의 함수 (복잡도 분석기와 패턴 통일)
def analyze(text: str) -> TopicAnalysis: ...
def detect(text: str) -> TopicType: ...

_DEFAULT_ANALYZER = TopicAnalyzer()
```

### 4.3 라우터 연동 변경 지점

```python
# app/api/routers/retrieval.py — Before
topic_type = _detect_topic_type(query)

# After
from app.retrieval.analyzers.topic_analyzer import detect as detect_topic
topic_type = detect_topic(query)
```

### 4.4 단계별 적용 로드맵

| 단계 | 내용 | 우선순위 |
|---|---|---|
| P0 | 독립 클래스 분리 + 기존 키워드 동등 이식 | 이번 주 |
| P1 | 키워드 확장 + 가중치 + 기관명 필터 | 다음 주 |
| P2 | `TopicAnalysis.confidence`, `is_ambiguous` 라우터 연동 | week9 |
| P3 | 임베딩 fallback (confidence < 0.4) | week10+ |

---

## 5. 테스트 전략

### 5.1 단위 테스트 (분리 후 즉시 작성 가능)

```python
# tests/retrieval/analyzers/test_topic_analyzer.py

@pytest.mark.parametrize("query,expected", [
    ("기초생활수급자 신청 방법", "welfare"),
    ("불법주정차 신고하고 싶어요", "traffic"),
    ("공사 현장 소음 민원", "construction"),   # first-match 편향 검증
    ("복지시설 건축 허가", "construction"),     # 현재 버전 오분류 → 수정 검증
    ("환경부 홈페이지 주소", "general"),        # 기관명 false positive 검증
    ("", "general"),                           # 빈 문자열 예외
    ("안녕하세요", "general"),                  # 키워드 없음
])
def test_detect(query, expected):
    assert detect(query) == expected

def test_confidence_ambiguous():
    result = analyze("도로변 공사 소음")
    assert result.is_ambiguous or result.confidence < 0.7  # 복합 주제
```

### 5.2 회귀 방지

`_detect_topic_type` → `TopicAnalyzer.detect` 전환 후, 기존 동작과의 diff를 
실제 민원 데이터 100건으로 검증해 오분류율 변화를 측정한다.

---

## 6. 결정이 필요한 사항

| 번호 | 질문 | 옵션 |
|---|---|---|
| Q1 | `secondary_topic` 정보를 라우터가 사용할 것인가? | 사용 (routing params 보수적 조정)|
| Q2 | confidence < 0.35 시 "general" 강등 임계값 합의 | 0.40 |
| Q3 | 기관명 필터 목록 관리 방식 |부산시 기관만 할것이므로 크롤링 or 하드코딩 추후 결정 |
| Q4 | 임베딩 fallback을 week9에 포함할 것인가? | 포함 |
