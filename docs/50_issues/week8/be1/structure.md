# 하이브리드 구조화 서비스 설계안

문서 버전: v1.0  
작성일: 2026-05-07  
대상 파일: `app/structuring/service.py`

---

## 1. 설계 목적

기존 구조화 서비스는 4요소(observation/result/request/context) 추출을 단어 점수 기반 휴리스틱으로 수행한다. 이 방식은 민원 표현의 다양성을 수용하지 못하고, 키워드 룰이 비대해지면서 유지보수 비용이 높다.

하이브리드 설계는 다음 두 역할을 분리한다.

- **Rule-based**: 정규식으로 확실하게 추출 가능한 객관적 명사(주소·시간·시설)만 담당
- **LLM**: 문맥 이해가 필요한 추상적 4요소(상황·결과·요구·배경) 담당

결과를 병합하고 기존 `validate_schema()`로 최종 검증한다.

---

## 2. 전체 파이프라인 구조

```
Raw Record
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 1: Rule-based Entity Extractor                    │
│  - ADMIN_UNIT: 광역시·도·구 정규식                       │
│  - TIME: 날짜·시간 정규식                               │
│  - FACILITY: 시설 키워드 목록                           │
│  - HAZARD: 위험 키워드 목록                             │
│  → entities[] (confidence = 1.0)                        │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 2: LLM Semantic Extractor                         │
│  - Ollama EXAONE 3.0 7.8B-Instruct                     │
│  - format="json" + Pydantic 검증                        │
│  - 재시도: temperature 조정 1회                         │
│  → FourElementsLLMOutput (observation/result/            │
│                            request/context)              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Stage 3: Result Merger & Validator                       │
│  - LLM 4요소 → evidence_span 탐색                       │
│  - confidence 산정 (LLM: 0.70~0.90, Rule: 1.0)         │
│  - validate_schema() 최종 검증                          │
│  → Unified Structured Record                            │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Stage 1: Rule-based Entity Extractor

### 3.1 기존 코드 정리 방침

**제거 대상** — 아래 속성·메서드는 Stage 2(LLM)가 담당하므로 삭제한다.

| 제거 대상 | 이유 |
|---|---|
| `_observation_keywords`, `_request_keywords`, `_context_keywords`, `_result_keywords` | 4요소 추출을 LLM에 위임 |
| `_score_candidate()`, `_pick_best()`, `_score_to_confidence()` | 휴리스틱 점수 로직 전체 제거 |
| `_observation_pattern`, `_request_pattern`, `_answer_like_pattern` | 문장 분류 패턴 제거 |
| `_split_segments()`, `_sentence_candidates()` | Q/A 분리 및 문장 후보 생성 제거 |
| `extract_four_elements()` | LLM 전담으로 교체 |

**유지 대상** — 객관적 명사 추출 로직만 남긴다.

| 유지 대상 | 이유 |
|---|---|
| `_admin_unit_pattern`, `_is_plausible_admin_unit()` | 행정단위 정규식, 정확도 높음 |
| `_time_pattern`, `_season_time_keywords` | 날짜·시간 추출 |
| `_facility_keywords`, `_hazard_keywords` | 시설·위험 키워드 목록 |
| `_normalize_entity_label()`, `_sanitize_entities()` | 레이블 정규화 |
| `_normalize_required()`, `_normalize_created_at()` | 입력 정규화 |
| `_build_field()`, `_build_result_field()` | 필드 객체 생성 |

### 3.2 LOCATION 추출 개선

현재 LOCATION 추출은 6개 고정 지명만 체크한다(`서울`, `경기`, `안양` 등). 이를 패턴 기반으로 확장한다.

```python
# 신규 추가 패턴
self._location_pattern = re.compile(
    r"[가-힣]{2,5}(?:동|읍|면|리|가|로|길|대로|번길)\b"
    r"|[가-힣]{1,3}(?:구|군)\s*[가-힣]{1,5}(?:동|읍|면|리)"
)
```

`extract_entities()` 내에서 `_admin_unit_pattern` 매칭 후 LOCATION_pattern으로 동(洞)·로(路)·길 수준 위치명을 추가 추출한다. ADMIN_UNIT과 중복되지 않도록 `seen` 집합으로 필터링한다.

### 3.3 Stage 1 출력 스키마

```python
@dataclass
class RuleBasedNERResult:
    entities: List[Dict[str, str]]   # [{"label": "ADMIN_UNIT", "text": "..."}]
    extraction_latency_ms: int
```

모든 Rule-based 엔티티는 `confidence = 1.0`으로 Merger에서 부여한다.

---

## 4. Stage 2: LLM Semantic Extractor

### 4.1 신규 파일 구조

```
app/structuring/
  llm_extractor.py          ← 신규: LLMSemanticExtractor 클래스
  schemas.py                ← 신규: Pydantic 모델 정의
  service.py                ← 기존: 정리 후 Orchestrator 역할
```

### 4.2 Pydantic 출력 스키마 (`schemas.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional

class FourElementsLLMOutput(BaseModel):
    observation: Optional[str] = Field(
        None,
        description="민원인이 겪은 문제 상황 또는 관찰한 사실"
    )
    result: Optional[str] = Field(
        None,
        description="문제로 인해 발생한 현재의 결과나 피해"
    )
    request: Optional[str] = Field(
        None,
        description="민원인이 행정기관에 요구하는 구체적 조치"
    )
    context: Optional[str] = Field(
        None,
        description="문제 발생 배경 또는 부가 설명"
    )
```

### 4.3 LLMSemanticExtractor 클래스 (`llm_extractor.py`)

#### 4.3.1 Ollama 호출 방식

`generation/service.py`의 `call_ollama()` 패턴을 재사용한다. 핵심 파라미터:

```python
payload = {
    "model": settings.STRUCTURING_MODEL,  # 신규 config 키 (기본값: "exaone3:7.8b-instruct")
    "prompt": prompt,
    "stream": False,
    "format": "json",           # Ollama 레벨 JSON 강제
    "options": {
        "temperature": 0.1,     # 4요소 추출은 결정론적 응답이 중요
        "num_predict": 512,     # 4요소 합산 최대 500자 수준
        "num_ctx": 4096,        # 민원 원문 수용
    },
}
```

**`format="json"`만으로 충분한 이유**: Ollama의 `format="json"` 파라미터는 모델이 반드시 JSON 객체를 출력하도록 강제한다. 이후 Pydantic으로 필드를 검증하므로 별도 `instructor` 라이브러리 추가 없이 처리 가능하다. `instructor` 도입은 의존성 추가와 Ollama 어댑터 구현이 필요하므로 현 시점에는 유보한다.

#### 4.3.2 시스템 프롬프트

```
당신은 민원 분석 AI입니다.
사용자의 민원 텍스트를 읽고 다음 4가지 요소를 추출하여 JSON 형식으로만 반환하세요.
다른 텍스트, 설명, 코드블록은 출력하지 마세요.

추출 항목:
- observation: 민원인이 겪은 문제 상황이나 관찰한 사실 (없으면 null)
- result: 문제로 인해 발생한 현재의 결과나 피해 (없으면 null)
- request: 민원인이 행정기관에 요구하는 구체적인 조치 (없으면 null)
- context: 문제가 발생한 배경이나 부가 설명 (없으면 null)

출력 형식 (반드시 이 JSON 구조만 반환):
{
  "observation": "string 또는 null",
  "result": "string 또는 null",
  "request": "string 또는 null",
  "context": "string 또는 null"
}
```

#### 4.3.3 파싱 및 재시도 전략

```
1차 시도 (temperature=0.1):
  Ollama 호출 → response JSON 파싱 → FourElementsLLMOutput.model_validate()
    성공 → 반환
    JSONDecodeError / ValidationError →

2차 시도 (temperature=0.0, 프롬프트에 "반드시 JSON만" 강조 추가):
  Ollama 호출 → 파싱
    성공 → 반환
    실패 →

Fallback:
  FourElementsLLMOutput(observation=None, result=None, request=None, context=None) 반환
  + 로깅: "LLM extraction failed after retry, using empty fallback"
```

#### 4.3.4 인터페이스

```python
class LLMSemanticExtractor:
    def __init__(self, ollama_url: str, model: str, timeout: float = 30.0): ...

    async def extract(
        self,
        text: str,
        *,
        max_text_len: int = 2000,   # 긴 민원 원문 앞 N자만 사용
    ) -> tuple[FourElementsLLMOutput, int]:
        """
        Returns:
            (FourElementsLLMOutput, extraction_latency_ms)
        """
```

`max_text_len`으로 너무 긴 원문을 앞에서 자른다. 민원 본문은 대부분 300~800자 수준이므로 2000자가 실질적 상한.

---

## 5. Stage 3: Result Merger & Validator

### 5.1 evidence_span 탐색 로직

LLM은 원문 위치를 반환하지 않는다. Merger가 추출된 텍스트를 원문에서 탐색해 span을 결정한다.

```
탐색 순서:
1. 정확 매칭: raw_text.find(llm_text)
     → 발견 시 (idx, idx + len(llm_text)) 반환

2. 부분 매칭: llm_text의 앞 30자를 키로 find()
     → 발견 시 해당 위치부터 min(len(llm_text), 200)자 범위 반환

3. 탐색 실패: span = [0, 0], span_source = "inferred"
     (validate_schema에서 warning 처리)
```

```python
def _find_span(raw_text: str, llm_text: str) -> tuple[int, int, str]:
    """Returns (start, end, span_source: 'exact' | 'partial' | 'inferred')"""
```

### 5.2 confidence 산정 규칙

**Rule-based 엔티티**: 정규식 매칭이므로 confidence = 1.0 고정.

**LLM 4요소**: non-null 필드 비율로 산정.

| non-null 필드 수 | confidence |
|---|---|
| 4 / 4 | 0.90 |
| 3 / 4 | 0.82 |
| 2 / 4 | 0.75 |
| 1 / 4 | 0.70 |
| 0 / 4 (전체 Fallback) | 0.0 (structured_by: "fallback") |

LLM이 전체 Fallback으로 돌아온 경우, `structure()` 전체가 실패하지 않도록 빈 필드(text="", confidence=0.0)를 반환하고 `structured_by: "fallback"` 플래그를 기록한다.

### 5.3 최종 병합 스키마

기존 스키마에 다음 필드를 추가한다.

```python
{
    # 기존 필드 유지
    "case_id": str,
    "observation": {"text": str, "confidence": float, "evidence_span": [int, int]},
    "result":      {"text": str, "confidence": float, "evidence_span": [int, int], "status": str},
    "request":     {"text": str, "confidence": float, "evidence_span": [int, int]},
    "context":     {"text": str, "confidence": float, "evidence_span": [int, int]},
    "entities":    [...],  # Rule-based NER (confidence=1.0)

    # 신규 추가
    "structured_by": "hybrid" | "llm_only" | "fallback",
    "extraction_meta": {
        "llm_model": str,            # e.g. "exaone3:7.8b-instruct"
        "llm_latency_ms": int,
        "ner_latency_ms": int,
        "llm_non_null_count": int,   # 0~4
        "span_sources": {            # 각 필드별 span 탐색 결과
            "observation": "exact" | "partial" | "inferred",
            "result":      "exact" | "partial" | "inferred",
            "request":     "exact" | "partial" | "inferred",
            "context":     "exact" | "partial" | "inferred",
        }
    }
}
```

### 5.4 ResultMerger 인터페이스

```python
class ResultMerger:
    def merge(
        self,
        raw_text: str,
        ner_result: RuleBasedNERResult,
        llm_output: FourElementsLLMOutput,
        llm_latency_ms: int,
        llm_model: str,
    ) -> dict:
        """
        Stage 1 + Stage 2 결과를 Unified Schema로 병합.
        evidence_span 탐색, confidence 산정 수행.
        validate_schema()는 StructuringService.structure()에서 호출.
        """
```

---

## 6. `validate_schema()` 점검 및 고도화 설계

### 6.1 현재 validate_schema() 문제점

| 문제 | 현상 | 위치 |
|---|---|---|
| evidence_span mismatch가 hard error | LLM이 원문 표현과 약간 다른 텍스트를 반환하면 `evidence_text_mismatch:observation` 에러 발생 → `is_valid=False` | `service.py:686` |
| `structured_by` 필드 미인식 | 신규 필드를 검증에 활용하지 않음 | 전체 없음 |
| `extraction_meta` 미검증 | LLM 메타 필드 타입 검증 없음 | 전체 없음 |
| `evidence_span_range` 검사가 span_source="inferred"에도 적용 | [0, 0]으로 반환된 inferred span이 항상 range 에러 발생 | `service.py:682` |
| result.status="insufficient"일 때 span=[0,0] 허용하나 text 비어도 range 체크 | `if span != [0, 0]` 조건이 `pending`에만 적용 | `service.py:678` |

### 6.2 고도화 설계

#### 6.2.1 `extraction_method` 파라미터 추가

```python
async def validate_schema(
    self,
    data: Dict[str, Any],
    extraction_method: str = "hybrid",  # "rule" | "llm" | "hybrid" | "fallback"
) -> Dict[str, Any]:
```

`extraction_method`에 따라 span 검증 엄격도를 분기한다.

#### 6.2.2 evidence_span 검증 로직 개선

```
현재 로직:
  0 <= start < end <= text_len 이어야 error 없음
  raw_text[start:end] == field.text 이어야 error 없음

개선 로직:
  span_source = data.get("extraction_meta", {}).get("span_sources", {}).get(field_name)

  if span == [0, 0]:
    if extraction_method in ("llm", "hybrid") and span_source == "inferred":
      → warnings.append(f"span_inferred:{field_name}")   ← error → warning으로 완화
    elif field_name == "result" and field.get("status") in ("pending", "insufficient"):
      → 정상 (기존 로직 유지)
    else:
      → warnings.append(f"span_missing:{field_name}")
  else:
    if not (0 <= start < end <= text_len):
      → errors.append(f"invalid_evidence_span_range:{field_name}")  ← 기존 유지
    else:
      sliced = raw_text[start:end]
      if normalize(sliced) != normalize(field.text):
        if extraction_method in ("llm", "hybrid"):
          → warnings.append(f"evidence_text_mismatch:{field_name}")  ← error → warning
        else:
          → errors.append(f"evidence_text_mismatch:{field_name}")    ← rule-based는 엄격 유지
```

#### 6.2.3 신규 검증 항목 추가

```python
# 1. structured_by 필드 타입 검증
if "structured_by" in data:
    allowed = {"hybrid", "llm_only", "fallback", "rule"}
    if data["structured_by"] not in allowed:
        errors.append("invalid_structured_by_value")

# 2. extraction_meta 필드 검증 (선택적)
meta = data.get("extraction_meta")
if meta is not None:
    if not isinstance(meta.get("llm_latency_ms"), int):
        warnings.append("invalid_extraction_meta:llm_latency_ms")
    llm_count = meta.get("llm_non_null_count")
    if llm_count is not None and not (0 <= llm_count <= 4):
        errors.append("invalid_extraction_meta:llm_non_null_count")

# 3. fallback 상태에서 confidence 경고
if data.get("structured_by") == "fallback":
    warnings.append("structuring_fallback_active")
```

#### 6.2.4 `result.status` 검증 강화

현재 `status` 값으로 `"pending"` / `"present"` / `"insufficient"` 세 가지를 허용한다. `"insufficient"` 상태에서도 span=[0,0]을 허용하도록 예외 조건을 명확히 추가한다.

```python
# 기존
if field_name == "result" and field.get("status") == "pending":
    if span != [0, 0]:
        errors.append("invalid_pending_result_span")

# 개선
if field_name == "result" and field.get("status") in ("pending", "insufficient"):
    # pending/insufficient는 span=[0,0]이 정상
    if span != [0, 0]:
        warnings.append(f"unexpected_span_for_status:{field.get('status')}")
```

---

## 7. config.py 변경 사항

`app/core/config.py`에 구조화 전용 Ollama 설정을 추가한다.

```python
# 신규 추가
STRUCTURING_MODEL: str = os.getenv("STRUCTURING_MODEL", "exaone3:7.8b-instruct")
STRUCTURING_TIMEOUT: float = float(os.getenv("STRUCTURING_TIMEOUT", "30.0"))
STRUCTURING_MAX_TEXT_LEN: int = int(os.getenv("STRUCTURING_MAX_TEXT_LEN", "2000"))
```

QA 생성용 `OLLAMA_MODEL`(현재 `qwen2.5:7b-instruct`)과 구조화용 모델을 분리함으로써 모델 교체 시 영향 범위를 최소화한다.

---

## 8. 최종 파일 구조

```
app/structuring/
  __init__.py
  service.py          ← 정리됨: Orchestrator + Stage 1 NER + validate_schema()
  llm_extractor.py    ← 신규: LLMSemanticExtractor
  schemas.py          ← 신규: FourElementsLLMOutput, RuleBasedNERResult
  merger.py           ← 신규: ResultMerger (evidence_span 탐색, confidence 산정)
```

### service.py 최종 역할 (정리 후)

```python
class StructuringService:
    """Orchestrator: Stage 1 → Stage 2 → Stage 3 순차 실행"""

    # 유지: Rule-based NER 메서드들
    def extract_entities(self, text) -> List[Dict]        # Stage 1
    def validate_schema(self, data, extraction_method)    # Stage 3 최종 검증

    # 제거: 4요소 추출 관련 모든 메서드 (→ llm_extractor.py로 이전)
    # extract_four_elements, _split_segments, _sentence_candidates,
    # _score_candidate, _pick_best, _score_to_confidence

    async def structure(self, record) -> Dict:
        # 1. 입력 정규화
        # 2. Stage 1: extract_entities() [Rule NER]
        # 3. Stage 2: LLMSemanticExtractor.extract()
        # 4. Stage 3: ResultMerger.merge()
        # 5. compute_confidence_score()
        # 6. validate_schema(extraction_method="hybrid")
        # 7. 결과 반환
```

---

## 9. 에러 처리 전략

| 상황 | 처리 방식 |
|---|---|
| Ollama 연결 실패 (ConnectError) | `StructuringError(code="LLM_NOT_READY")` 발생. 재시도 없음. |
| Ollama 타임아웃 | 2차 시도 없이 Fallback 반환 (`structured_by="fallback"`) + 경고 로그 |
| LLM JSON 파싱 실패 (1회) | temperature=0.0으로 2차 시도 |
| LLM JSON 파싱 실패 (2회 연속) | Fallback 반환 + `pipeline_logger.warning` |
| Pydantic 검증 실패 | 개별 null 필드로 처리 (`model_construct` 활용) |
| Rule NER 정규식 예외 | 빈 entities 반환 + 경고 로그, 파이프라인 중단 없음 |

---

## 10. 구현 시 주의사항

1. **`format="json"` 단독 사용의 한계**: Ollama의 `format="json"`은 JSON 형식은 보장하지만 키 이름이나 값 타입은 보장하지 않는다. 반드시 `FourElementsLLMOutput.model_validate()`로 후처리 필요. `model_validate`가 실패하면 재시도 로직 진입.

2. **evidence_span 탐색의 신뢰도**: LLM은 원문을 요약·압축해서 반환하는 경향이 있어 정확 매칭 실패율이 높다. `span_source="inferred"` 비율을 모니터링해 모델 프롬프트 개선 여부를 판단할 것.

3. **`extract_entities()`의 LOCATION 하드코딩 제거**: 현재 `["서울", "경기", "안양", "송파구", "풍납동"]` 고정 목록은 패턴 기반으로 전환해 유지보수 의존성을 없앤다.

4. **동기/비동기 일관성**: `LLMSemanticExtractor.extract()`는 `async`여야 한다. `service.py`의 `structure()` 호출 체인이 모두 `await`로 연결되어 있으므로 기존 패턴 그대로 유지.

5. **모델 워밍업**: EXAONE 3.0 7.8B는 첫 호출 시 로딩 지연이 발생한다. `app/api/main.py`의 lifespan context에서 구조화 모델 워밍업 호출을 추가하는 것을 권장한다.

6. **기존 테스트 영향 범위**: `app/tests/unit/test_be1_week2_tasks.py` 등이 `extract_four_elements()` 직접 호출 가능성이 있다. 해당 테스트를 `structure()` 통합 호출 방식으로 마이그레이션 필요.
