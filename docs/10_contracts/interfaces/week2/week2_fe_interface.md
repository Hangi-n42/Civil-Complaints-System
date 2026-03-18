# Week 2 FE 인터페이스 문서

문서 버전: v1.0-week2  
작성일: 2026-03-19  
책임: FE  
협업: BE1, BE3

## 1) 책임 범위

- 업로드/구조화 결과/검증 상태 UI 렌더링
- API 응답 성공/실패 상태를 일관 표시
- 필드명 변경 없이 화면 모델 매핑

## 2) FE 입력 계약 (from API)

### 2.1 Ingest 결과 뷰모델

```json
{
  "success": true,
  "request_id": "REQ-20260319-AB12CD34",
  "timestamp": "2026-03-19T10:00:00+09:00",
  "data": {
    "ingested_count": 50,
    "skipped_count": 2,
    "records": [
      {"case_id": "CASE-2026-000123", "status": "accepted", "normalized_text": "..."}
    ]
  }
}
```

### 2.2 Structure 결과 뷰모델

```json
{
  "success": true,
  "request_id": "REQ-20260319-AB12CD34",
  "timestamp": "2026-03-19T10:00:00+09:00",
  "data": {
    "structured_count": 50,
    "results": [
      {
        "case_id": "CASE-2026-000123",
        "observation": {"text": "...", "confidence": 0.9, "evidence_span": [0, 10]},
        "result": {"text": "...", "confidence": 0.8, "evidence_span": [11, 20]},
        "request": {"text": "...", "confidence": 0.9, "evidence_span": [21, 30]},
        "context": {"text": "...", "confidence": 0.7, "evidence_span": [31, 40]},
        "validation": {"is_valid": true, "errors": [], "warnings": []}
      }
    ]
  }
}
```

## 3) 변수명 충돌 방지 규칙

- FE state key도 API 필드명 그대로 사용 (`structured_count`를 `count`로 축약 금지).
- `validation.is_valid`는 `status`와 혼용하지 않는다.
- 4요소 렌더링 카드 key는 `observation|result|request|context`만 사용.
- 에러 배너는 `error.message`를 그대로 노출한다 (임의 키 재매핑 금지).

## 4) FE 완료 체크

- [ ] 성공/실패 상태 분기 렌더링 일관화
- [ ] 검증 배지(`is_valid`)와 에러 배너(`error.message`) 동시 표시 테스트
- [ ] 50건+ 처리 시 목록 가상화/페이징으로 UI 지연 방지
