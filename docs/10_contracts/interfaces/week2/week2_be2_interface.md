# Week 2 BE2 인터페이스 문서

문서 버전: v1.0-week2  
작성일: 2026-03-19  
책임: BE2  
협업: BE1, BE3

## 1) 책임 범위

- 구조화 결과를 인덱싱 입력으로 변환
- 검색 메타데이터 매핑 고정
- 검색용 청크 스키마 일관성 유지

## 2) BE2 입력 계약 (from BE1)

객체명: `StructuredCivilCase`

필수 키:
- `case_id`, `source`, `created_at`
- `observation`, `result`, `request`, `context`
- `entities`, `validation`

## 3) BE2 출력 계약 (index input)

객체명: `SearchChunk`

```json
{
  "chunk_id": "CASE-2026-000123__chunk-0",
  "case_id": "CASE-2026-000123",
  "chunk_text": "임베딩 대상 텍스트",
  "chunk_type": "combined",
  "source": "aihub_71852",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 강남구",
  "entity_labels": ["FACILITY", "TIME"],
  "entity_texts": ["가로등", "매일 저녁 8시"],
  "metadata": {
    "pipeline_version": "week2"
  }
}
```

## 4) 변수명 충돌 방지 규칙

- 문서ID는 `doc_id`, 케이스ID는 `case_id`로 분리한다 (`id` 단일 키 금지).
- 검색 점수는 `score`, citation 점수는 `relevance_score`로 분리한다.
- 청크 원문은 `chunk_text` 고정 (`text`, `content` 금지).
- 엔티티는 `entity_labels`/`entity_texts` 파생 필드만 생성하고 원본은 `entities`를 유지한다.

## 5) BE2 완료 체크

- [ ] `chunk_id` 규칙 `<case_id>__chunk-<n>` 준수
- [ ] `created_at` ISO-8601 유지
- [ ] `entity_labels`와 `entity_texts` 길이 정합성 검증

## 6) entity_labels 계약 고정 (BE1/BE2/BE3 공통)

허용 라벨셋(고정):

- `LOCATION`
- `TIME`
- `FACILITY`
- `HAZARD`
- `ADMIN_UNIT`

인덱싱 저장 규칙:

- BE2는 인덱싱 시 `entity_labels`에 허용 라벨셋만 저장한다.
- 허용 라벨이 아닌 값은 저장하지 않는다.

검색 필터 규칙 (`filters.entity_labels`):

- 매칭은 OR 규칙이다. (`FACILITY`, `HAZARD` 전달 시 둘 중 하나라도 포함하면 매칭)
- 빈 배열(`[]`)은 "필터 미적용"으로 처리한다.
- 미전달(`null` 또는 키 없음)도 "필터 미적용"으로 처리한다.
- 허용 라벨셋 외 입력은 요청을 거부한다. (FastAPI/Pydantic 검증 오류, HTTP 422)

비정상 라벨 처리 정책:

- 정책: **무시하지 않고 에러 반환(Reject)**
- 이유: FE 오류 메시지 표준화, 디버깅 용이성, 재현 가능한 동작 보장
