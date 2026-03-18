# BE1 Week1 4요소 수작업 20건 샘플 기준

문서 버전: v1.0  
작성일: 2026-03-18

## 1. 목적

구조화 품질 초기 기준선을 만들기 위한 수작업 20건 어노테이션 규칙을 정의한다.

## 2. 표본 선정 규칙

- 총 20건
- 기관 유형 균형: 중앙행정/지방행정/공공기관 혼합
- 길이 균형: 단문(<=180) 6건, 중문(181~320) 8건, 장문(>=321) 6건
- 유형 균형: 교통, 환경, 안전, 문화, 행정 민원 혼합

## 3. 어노테이션 단위

각 케이스에 대해 아래를 수작업 작성한다.

- `observation.text`
- `result.text`
- `request.text`
- `context.text`
- `entities[]` (`LOCATION`, `TIME`, `FACILITY`, `HAZARD`, `ADMIN_UNIT`)

## 4. 4요소 정의 기준

- observation: 민원인이 관찰/인지한 사실
- result: 발생한 영향/피해/상태 결과
- request: 행정기관에 요구하는 조치
- context: 배경 정보(시점, 장소, 이력, 법령 맥락)

## 5. 판정 우선순위

- 한 문장이 여러 필드 후보일 때 `request > result > observation > context` 우선순위로 배정
- 법령 인용/회신 단락은 `context` 우선

## 6. 산출 파일 형식(템플릿)

```json
{
  "case_id": "000022",
  "observation": {"text": "", "confidence": 1.0, "evidence_span": [0, 0]},
  "result": {"text": "", "confidence": 1.0, "evidence_span": [0, 0]},
  "request": {"text": "", "confidence": 1.0, "evidence_span": [0, 0]},
  "context": {"text": "", "confidence": 1.0, "evidence_span": [0, 0]},
  "entities": []
}
```

## 7. 품질 점검 체크리스트

- 4요소 모두 비어있지 않은가
- request에 행위 동사(요청, 개선, 조치)가 포함되는가
- evidence_span이 원문 범위를 벗어나지 않는가
- entities 라벨이 허용 집합 안에 있는가
