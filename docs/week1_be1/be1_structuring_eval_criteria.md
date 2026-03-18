# BE1 Week1 구조화 평가 기준 초안

문서 버전: v1.0  
작성일: 2026-03-18

## 1. 평가 목적

구조화 파이프라인의 품질을 필드 단위로 정량화하여 개선 우선순위를 결정한다.

## 2. 평가 단위

- 케이스 단위: `case_id`
- 필드 단위: `observation`, `result`, `request`, `context`
- 보조 단위: `entities.label`, `entities.text`

## 3. 판정 방식

### 3.1 4요소 필드 일치 판정

- Exact Match: 정답 문자열과 예측 문자열 완전 일치
- Relaxed Match: 정규화 후 토큰 F1 >= 0.7
- KPI 계산은 Relaxed Match 기준

### 3.2 엔티티 일치 판정

- `label`과 `text`가 모두 일치하면 True Positive
- 라벨만 일치/텍스트 불일치는 False Positive

## 4. 지표 정의

각 필드별로 다음을 계산한다.

- Precision: $\frac{TP}{TP + FP}$
- Recall: $\frac{TP}{TP + FN}$
- F1: $\frac{2PR}{P + R}$

프로젝트 KPI는 4요소 필드 F1의 Macro 평균으로 계산한다.

## 5. KPI 기준

- 구조화 품질 KPI: 필드 단위 F1 >= 0.72
- 보조 지표:
  - 스키마 검증 통과율 >= 95%
  - 빈 필드율(4요소) <= 10%

## 6. 샘플셋 기준(수작업 20건)

- 기관 다양성: 중앙/지방/공공기관 포함
- 유형 다양성: 도로, 환경, 교통, 안전, 문화 포함
- 난이도 분포:
  - 짧은 민원 6건
  - 중간 길이 8건
  - 장문 법령형 6건

## 7. 평가 산출물

- 필드별 Precision/Recall/F1 표
- 실패 사례 Top 10
- 노이즈 패턴 목록(정제 규칙 개선 입력)

## 8. 구현 연결

- 평가 스크립트: `scripts/evaluate_structuring.py`
- 결과 저장: `reports/structuring_eval_week1.md` 또는 JSON
