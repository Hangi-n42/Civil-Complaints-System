# responsible_unit content-aware 최종 평가 리포트

## 완료 상태

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| 마스터 업무 라벨 확장 | 완료 | 검색용 task document 확장 계층 적용, 원본 task metadata 보존 |
| 부서 인덱스 재빌드 | 완료 | `busan_departments_v1` count 2,114 |
| 기존 기준 재평가 | 완료 | human 100 및 holdout1000 auto query/docs 산출물 확인 |
| holdout1000 content-aware alias 재정제 | 완료 | 848건 평가 본파일, 152건 review 분리 |

## content-aware 라벨셋 검증

- 기존 auto holdout: 1,000건
- content-aware 평가 본파일: 848건
- review 대상: 152건
- label_confidence: `{"medium": 627, "high": 221}`
- 기존 auto gold와 달라진 평가 본파일 row: 93건
- 평가 본파일 gold는 모두 `busan_departments_master.json`에 존재하는 부서명이다.
- `needs_review` 152건은 자동 규칙으로 확정하지 않고 지표에서 제외했다.
- 본파일에는 `low`와 `NONE` 케이스가 없고, high+medium 전체가 content-aware 평가 기준이다.

## 평가 결과

| 기준 | total | eval rows | Recall@3 | Top1 | MRR@3 | miss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| human 100 query | 100 | 95 | 1.0000 | 0.9158 | 0.9526 | 0 |
| holdout1000 auto query | 1000 | 1000 | 0.7070 | 0.5320 | 0.6095 | 293 |
| holdout1000 content-aware query high+medium | 848 | 848 | 0.8373 | 0.6427 | 0.7298 | 138 |
| holdout1000 content-aware query high only | 221 | 221 | 0.8643 | 0.6380 | 0.7421 | 30 |
| holdout1000 content-aware query medium only | 627 | 627 | 0.8278 | 0.6443 | 0.7254 | 108 |
| docs current Chroma metadata auto | 1000 | 1000 | 0.4240 | 0.2330 | 0.3152 | 576 |
| docs current Chroma metadata content-aware | 848 | 848 | 0.4929 | 0.2807 | 0.3730 | 430 |

주의: content-aware 라벨셋은 자동 재정제 결과이며 최종 정답셋이 아니다. 운영 정확도가 아니라 기존 auto alias보다 더 타당한 자동 평가 기준으로 해석한다.

## query/docs 해석

- query-side `DepartmentAssigner.assign()`는 content-aware high+medium 기준 Recall@3 0.8373, Top1 0.6427, MRR@3 0.7298이다.
- current Chroma docs metadata는 같은 content-aware 기준 Recall@3 0.4929, Top1 0.2807, MRR@3 0.3730이다.
- docs metadata는 현재 `civil_cases_v1`에 저장된 값이며, 이번 부서 인덱스 재빌드만으로 갱신되지 않는다.
- 따라서 BE2는 query 담당부서 신호와 docs metadata 신호를 같은 품질로 보면 안 된다.

## 잔여 오답 상위 부서

### query miss by gold

| gold | miss |
| --- | ---: |
| 하천관리과 | 18 |
| 대중교통과 | 16 |
| 주택정책과 | 11 |
| 여성가족과 | 10 |
| 도시계획과 | 9 |
| 미래에너지산업과 | 8 |
| 도로안전과 | 7 |
| 건강정책과 | 7 |
| 도시정비과 | 6 |
| 중소상공인지원과 | 5 |

### docs metadata miss by gold

| gold | miss |
| --- | ---: |
| 도시계획과 | 88 |
| 건축정책과 | 61 |
| 주택정책과 | 61 |
| 창업벤처담당관 | 31 |
| 하천관리과 | 24 |
| 건강정책과 | 23 |
| 대중교통과 | 18 |
| 도시정비과 | 18 |
| 생활체육과 | 14 |
| 여성가족과 | 13 |

### review 대상 상위 카테고리

| category | review |
| --- | ---: |
| 건설과 | 24 |
| 건설산업과 | 18 |
| 도로과 | 14 |
| 철도교통과 | 13 |
| 도시활력지원과 | 12 |
| 건설정책과 | 12 |
| 구조물관리과 | 8 |
| 도로관리과 | 8 |
| 녹지과 | 7 |
| 시설안전과 | 6 |

## 대표 query miss 샘플

### holdout1000-auto-0031-src-000244

- category: 기후환경본부 대기정책과
- gold: `환경정책과`
- predictions: `탄소중립정책과`, `대중교통과`, `자원순환과`
- confidence: medium
- evidence: `기후환경본부 대기정책과`
- query: 경유차 매연저감장치 필터교체 관련

### holdout1000-auto-0038-src-800705

- category: 생태하천과
- gold: `하천관리과`
- predictions: `공원여가정책과`, `도로계획과`, `도로안전과`
- confidence: high
- evidence: `강`
- query: 하천변 조경사업 침수 반복으로 활용도 개선 요청

### holdout1000-auto-0056-src-300450

- category: 도시활력지원과
- gold: `시설계획과`
- predictions: `도시계획과`, `건설행정과`, `도로계획과`
- confidence: medium
- evidence: `도시계획시설사업`, `실시계획인가`, `사업시행자지정`, `도시계획시설`
- query: 도시계획시설 도로사업 시행자 지정 여부 질의

### holdout1000-auto-0069-src-501469

- category: 창업
- gold: `중소상공인지원과`
- predictions: `도시공간활력과`, `도로계획과`, `건설행정과`
- confidence: medium
- evidence: `신용보증`
- query: 서울신용보증재단 지원자금 신청 방법 문의

## 리스크

- content-aware 라벨셋은 자동 규칙 기반이다. 152건 review와 주요 miss 부서는 사람 검수 전까지 최종 정답셋으로 단정하면 안 된다.
- docs metadata는 current Chroma `civil_cases_v1` 적재값이며, query-side 최신 담당부서 검색 품질을 반영하지 않는다.
- 하천/공원/도로처럼 현장 시설과 관리 주체가 겹치는 민원은 task 확장만으로 완전히 분리하기 어렵다.
- 부산시 본청 마스터에 적절한 소관이 없거나 기초지자체/타기관 소관인 케이스는 `NONE`/review 정책이 필요하다.

## BE2 전달사항

- `responsible_unit`은 hard filter가 아니라 soft rerank/metadata signal로만 사용하는 것을 권장한다.
- content-aware 기준 query 신호는 개선됐지만, docs metadata는 현재 컬렉션 적재값이라 query-side 최신 인덱스 품질과 차이가 크다.
- BE2가 docs metadata까지 최신 BE1 담당부서로 쓰려면 원천 데이터 재구조화 후 `civil_cases_v1` 또는 후보 컬렉션 재색인이 필요하다.
- 재측정 시 `reports/responsible_unit_holdout1000_content_aware_query_eval.json`과 `reports/responsible_unit_holdout1000_content_aware_doc_metadata_eval.json`을 비교한다.
- content-aware 라벨셋은 평가셋 정답 품질 개선용 자동 기준이며, 최종 운영 품질 판단 전 `needs_review` 152건과 주요 miss 부서 중심의 사람 검수가 필요하다.

## 인덱스/재색인 필요 여부

- 부서 인덱스 `busan_departments_v1`는 이번 task expansion 반영을 위해 재빌드 완료했다.
- 문서 검색 컬렉션 `civil_cases_v1`의 case metadata는 이번 작업만으로 갱신되지 않는다.
- BE2 운영 검색에서 docs metadata 품질을 높이려면 BE1 구조화 결과를 반영한 case 재색인이 별도 필요하다.

## 산출물

- `data/departments/eval/responsible_unit_holdout1000.content_aware.jsonl`
- `data/departments/eval/responsible_unit_holdout1000.content_aware.review.jsonl`
- `reports/responsible_unit_holdout1000_content_aware_query_eval.json`
- `reports/responsible_unit_holdout1000_content_aware_doc_metadata_eval.json`
- `reports/responsible_unit_holdout1000_content_aware_labeling_report.md`
- `reports/responsible_unit_content_aware_final_report.json`
- `scripts/build_responsible_unit_content_aware_holdout.py`
- `scripts/eval_responsible_unit_doc_metadata.py`
