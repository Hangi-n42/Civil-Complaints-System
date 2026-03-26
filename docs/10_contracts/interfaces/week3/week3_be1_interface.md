# Week 3 BE1 인터페이스 문서

문서 버전: v1.0-week3-draft  
작성일: 2026-03-27  
책임: BE1  
협업: BE2, BE3, FE

---

## 1) 책임 범위

Week 3에서 BE1은 **검색 기초 데이터 준비** 및 **LLM 벤치마크 관리**를 담당한다.

### 1.1 주요 작업
1. 검색용 필드 품질 보완 (카테고리/지역/기간 메타데이터)
2. 모델 비교용 공통 평가셋/질문셋 고정 및 품질 점검
3. 기존 AIHub baseline 모델 벤치마크 실행
4. 벤치마크 결과 수집 및 1차 리포트 생성

---

## 2) 입력 (Week 2 상속)

### 2.1 StructuredCivilCase 객체 (변경 없음)
- Week 2 계약 참고: `10_contracts/interfaces/week2/week2_be1_interface.md`
- 필드: `case_id`, `source`, `created_at`, `observation`, `result`, `request`, `context`, `entities`, `metadata`

### 2.2 인덱싱 대상 케이스
- 총 500건 이상 (기존 50건 + 450건 이상 확장)
- 카테고리별 균형 분배
- 지역별 균형 분배

---

## 3) 출력 : 검색용 메타데이터 강화 (`metadata` 필드)

### 3.1 확장 메타데이터 구조

```json
{
  "case_id": "CASE-2026-000001",
  "source": "aihub_71852",
  "created_at": "2026-03-05T10:15:00+09:00",
  "structured": {
    "observation": "민원 상황",
    "result": "처리 결과",
    "request": "요청사항",
    "context": "배경"
  },
  "metadata": {
    "source_id": "aihub_000001",
    "consulting_category": "도로안전",
    "consulting_turns": 3,
    "consulting_length": 245,
    "region": "서울시 강남구",
    "region_code": "11010",
    "category_code": "ROAD_SAFETY",
    "date_range": "2026-Q1",
    "keywords": ["포트홀", "도로 훼손", "안전"],
    "source_file": "aihub_71852_sample.json"
  }
}
```

### 3.2 신규 필드 (Week 3 추가)
- `region` (string, 필수): "서울시 강남구" 형식
- `region_code` (string, 권장): 지역 코드 (예: "11010")
- `category_code` (string, 권장): 카테고리 단축코드
- `date_range` (string, 권장): 년-분기 (예: "2026-Q1")
- `keywords` (array, 권장): 추출 키워드 목록

### 3.3 메타데이터 품질 기준
- ✅ 모든 케이스에 `region` 필드 필수
- ✅ 모든 케이스에 `consulting_category` 필수
- ✅ `keywords` 최소 2개 이상 권장
- ✅ 검색 필터링 가능해야 함

---

## 4) 벤치마크 평가셋 관리

### 4.1 평가셋 구조 (`evaluation_set.json`)

```json
{
  "metadata": {
    "created_at": "2026-03-27T10:00:00+09:00",
    "total_test_cases": 500,
    "distribution": {
      "by_category": {
        "도로안전": 100,
        "건설공사": 80,
        "상수도": 120,
        "가로등": 60,
        "기타": 140
      },
      "by_region": {
        "서울시": 200,
        "경기도": 150,
        "인천시": 150
      }
    }
  },
  "test_cases": [
    {
      "case_id": "CASE-2026-000001",
      "query": "포트홀 신고 절차",
      "expected_scenario": "도로 훼손 관리",
      "difficulty": "easy"
    },
    {
      "case_id": "CASE-2026-000150",
      "query": "단수도 요금 이의 제기 방법",
      "expected_scenario": "요금 분쟁 해결",
      "difficulty": "medium"
    }
  ]
}
```

### 4.2 평가셋 필드
- `case_id` (string): 테스트할 구조화된 민원 ID
- `query` (string): 사용자가 입력할 자연어 질문
- `expected_scenario` (string): 질문의 예상 시나리오
- `difficulty` (string: "easy" | "medium" | "hard"): 난이도

### 4.3 평가셋 배포
- 경로: `docs/40_delivery/week3/model_test_assets/evaluation_set.json`
- 크기: 500건
- 카테고리 균형: 4대 카테고리(도로, 건설, 상수도, 가로등) + 기타

---

## 5) 벤치마크 실행 및 리포트

### 5.1 벤치마크 스크립트
- 스크립트: `scripts/run_week3_model_benchmark.py`
- 설정: `configs/week3_model_benchmark.yaml`
- 실행 명령:
  ```bash
  python scripts/run_week3_model_benchmark.py \
    --config configs/week3_model_benchmark.yaml \
    --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json \
    --model aihub_baseline
  ```

### 5.2 혼합 실행 (병렬 처리)
- BE1: aihub_baseline 테스트
- BE2: skt/A.X-4.0-Light 테스트
- BE3: exaone3.5 + gemma3 + phi4-mini 테스트

### 5.3 수집 메트릭
- 평균 응답 시간 (ms)
- P95 응답 시간 (ms)
- JSON 파싱 성공률 (%)
- 총 테스트 건수 vs 성공/실패 건수

### 5.4 리포트 출력
- 경로: `logs/evaluation/week3/model_benchmark_report_final.json`
- 형식: JSON + Markdown 요약본
- 포함: 모델별 메트릭 + 비교표 + 권장사항

---

## 6) 평가셋 품질 체크리스트

- [ ] 500건 모두 유효한 case_id 참조
- [ ] 모든 케이스에 query 필드 포함
- [ ] 난이도별 분포: easy 40%, medium 40%, hard 20%
- [ ] 카테고리별 균형 검증
- [ ] 지역별 균형 검증
- [ ] 중복 쿼리 확인

---

## 7) 벤치마크 최종 체크리스트

- [ ] 5종 모델 모두 설치 확인
- [ ] 평가셋 500건 준비 완료
- [ ] BE1/BE2/BE3 병렬 테스트 실행
- [ ] 단일 모델 테스트 완료 (20~30분 소요)
- [ ] 전체 리포트 통합 (2026-03-31 예정)
