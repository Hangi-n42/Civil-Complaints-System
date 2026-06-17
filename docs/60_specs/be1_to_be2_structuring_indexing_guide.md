# BE1 구조화 결과를 BE2 검색 인덱스에 넣는 방법

## 목적

BE2가 원천 민원 데이터를 검색 인덱스에 넣기 전에 BE1 구조화 파이프라인을 실행하는 절차를 정리한다.

현재 계약은 **원천데이터만 사용**한다. `02.라벨링데이터`의 `instructions`/`supervision`은 BE1 구조화 입력이나 출력에 사용하지 않는다.

## 전체 흐름

```text
원천 JSON
  -> BE1 preprocessing
     - consulting_content에서 민원인 제목/Q/A를 분리
     - 검색 재색인용 구조화 본문에는 민원인 원문과 상담사 답변을 함께 사용
  -> Ingestion
     - 텍스트 정제
     - PII 마스킹
  -> StructuringService.structure()
     - Rule NER
     - LLM 4요소 구조화
     - entity_texts / legal_refs / key_terms
     - responsible_unit / urgency
  -> scripts/build_index.py
     - BE2 /api/v1/index 호출
  -> BE2 ChromaDB collection(civil_cases_v1)
```

## 입력 데이터

권장 입력은 AI Hub 원천데이터 JSON 디렉터리다.

```text
data/raw_data
```

원본 Training 구조를 유지한다면 아래 경로만 사용한다.

```text
data/Training/01.원천데이터
```

사용하지 않는 경로:

```text
data/Training/02.라벨링데이터
```

## BE1 전처리 보장

`app/structuring/preprocessing.py`가 원천 포맷을 통합한다.

- `제목 / Q / A` 형식
- `Q.`, `A:`, `답변:` 변형
- `_x000D_` 줄바꿈 잔재
- `고객:` / `상담원:` 대화형 형식

BE1 구조화 입력의 `text`/`raw_text`에는 민원인 제목과 질문만 들어간다. 상담사 답변은 민원인의 요구가 아니므로 구조화, 담당부서, 긴급도 판단에 섞지 않는다.

BE2 검색 색인 본문은 `search_text`를 우선 사용한다. 이 값은 과거 상담 데이터에 상담사 답변이 있으면 `title + client_question + consultant_answer`로 만들고, 신규 민원처럼 답변이 없으면 자연스럽게 `title + client_question`만 담는다. 이 분리는 외부 API/DTO 형식을 바꾸지 않고 내부 텍스트 생성 정책만 명확히 하기 위한 것이다.

구조화 진입점은 공식 인덱싱 스크립트를 우회한 단건 호출에서도 PII 마스킹을 다시 적용한다. 따라서 `StructuringService.structure()`와 `/api/v1/structure`의 `raw_text` 및 후속 구조화 필드는 마스킹된 본문을 기준으로 생성된다.

원천 파싱 결과는 `title`, `client_question`, `consultant_answer`를 분리 보존한다. 다만 구조화 모델 입력과 검색 인덱싱으로 이어지는 `text`/`raw_text`는 이 필드들을 정책상 결합한 단일 본문이다.

## BE1 구조화 단건 API

단건 검증이나 BE2/BE3 연계 테스트는 `/api/v1/structure`를 사용할 수 있다.

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/structure `
  -H "Content-Type: application/json" `
  -d "{\"request_id\":\"STR-LOCAL-001\",\"case_id\":\"CASE-1\",\"raw_text\":\"도로 파손 보수 요청\"}"
```

본문이 비어 있으면 `BAD_REQUEST`를 반환한다. `text`, `raw_text`, `consulting_content` 중 하나는 필요하다.

## BE2 인덱싱 실행

BE2 API 서버를 먼저 실행한 뒤 BE1 저장소에서 실행한다.

```powershell
python scripts/build_index.py `
  --input-dir data/raw_data `
  --api-url http://127.0.0.1:8000 `
  --collection-name civil_cases_v1 `
  --batch-size 20 `
  --rebuild
```

Training 원천 폴더를 직접 쓸 경우:

```powershell
python scripts/build_index.py `
  --input-dir data/Training/01.원천데이터 `
  --api-url http://127.0.0.1:8000 `
  --collection-name civil_cases_v1 `
  --batch-size 20 `
  --rebuild
```

소량 검증:

```powershell
python scripts/build_index.py `
  --input-dir data/raw_data `
  --api-url http://127.0.0.1:8000 `
  --collection-name civil_cases_v1 `
  --batch-size 5 `
  --limit 10 `
  --no-rebuild
```

## BE2 전달 필드

`scripts/build_index.py`는 BE1 구조화 결과를 BE2 `/api/v1/index` 계약으로 변환한다.

- `case_id`: 원천 민원 식별자
- `source`: 원천 기관/지역
- `created_at`: 접수일
- `category`: 원천 카테고리
- `region`: 지역
- `text`: BE2 임베딩 대상 검색 본문. `search_text`가 있으면 답변 포함 본문을 사용하고, 없으면 구조화 4요소 결합으로 fallback한다.
- `structured_text`: observation/result/request/context 평탄 텍스트
- `entities`: BE1 NER 결과
- `metadata.structured_by`: `hybrid`, `constrained`, `fallback`
- `metadata.is_valid`: BE1 schema validation 결과

BE1 구조화 원본에는 검색 보조 신호도 포함된다.

- `entity_texts`
- `legal_refs`
- `key_terms`
- `responsible_unit`
- `urgency`

BE2가 해당 신호를 metadata로 보존하면 soft rerank에 사용할 수 있다.

## 담당부서 신호

`responsible_unit`은 BE1이 실제 담당부서 후보를 추론한 경우에만 채워진다.

```json
{
  "responsible_unit": [
    {
      "name": "도로안전과",
      "confidence": 0.54,
      "evidence": ["도로시설물 안전점검", "도로"],
      "source": "be1_structured"
    }
  ]
}
```

담당부서 후보가 없으면 빈 배열을 허용한다.

```json
{
  "responsible_unit": []
}
```

`category/source` fallback은 BE1 담당부서 추론값이 아니므로 BE2 soft rerank에서 실제 담당부서와 동일하게 해석하지 않는다.

## 검증 체크리스트

인덱싱 전:

```powershell
python -m pytest app/tests/unit/test_preprocessing_adapter.py app/tests/unit/test_be1_week2_tasks.py -q
```

원천데이터 전처리 커버리지 확인:

```powershell
@'
import json
from pathlib import Path
from app.structuring.preprocessing import process_raw_record, to_structuring_record

total = question = text = 0
for path in Path("data/raw_data").glob("*.json"):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        continue
    for row in payload:
        if not isinstance(row, dict):
            continue
        total += 1
        processed = process_raw_record(row)
        structured = to_structuring_record(row)
        question += bool(processed.get("client_question"))
        text += bool(structured.get("text"))

print({"total": total, "client_question": question, "structuring_text": text})
'@ | python -
```

기대값:

```text
client_question == total
structuring_text == total
```

BE2 Chroma metadata 재측정:

```powershell
python scripts/check_chromadb_search_signal_coverage.py `
  --persist-dir data/chroma_db `
  --collection civil_cases_v1
```

## 장애 시 확인 순서

1. `text`가 비어 있으면 `consulting_content` 포맷이 `preprocessing.py`에서 커버되는지 확인한다.
2. `A:` 또는 `상담원:` 답변은 검색/구조화 입력에 포함되는 것이 정상이다. 다만 원천 파싱 결과에서는 `client_question`과 `consultant_answer`가 분리되어야 한다.
3. BE2 API가 실패하면 `/api/v1/index` 응답의 `failed_count`와 서버 로그를 먼저 확인한다.
4. `responsible_unit`이 비어 있어도 구조화 실패는 아니다. 담당부서 인덱스/플래그가 꺼져 있으면 빈 배열이 정상이다.
5. 구조화 4요소가 모두 비면 BE2 색인용 `text`는 마스킹된 원천 본문으로 fallback된다. 이 경우 metadata의 `index_text_source=raw_text_fallback_empty_structured`와 `empty_structured_text_fallback=true`를 확인한다.
