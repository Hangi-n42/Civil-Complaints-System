# Week 7 BE1 인터페이스 문서

문서 버전: v1.0-week7-draft  
작성일: 2026-05-01  
책임: BE1  
협업: FE, BE2, BE3

---

## 1) 책임 범위

Week 7에서 BE1은 Workbench 중앙 민원 목록과 선택 컨텍스트에 필요한 구조화/분류 요약 필드를 제공한다.

주요 작업:
1. 중앙 목록용 summary field 계약 고정
2. 선택 민원 컨텍스트 제공
3. list/detail/panel 간 complaint_id 정합성 보장

---

## 2) 입력 계약

### 2.1 원천 데이터
- `Complaint`
- `AnalyzerOutput`
- `RoutingTrace`

### 2.2 요청 컨텍스트
- `complaint_id`
- `topic_type`
- `complexity_level`
- `complexity_score`

---

## 3) 출력 계약

### 3.1 ComplaintWorkbenchItem

```json
{
  "complaint_id": "CMP-2026-0001",
  "title": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
  "status": "in_progress",
  "topic_type": "welfare",
  "complexity_level": "high",
  "complexity_score": 0.81,
  "summary": "보수 지연과 관리비 이의제기 요청이 함께 포함된 복합 민원",
  "request_segments": ["보수 지연", "관리비 이의제기"]
}
```

필수 필드:
- `complaint_id`
- `title`
- `status`
- `topic_type`
- `complexity_level`
- `complexity_score`
- `summary`
- `request_segments`

---

## 4) 정합성 규칙

- `complaint_id`는 목록/상세/패널 전체에서 동일해야 한다.
- `summary`는 request_segments를 근거로 생성되어야 한다.
- `status` 값은 `pending | in_progress | review_completed`만 허용한다.
- `complexity_score`는 0~1 범위여야 한다.

---

## 5) 리스트 응답 계약

### 5.1 WorkbenchListResponse

```json
{
  "items": [
    {
      "complaint_id": "CMP-2026-0001",
      "title": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
      "status": "in_progress",
      "topic_type": "welfare",
      "complexity_level": "high",
      "complexity_score": 0.81,
      "summary": "보수 지연과 관리비 이의제기 요청이 함께 포함된 복합 민원"
    }
  ],
  "total_count": 1,
  "empty": false
}
```

---

## 6) 에러 계약

Week 7 BE1 에러 코드:
- `LIST_SUMMARY_MISSING`
- `COMPLAINT_ID_MISMATCH`
- `STATUS_INVALID`
- `WORKBENCH_LIST_EMPTY`

---

## 7) 핸드오프

FE로 전달:
- 중앙 목록 렌더용 summary/label 필드

BE2로 전달:
- 선택 민원 기준 panel query key

BE3로 전달:
- 패널 컨텍스트에 사용할 complaint summary 샘플

완료 체크:
- 중앙 목록 필드가 FE 카드 구조와 그대로 일치한다
- 목록/패널 간 complaint_id 충돌이 없다
