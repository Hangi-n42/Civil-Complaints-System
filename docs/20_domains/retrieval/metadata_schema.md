# 검색 메타데이터 구조 초안 (Week 1, BE2)

문서 버전: v1.1
작성일: 2026-06-08
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

## 2-1. 검색 rerank 보조 신호

아래 키는 PR #314 이후 BE1 구조화 결과에서 넘어오는 검색 보조 신호다. BE2는 ChromaDB
메타데이터 제약 때문에 인덱싱 시 `|` 구분 문자열로 저장하고, 검색 결과에서는 다시
`array[string]`으로 복원한다. 현재 단계에서는 hard filter가 아니라 후속 soft rerank
신호로만 사용한다.

| BE1 원본 필드 | Chroma 메타데이터 키 | 검색 결과 타입 | 설명 |
| --- | --- | --- | --- |
| `entity_texts[].text` | `entity_texts` | array[string] | 정규화된 대상/시설/개념명 |
| `legal_refs[].name` | `legal_ref_names` | array[string] | 관련 법령명 |
| `legal_refs[].law_id` | `legal_ref_ids` | array[string] | 법령 식별자 |
| `key_terms` | `key_terms` | array[string] | 핵심 키워드 |
| `responsible_unit[].name` | `responsible_units` | array[string] | 후보 담당부서/소관기관 |
| `urgency.level` | `urgency_level` | string | 긴급도 레벨 |

운영 주의:
- `confidence`는 아직 보정되지 않았으므로 절대 임계값 필터로 쓰지 않는다.
- `responsible_unit`은 BE1 기본값이 비활성일 수 있어 필수 신호로 보지 않는다.
- 누락된 값은 빈 배열 또는 빈 문자열로 보존한다.

### `/api/v1/search.query_signals`

신규 민원 구조화 결과를 검색 쿼리와 함께 넘길 때는 `filters`가 아니라
`query_signals`를 사용한다. 이 값은 후보를 제외하지 않고 순서만 살짝 조정한다.

```json
{
  "query": "가로등 점검 요청",
  "top_k": 5,
  "query_signals": {
    "entity_texts": ["가로등"],
    "legal_ref_names": ["도로법"],
    "legal_ref_ids": ["001706"],
    "key_terms": ["가로등", "점검"],
    "responsible_units": ["도로관리과"]
  }
}
```

Soft rerank 점수 정책:

| 신호 | boost |
| --- | --- |
| `legal_ref_ids` 일치 | `+0.08` |
| `legal_ref_names` 일치 | `+0.06` |
| `entity_texts` 일치 | `+0.04` |
| `responsible_units` 일치 | `+0.03` |
| `key_terms` 겹침 | `+0.01 * overlap_count`, 최대 `+0.04` |

전체 boost는 최대 `+0.20`이며, 최종 점수는 `base_score * (1 + boost)`로 계산한다.
적용 순서는 `Hybrid -> metadata soft rerank -> grounding_filter -> top_k`이다.

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
