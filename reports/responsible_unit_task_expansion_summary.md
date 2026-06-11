# responsible_unit task 확장 검증 요약

## 문제 원인 분석

- `responsible_unit_holdout1000_query_eval_after_prior_v4.json` 기준 miss 339건 중 일부는 마스터 task 라벨이 짧아 검색 신호가 부족했다.
- 확장해도 안전한 축은 실제 부산시 마스터 업무와 직접 연결되는 제도/시설명이다.
  - 건설행정과: 종합건설업, 전문건설업, 건설기계, 하도급
  - 주택정책과: 주택정책, 주택 부동산 정책
  - 건축정책과: 건축관련 협의사항, 한국건축규정, 건축기본계획
  - 도시계획과: 도시계획, 도시관리계획, 도시기본계획
  - 공원여가정책과: 공원여가, 도시공원, 공원녹지
  - 푸른숲도시과: 산림, 산지, 숲길, 도시숲
- 확장하면 위험한 축은 자동 alias 라벨 노이즈다.
  - `건설과 -> 건설행정과`: 실제 본문이 도로, 하수, 맨홀, 보도 정비인 케이스가 많음
  - `도시활력지원과 -> 도시공간활력과`: 실제 본문이 도시계획/시설계획인 케이스가 많음
  - `녹색도시과`, `생활교통복지과`, `생태하천과` 등도 부산시 본청 마스터와 1:1 대응이 불안정함

## 설계

- 원본 `data/departments/busan_departments_master.json`는 수정하지 않았다.
- Chroma metadata의 표시용 `task`는 원문을 유지한다.
- 임베딩/BM25 대상 `document`만 `expand_department_task_text()`에서 확장한다.
- 확장어는 부서 단위 전체 살포가 아니라 task 트리거 기반으로만 붙인다.
- `도시공간활력과`는 마스터 업무상 노후계획도시/도시재생 중심으로만 확장하고, 도시계획/도시개발 일반 키워드는 붙이지 않았다.

## 구현

- `app/structuring/department_assigner.py`
  - `_TASK_TEXT_EXPANSION_RULES` 추가
  - `_task_expansion_terms()` 추가
  - `expand_department_task_text()`에서 기존 enrichment 확장 뒤 task-trigger 확장어 병합
- `app/tests/unit/test_department_assigner.py`
  - 원본 task metadata 보존 테스트
  - 기대 확장어 포함 테스트
  - 무관 부서 확산 방지 테스트
  - 위험 alias 노이즈 방지 테스트
  - BM25 sparse-only hit 테스트

## 인덱스 재빌드

- 이번 변경은 검색용 task document가 바뀌므로 `busan_departments_v1` 재빌드가 필요하다.
- 재빌드 결과: `{'departments': 118, 'tasks': 2114, 'skipped': 0}`
- 재빌드 후 Chroma count: `2114`
- 샘플 확인 결과 `metadata.task`는 원문이고 `document`에만 확장어가 포함됨.

## 검증 결과

| 평가 대상 | 기준 | Recall@3 | Top1 | MRR@3 |
| --- | --- | ---: | ---: | ---: |
| docs current Chroma metadata | civil_cases_v1 기존 적재값 | 0.4240 | 0.2330 | 0.3152 |
| query baseline | task 확장 전 최초 | 0.5490 | 0.3350 | 0.4322 |
| query after prior v4 | query prior 개선 후 | 0.6610 | 0.4730 | 0.5598 |
| query after task expansion | 최종 | 0.7070 | 0.5320 | 0.6095 |
| human-labeled 100 query | 회귀 확인 | 1.0000 | 0.9158 | 0.9526 |

## 테스트

- `.\civil\Scripts\python.exe -m pytest app\tests\unit\test_department_assigner.py app\tests\unit\test_eval_responsible_unit.py -q`
- 결과: `37 passed`

## 남은 리스크

- holdout 1000은 자동 alias 라벨셋이라 85%를 안전하게 달성하기 어렵다.
- 남은 miss는 `건설과`, `도시활력지원과`, `생태하천과`, `철도교통과`, `생활교통복지과` alias에 집중되어 있다.
- 이들을 강제로 맞추는 확장은 운영 query 담당부서 신호를 오염시킬 수 있어 보류했다.

## BE2 전달 해석

- BE1 query-side `responsible_unit` 신호는 task 확장 후 Recall@3 0.7070까지 개선됐다.
- 이 개선은 `busan_departments_v1` 부서 인덱스 재빌드가 있어야 반영된다.
- `civil_cases_v1` 문서 metadata의 `responsible_units`는 이번 부서 인덱스 재빌드만으로 바뀌지 않는다.
- BE2가 문서 metadata까지 최신 BE1 결과로 쓰려면 원천 데이터 재구조화 후 `civil_cases_v1` 재색인이 별도로 필요하다.
- 그래도 현재 결론은 hard filter가 아니라 soft signal로 쓰는 것이 안전하다.
