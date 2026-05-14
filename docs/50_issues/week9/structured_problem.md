# 구조화 4요소 추출 실패 분석 및 수정

작성일: 2026-05-12  
관련 파일: `app/structuring/llm_extractor.py`  
상태: **수정 완료**

---

## 1. 증상

`scripts/build_index.py` 실행 시 모든 문서에서 아래와 같은 출력이 나타남.

```
structured_by=fallback, confidence=0.05
Observation:
Result:
Request:
Context:
```

---

## 2. 원인 추적

팀원이 `_call_once()` 직후에 로깅을 추가해 Ollama의 실제 응답을 확인한 결과:

```
LLM raw response: {"event":"ticket_discount","amount":5}
```

민원 텍스트와 전혀 무관한 임의 JSON이 반환되고 있었다.  
`FourElementsLLMOutput.model_validate()` 단계에서 필수 키(`observation` 등)가 없으므로  
`ValidationError` → 재시도 → 재시도 후에도 동일 실패 → Fallback으로 귀결되었다.

---

## 3. 근본 원인 분석

### 3-1. 기존 구현의 문제

`_build_payload()`가 Ollama `/api/generate` 엔드포인트에 다음 형태의 페이로드를 전송했다:

```python
{
    "model": "exaone3:7.8b-instruct",
    "system": "<민원 분석 시스템 프롬프트>",   # ← 문제
    "prompt": "민원 텍스트:\n...",
    "format": "json",
    ...
}
```

### 3-2. `/api/generate`의 `system` 필드 동작 방식

Ollama의 `/api/generate` 엔드포인트는 `system` 파라미터를 지원하지만,
이 필드를 **모델의 native chat template에 자동 적용하지 않는다**.

EXAONE 3.0 instruct 모델의 native chat template은 다음 형태다:

```
[|system|]
{system_content}[|endofturn|]
[|user|]
{user_content}[|endofturn|]
[|assistant|]
```

`/api/generate`에서 `system` 필드를 넘기면 이 template이 적용되지 않아
모델이 **system prompt를 무시**하고 사전 학습에서 본 임의 패턴을 출력한다.  
결과적으로 `{"event":"ticket_discount","amount":5}` 같은 무관한 JSON이 나온다.

### 3-3. `/api/chat` vs `/api/generate` 비교

| 항목 | `/api/generate` | `/api/chat` |
|---|---|---|
| 요청 형태 | `system` + `prompt` 단일 문자열 | `messages` 배열 (role/content) |
| Chat template 적용 | **자동 미적용** | **자동 적용** (Ollama가 모델별 처리) |
| Instruct 모델 적합성 | 낮음 | 높음 |
| 응답 경로 | `response.json()["response"]` | `response.json()["message"]["content"]` |

---

## 4. 수정 방안

### 방안 A — `/api/chat` + messages 배열 전환 **(채택)**

Ollama `/api/chat` 엔드포인트를 사용하면 Ollama가 모델의 chat template을 자동으로 적용한다.

```python
# _build_payload() 변경
def _build_payload(self, text, temperature, retry):
    system = _SYSTEM_PROMPT + (_RETRY_SUFFIX if retry else "")
    return {
        "model": self.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": f"민원 텍스트:\n{text[:self.max_text_len]}"},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature, "num_predict": 512, "num_ctx": 4096},
    }

# _call_once() 변경
url = f"{self.ollama_url}/api/chat"                    # 엔드포인트 변경
raw = response.json().get("message", {}).get("content", "")  # 응답 파싱 변경
```

**채택 이유:**
- EXAONE뿐 아니라 다른 instruct 모델(EXAONE 3.5, qwen 등)도 동일하게 처리 가능
- 모델 교체 시 추가 코드 수정 불필요 (Ollama가 template 자동 처리)
- Ollama 공식 권장 방식

### 방안 B — system prompt를 prompt 필드에 직접 병합 (대안)

```python
full_prompt = f"{_SYSTEM_PROMPT}\n\n민원 텍스트:\n{text[:self.max_text_len]}"
payload = {"model": self.model, "prompt": full_prompt, ...}
```

단점: 모델 교체 시 native chat template과 충돌 가능. EXAONE에 한정적으로만 유효.

---

## 5. 실제 수정 내역

**파일**: `app/structuring/llm_extractor.py`

| 메서드 | 변경 전 | 변경 후 |
|---|---|---|
| `_build_payload()` | `"system"` + `"prompt"` 키 | `"messages"` 배열 (`system`/`user` role) |
| `_call_once()` | 엔드포인트: `/api/generate` | 엔드포인트: `/api/chat` |
| `_call_once()` | 파싱: `json()["response"]` | 파싱: `json()["message"]["content"]` |

---

## 6. 검증 방법

```bash
# 1. 임포트 확인
python -c "from app.structuring.llm_extractor import LLMSemanticExtractor; print('OK')"

# 2. 소규모 실행 (국립아시아문화전당 1개 파일)
python scripts/build_index.py \
  --input-dir data/Training/01.원천데이터/TS_국립아시아문화전당 \
  --api-url http://127.0.0.1:8000

# 3. 성공 기준 확인
# 터미널 출력에서:
# structured_by=hybrid  ← fallback 이 아님
# confidence >= 0.70
# Observation: [한국어 민원 텍스트]
# Request:     [한국어 요청 텍스트]
```

---

## 7. 영향 범위

- 수정 파일: `app/structuring/llm_extractor.py` (2개 메서드)
- 영향 범위: 구조화 서비스 전체 (`StructuringService.structure()` 경유)
- 하위 호환성: `/api/chat`은 `/api/generate`와 동일한 모델을 사용하므로 기존 설정 (`STRUCTURING_MODEL`) 그대로 유지
- 기존 테스트 영향: `LLMSemanticExtractor` 자체 단위 테스트 없음. `test_be1_week2_tasks.py`는 Ollama 미기동 시 fallback으로 통과하므로 영향 없음.

---

## 8. FE 요청 필드 정합성 점검 (Week9)

FE가 요청한 필드와 실제 코드(ingestion/structuring)를 비교했다.
기준 코드: `app/ingestion/service.py`, `app/structuring/service.py`, `app/structuring/merger.py`.

### 8.1 민원 기본 레코드 & 구조화 결과 (structured)

| FE 요청 필드 | 실제 코드 기준 | 정합성 | 비고 |
| --- | --- | --- | --- |
| `case_id` | ingestion/structuring 정상화에 존재 | OK | - |
| `source` | ingestion/structuring 정상화에 존재 | OK | - |
| `raw_text` | ingestion/structuring 정상화에 존재 | OK | - |
| `status` | 코드에 없음 | NO | 별도 상태 저장/관리 로직 필요 |
| `priority` | 신규 도입 (SLA 기반 산정) | OK | 라벨 enum: 매우급함/급함/보통 (SLA 기준, HAZARD 있으면 +1단계) |
| `created_at` | ingestion/structuring 정상화에 존재 | OK | - |
| `admin_unit` | top-level 필드 승격 | OK | `ADMIN_UNIT` 엔티티 우선, 없으면 region fallback |
| `category` | ingestion/structuring 정상화에 존재 | OK | - |
| `region` | ingestion/structuring 정상화에 존재 | OK | - |
| `observation/result/request/context` | `merger`가 `{text, confidence, evidence_span}` 생성 | OK | `result`만 `status` 추가 필드 포함 |
| `entities` | Rule NER 결과 `[{label, text}]` | OK | 허용 라벨: LOCATION/TIME/FACILITY/HAZARD/ADMIN_UNIT |
| `validation` | `{is_valid, errors}`만 유지 | OK | warnings 제거 (MVP) |

정렬 규칙: 동일 priority 단계에서는 `created_at` 오래된 순으로 정렬.

추가로 현재 structuring 결과에는 아래 필드가 자동 포함된다(요청 외 추가):
- `structured_by`, `extraction_meta`, `confidence_score`, `structured_at`, `metadata`

### 8.2 관리자 대시보드 통계 API (예: `/api/v1/stats/dashboard`)

현재 계약 문서에 정의가 없어, FE 요구 구조를 아래와 같이 임시 명세로 추가한다.

```json
{
    "total_cases": 0,
    "cases_this_month": 0,
    "cases_this_week": 0,
    "category_stats": {
        "category": ["도로안전"],
        "count": [342],
        "change_pct": [12.5]
    },
    "hazard_top5": [
        {"hazard": "포트홀", "count": 124, "percentage": 15.2}
    ],
    "region_stats": {
        "region": ["강남구"],
        "count": [256]
    },
    "weekly_trends": {
        "weeks": ["1주차"],
        "counts": [58]
    }
}
```

### 8.3 결정 필요 항목 (FE/BE 합의 필요)

- `status` 필드를 어디서 관리/노출할지 (ingestion/structuring에는 없음)
