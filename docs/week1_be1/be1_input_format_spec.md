# BE1 Week1 입력 포맷 기준서

문서 버전: v1.0  
작성일: 2026-03-18

## 1. 목적

Week 1 기준으로 팀 전체가 동일한 입력 포맷을 사용하도록 민원 입력 규격을 고정한다.

## 2. 입력 채널

- `manual`: UI 수동 입력
- `csv`: 배치 CSV 업로드
- `json`: 배치 JSON 업로드

## 3. 표준 내부 필드

| 필드 | 타입 | 필수 | 기본값 정책 | 설명 |
| --- | --- | --- | --- | --- |
| `case_id` | string | Y | 없음(생성 실패 시 레코드 reject) | 민원 식별자 |
| `source` | string | Y | `unknown` | 제공기관/출처 |
| `created_at` | string | Y | `unknown` | 생성일(`YYYYMMDD` 또는 ISO8601) |
| `category` | string | N | `unknown` | 민원 카테고리 |
| `region` | string | N | `unknown` | 행정구역 |
| `raw_text` | string | Y | 없음(공백만 있으면 reject) | 원문 민원 텍스트 |
| `entities` | array | N | `[]` | NER 결과(초기 비어도 허용) |
| `metadata` | object | N | `{}` | 원천 보존 메타 |

## 4. 원천데이터 매핑 규칙

| 원천 필드 | 내부 필드 | 규칙 |
| --- | --- | --- |
| `source_id` | `case_id` | 문자열 유지 |
| `source` | `source` | 공백 시 `unknown` |
| `consulting_date` | `created_at` | 원문 `YYYYMMDD` 유지 |
| `consulting_category` | `category` | `-` 또는 공백은 `unknown` |
| `consulting_content` | `raw_text` | 원문 유지 |

## 5. 어댑터 보정 규칙

- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`

## 6. 입력 예시(JSON)

```json
{
  "case_id": "000022",
  "source": "서울시",
  "created_at": "20240709",
  "category": "재난안전",
  "region": "unknown",
  "raw_text": "제목 : 한가람로 풍납동까지 연결해 주세요...",
  "entities": [],
  "metadata": {
    "source_id": "000022",
    "consulting_turns": 2,
    "consulting_length": 199
  }
}
```

## 7. Reject 기준

- `case_id` 누락
- `raw_text`가 비어있거나 공백만 존재
- 구조적으로 JSON 파싱 불가

## 8. 산출 경로

- 파일 전달: `data/samples/week2_delivery_sample_20.json`
- API 전달: `/api/v1/ingest`, `/api/v1/structure`
