# BE1-BE2 인터페이스 계약 (Week 1)

문서 버전: v1.0  
작성일: 2026-03-17  
담당: BE1, BE2

## 1. 목적

BE1 구조화 결과를 BE2 인덱싱 파이프라인에 안정적으로 연결하기 위한 입력 계약을 고정한다.

## 2. 전달 객체 (BE1 -> BE2)

최소 필수 필드:

```json
{
  "case_id": "CASE-2026-000123",
  "source": "civil_portal",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 강남구",
  "observation": {"text": "...", "confidence": 0.9, "evidence_span": [0, 20]},
  "result": {"text": "...", "confidence": 0.8, "evidence_span": [21, 40]},
  "request": {"text": "...", "confidence": 0.9, "evidence_span": [41, 60]},
  "context": {"text": "...", "confidence": 0.7, "evidence_span": [61, 80]},
  "entities": [{"label": "FACILITY", "text": "가로등"}]
}
```

## 3. 필드 책임

| 필드 | 책임 | 비고 |
| --- | --- | --- |
| `case_id`, `created_at`, `source` | BE1 필수 제공 | 누락 시 BE2 어댑터가 보정 시도 |
| `category`, `region` | BE1 우선 제공 | 누락 허용(필터 제한됨) |
| `entities` | BE1 제공 | `entity_labels`는 BE2가 파생 생성 |
| 4요소 confidence | BE1 제공 | 검색 품질 분석에 활용 |

## 4. 어댑터 규칙 (BE2)

샘플 포맷 불일치 대응:
- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`

## 5. 합의 체크포인트

- [ ] BE1이 Week 2 시작 전 필수 필드 제공 가능
- [ ] 누락 필드 기본값 정책 확정 (`unknown`, `null`)
- [ ] 전달 경로 확정 (파일 기반 또는 API 호출)

## 6. 오픈 이슈

- `category`, `region` 자동 추출 수준을 어디까지 허용할지
- `raw_text` 저장 범위(원문/마스킹본 동시 보관 여부)
