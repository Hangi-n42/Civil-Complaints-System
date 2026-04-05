# Week 4 BE1 인터페이스 문서

문서 버전: v1.0-week4-draft  
작성일: 2026-04-05  
책임: BE1  
협업: BE2, BE3, FE

---

## 1) 책임 범위

Week 4에서 BE1은 단일 RAG baseline의 **평가 기준선과 KPI 산출 계약**을 고정한다.

주요 작업:
1. baseline 평가셋/질문셋 freeze 유지
2. 구조화/메타데이터 품질 점검표 운영
3. Gate A 지표 산출 및 배포

---

## 2) 입력 계약

- `StructuredCivilCase` (Week 2 상속)
- `SearchResult` 샘플 (Week 3 상속)
- `QAResponse` 샘플 (Week 4 공통 상속)

참조:
- `../week3/week3_common_interface.md`
- `week4_common_interface.md`

---

## 3) 출력 계약

### 3.1 평가셋 freeze manifest

```json
{
  "version": "week4-baseline-freeze-1",
  "frozen_at": "2026-04-05T10:00:00+09:00",
  "test_case_count": 500,
  "distribution": {
    "category_balanced": true,
    "region_balanced": true,
    "difficulty_balanced": true
  }
}
```

### 3.2 Gate A KPI 결과

```json
{
  "kpi_id": "KPI-W4-001",
  "report_id": "GATEA-2026-W4-001",
  "recall_at_5": 0.78,
  "four_element_f1": 0.81,
  "citation_alignment": 0.84,
  "latency_avg_ms": 1920,
  "baseline_model": "aihub_baseline"
}
```

---

## 4) 품질 규칙

- `region`, `category`, `created_at` 결측 허용 불가
- 난이도 분포 왜곡 시 freeze 재승인 필요
- KPI 산출 로그 경로를 보고서에 명시

---

## 5) 핸드오프

BE2로 전달:
- 검색용 메타데이터 품질 점검표
- freeze 버전 정보

BE3로 전달:
- KPI 산출 기준/샘플 질의 세트
- citation 정합성 검사 기준

FE로 전달:
- 데모용 기준 질의/정답 요약
- 실패 사례 샘플(표시 검증용)
