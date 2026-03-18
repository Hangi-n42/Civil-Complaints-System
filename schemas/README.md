# Schemas

프로젝트의 데이터 계약(JSON Schema) 정의 디렉토리입니다.

## 1) civil_case.schema.json

AIHub 공공 민원 원천데이터를 내부 구조화 포맷으로 변환한 최종 스키마입니다.

- 필수 필드
	- `case_id`, `created_at`, `source`
	- `raw_text`
	- `observation`, `result`, `request`, `context`
	- `entities`
- 권장 필드
	- `category`, `region`
- 보존 메타
	- `metadata.source_id`, `metadata.consulting_category`, `metadata.consulting_turns`, `metadata.consulting_length`, `metadata.client_gender`, `metadata.client_age`
- 라벨링 보조 정보(선택)
	- `supervision.classification`
	- `supervision.summary`
	- `supervision.qa[]`

## 2) 필드 보정 정책(Week2 계약)

- `id` -> `case_id`
- `submitted_at` -> `created_at`
- `metadata.source` -> `source`
- 누락 시 기본값
	- `category = "unknown"`
	- `region = "unknown"`
	- `entities = []`

## 3) 비고

- `supervision` 필드는 AIHub 제공 라벨링 데이터(질의응답/요약/분류)를 저장하기 위한 선택 필드입니다.
- 운영 추론 경로에서는 `supervision` 없이도 동작하도록 설계합니다.
