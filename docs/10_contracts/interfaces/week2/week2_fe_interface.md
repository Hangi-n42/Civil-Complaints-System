# Week 2 FE 인터페이스 문서

문서 버전: v1.3-week2-final  
작성일: 2026-03-19  
최신화: 2026-03-25 (search->qa doc_id 중계 규칙, 422 래퍼 처리 반영)  
책임: FE  
협업: BE1, BE3

## 1) 책임 범위

- 업로드/구조화 결과/검증 상태 UI 렌더링
- API 응답 성공/실패 상태를 일관 표시
- 필드명 변경 없이 화면 모델 매핑

## 1.1) 현재 상태 및 제약 (Week 2)

**POST /api/v1/ingest, /api/v1/structure 엔드포인트 미구현:**
- Week 2 기준 BE1 API는 구조화 엔드포인트 미제공
- 현재 FE 화면은 `build_structure_success_payload()` 시뮬레이션 함수로 동작
- 실제 API 연동은 Week 3 이후 예정
- FE는 아래 계약을 미리 준수하도록 구현 (API 준비 시 즉시 연동 가능)

**검색/QA는 실제 API 연동 완료:**
- POST /api/v1/search, /api/v1/qa 엔드포인트 구현 완료
- FE 검색/응답 화면은 실제 BE API 호출 사용 중
- search 결과를 qa 요청으로 중계할 때 `doc_id`는 검색 응답의 `doc_id`를 그대로 전달한다 (`id` 사용 금지)

## 2) FE 입력 계약 (from API, Week 3 예정)

### 2.1 Ingest 결과 뷰모델 (POST /api/v1/ingest 응답)

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

### 2.2 Structure 결과 뷰모델 (POST /api/v1/structure 응답)

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

## 3) 시뮬레이션 (현재 Week 2 구현 상태)

**Ingest/Structure 시뮬레이션 동작:**
- 파일 업로드/구조화 화면은 `build_structure_success_payload()` 함수로 생성된 샘플 데이터 사용
- 함수 위치: [app/ui/Home.py#L496](app/ui/Home.py#L496)
- 실제 API 호출 없이 하드코딩된 시나리오 JSON 반환
- **Purpose**: 실제 BE API 구현 전 FE 레이아웃 테스트, 필드 매핑 검증

**예시 시뮬레이션 페이로드:**
```python
# app/ui/Home.py 중
def build_structure_success_payload(scenario_key: str, source_text: str) -> dict:
    """구조화 결과 시뮬레이션 (by scenario)"""
    return {
        "success": True,
        "request_id": f"DEMO-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "data": {
            "structured_count": len(results),
            "results": [StructuredCivilCase 형태의 샘플 객체]
        }
    }
```

**API 준비 완료 시 마이그레이션:**
- 시뮬레이션 함수 호출 → 실제 `/api/v1/ingest`, `/api/v1/structure` POST 호출로 변경
- 필드명/스키마는 현재 시뮬레이션 기준으로 이미 맞춰져 있음 (즉시 연동 가능)
- 응답 처리 로직은 변경 없음

## 4) 변수명 충돌 방지 규칙

- FE state key도 API 필드명 그대로 사용 (`structured_count`를 `count`로 축약 금지).
- `validation.is_valid`는 `status`와 혼용하지 않는다.
- 4요소 렌더링 카드 key는 `observation|result|request|context`만 사용.
- 에러 배너는 `error.message`를 그대로 노출한다 (임의 키 재매핑 금지).
- 422 검증 오류도 `success=false` 실패 래퍼(`error.code=VALIDATION_ERROR`)로 처리한다.
- search -> qa 중계 payload는 `doc_id`를 유지한다 (`id`로 재매핑 금지).
- `entities.label` 렌더링/필터 기준은 서버 허용 5종(`LOCATION`, `TIME`, `FACILITY`, `HAZARD`, `ADMIN_UNIT`)으로 고정한다.
- `validation.warnings`의 `entity_label_normalized:<OLD>-><NEW>`는 데이터 품질 로그 패널에 노출 가능해야 한다.

## 5) FE 완료 체크

- [x] 성공/실패 상태 분기 렌더링 일관화
- [x] 검증 배지(`is_valid`)와 에러 배너(`error.message`) 동시 표시 테스트
- [x] API 연동 준비: 시뮬레이션 로직을 `/api/v1/structure` 호출로 교체 가능하도록 설계
- [ ] 50건+ 처리 시 목록 가상화/페이징으로 UI 지연 방지
- [ ] `/api/v1/ingest`, `/api/v1/structure` 구현 후 실연동 전환 검증
