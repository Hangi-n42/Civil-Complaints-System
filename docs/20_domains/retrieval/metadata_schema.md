# 검색 메타데이터 구조 초안 (Week 1, BE2)

문서 버전: v1.0  
작성일: 2026-03-17  
담당: BE2 (민건)

## 1. 목적

검색 필터링과 QA citation 추적에 필요한 최소 메타데이터 키를 고정한다.

## 2. 필수 키 정의

| 키 | 타입 | 필수 | 제공 주체 | 설명 |
| --- | --- | --- | --- | --- |
| `case_id` | string | Y | BE1 | 원본 민원 식별자 |
| `source` | string | Y | BE1 | 데이터 출처 |
| `created_at` | string(datetime) | Y | BE1 | 시간 필터 기준 |
| `category` | string | N | BE1 (우선), BE2 어댑터(보정) | 카테고리 필터 |
| `region` | string | N | BE1 (우선), BE2 어댑터(보정) | 지역 필터 |
| `entity_labels` | array[string] | N | BE1 | NER 태그 목록 |

## 3. 검색 API 필터 키 매핑

`POST /api/v1/search`에서 아래 키를 사용한다.

```json
{
  "filters": {
    "region": "서울시 강남구",
    "category": "도로안전",
    "date_from": "2026-01-01T00:00:00+09:00",
    "date_to": "2026-03-17T23:59:59+09:00",
    "entity_labels": ["FACILITY", "HAZARD"]
  }
}
```

매핑 규칙:
- `date_from` -> `created_at >= date_from`
- `date_to` -> `created_at <= date_to`
- `entity_labels`는 OR 매칭(최소 1개 포함)

## 4. 정규화 규칙

1. `case_id`
- 우선순위: `case_id` -> `id`
- 예: `sample_001` -> `CASE-SAMPLE-001` (어댑터 규칙에서 통일)

2. `created_at`
- 우선순위: `created_at` -> `submitted_at`
- 포맷은 ISO 8601으로 변환한다.

3. `source`
- `source` 누락 시 `metadata.source`에서 보충
- 모두 누락 시 `unknown` 기본값

4. `entity_labels`
- 값은 대문자 라벨로 통일
- 허용 라벨: `LOCATION`, `TIME`, `FACILITY`, `HAZARD`, `ADMIN_UNIT`

## 5. 품질 체크

인덱싱 전 아래를 검사한다.

- `case_id` 공백 여부
- `created_at` 파싱 가능 여부
- `category`, `region` 누락 비율
- `entity_labels` 허용 라벨 외 값 포함 여부

## 6. 리스크 및 대응

### 리스크: 샘플 데이터 필드 불일치
- 징후: `id`, `submitted_at`만 있고 `case_id`, `created_at`이 없음
- 원인: 샘플 포맷이 계약 문서보다 단순함
- 예방책: 어댑터에서 명시 변환 규칙 적용
- 대응책: 변환 실패 레코드 로깅 후 스킵
- 최악의 경우 폴백안: 필터 축소(시간/지역) 후 시맨틱 검색만 운영
