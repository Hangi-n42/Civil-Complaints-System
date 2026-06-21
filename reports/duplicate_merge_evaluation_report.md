# Duplicate Merge Recommendation Layer 평가 보고서

## 1. 실험 계획

- 기준선 확인: 기존 `test_duplicate_merger.py`로 API 계약, 상태 전이, confirmed 전용 draft payload를 재확인한다.
- 다차원 시나리오 평가: 정상 중복, 담당부서 충돌, 요청 유형 충돌, 시간창 초과, 낮은 근거, 안전/단순문의 혼합, PII payload 마스킹을 함께 검증한다.
- 제3자 관점 점검: 성공 케이스 통과만 보지 않고 false positive 방지, blocker의 확정 차단, FE contract 노출 여부를 확인한다.
- 과잉 테스트 방지: 외부 LLM, DB, 대규모 부하 테스트는 제외하고 100건 이하 합성 배치로 O(n^2) 경향만 확인한다.

## 2. 계획 평가 및 보완

초기 계획은 정상 후보 생성과 API 계약 검증에 치우칠 수 있었다. 운영 관점에서는 서로 다른 사건이 하나로 묶이는 false positive가 더 위험하므로 다음 항목을 보강했다.

- blocker risk가 `confirm`을 실제로 막는지 확인한다.
- candidate 상태에서 `draft_reply`가 차단되는지 확인한다.
- 광역 위치명 또는 같은 접두어 장소명 때문에 과잉 그룹화되는지 별도 probe로 확인한다.
- 취약점 probe는 운영 테스트를 깨뜨리지 않도록 `xfail(strict=False)`로 문서화한다.

## 3. 작업 내용

- `app/tests/unit/test_duplicate_merger_evaluation_matrix.py` 추가
  - 정상 중복 그룹 생성 및 대표 민원 선정
  - 담당부서 충돌 blocker
  - 단속/보상 요청 혼합 및 법적 권리관계 blocker
  - 72시간 초과 접수 간격 warning
  - 구조화 근거 부족 warning
  - 안전 위험 민원과 단순 문의 혼합 blocker
  - confirmed 그룹의 PII-safe draft payload
  - 광역 위치명 과잉 후보화 위험 `xfail`

운영 코드는 수정하지 않았다.

## 4. 검증 결과

### 테스트

```text
C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe -m pytest app/tests/unit/test_duplicate_merger.py
6 passed

C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe -m pytest app/tests/unit/test_duplicate_merger.py app/tests/unit/test_duplicate_merger_evaluation_matrix.py
8 passed, 1 xfailed

C:\Projects\AI-Civil-Affairs-Systems\civil\Scripts\python.exe -m pytest app/tests/unit/test_duplicate_merger.py app/tests/unit/test_duplicate_merger_evaluation_matrix.py app/tests/unit/test_complaint_intelligence.py
29 passed, 1 xfailed
```

글로벌 Python에서는 `yaml` 의존성이 없어 테스트 수집이 실패했다. 기존 프로젝트 가상환경인 `civil` 실행기로 검증했다.

### 합성 배치 성능

같은 접두어를 가진 아파트명을 5건 단위 cluster로 생성해 100건 이하에서 측정했다.

| 입력 건수 | 실행 시간 | 생성 그룹 수 |
| ---: | ---: | ---: |
| 10 | 9.16 ms | 2 |
| 30 | 70.30 ms | 6 |
| 60 | 320.39 ms | 7 |
| 100 | 808.27 ms | 4 |

100건까지는 로컬 단위 평가에서 1초 내로 처리됐다. 다만 그룹 수가 기대 cluster 수보다 줄어드는 현상이 있어, 속도보다 위치 휴리스틱에 따른 과잉 병합 위험이 더 중요한 관찰점이다.

## 5. 관찰된 성능

- 정상 중복 후보 생성, 대표 민원 선정, evidence/risk_flags/allowed_actions/blocked_actions 계약은 안정적으로 동작했다.
- blocker risk가 있는 후보는 `confirm`에서 409 성격의 충돌로 차단된다.
- candidate/rejected/split 상태에서는 draft payload가 차단되고, confirmed 상태에서만 PII-safe payload가 생성된다.
- 100건 이하의 소규모 배치에서는 응답 시간이 실무 검토용 배치 분석에 무리가 없어 보인다.

## 6. 미흡한 부분

1. 위치 판단이 아직 거칠다.
   - `region`이 같으면 세부 장소가 달라도 `exact`가 될 수 있다.
   - 같은 접두어를 가진 장소명은 `nearby`로 묶일 가능성이 높다.
   - 이로 인해 서로 다른 세부 장소의 소음 민원이 하나의 후보로 묶일 수 있다.

2. union-find 기반 그룹화가 과잉 병합을 키울 수 있다.
   - A-B, B-C가 후보이면 A-C 직접 근거가 약해도 같은 그룹이 될 수 있다.
   - 그룹 생성 후 전체 member pair에 대한 hard gate 재검사가 필요하다.

3. 요청 유형 분류가 키워드 기반이다.
   - `other`가 포함된 요청 유형 차이는 pair mismatch로 잡히지 않는다.
   - 모호한 표현은 `LOW_EVIDENCE`와 함께 더 보수적으로 낮출 필요가 있다.

4. 현재 성능 평가는 labeled dataset 기반 precision/recall이 아니다.
   - 이번 평가는 회귀/계약/합성 시나리오 중심이다.
   - 실제 운영 성능을 말하려면 샘플링된 실제 민원 또는 라벨링된 평가셋이 필요하다.

5. O(n^2) pair scoring 구조다.
   - 100건까지는 충분히 빠르지만, 수백~수천 건 배치에서는 blocking key를 더 강하게 적용해야 한다.

## 7. 권장 개선 순서

1. 위치 hard gate 개선
   - 광역 행정구역만 같은 경우 `exact`가 아니라 `ambiguous`로 낮춘다.
   - 세부 location entity가 서로 다르면 공유 region보다 conflict/ambiguous를 우선한다.
   - 첫 두 글자 prefix 기반 `nearby` 판정은 도로명/시설명 토큰 단위로 제한한다.

2. 그룹 생성 후 all-pairs verifier 추가
   - union-find로 묶인 그룹 내부의 모든 pair를 다시 검사한다.
   - 미평가 pair에서 LOCATION_MISMATCH, REQUEST_TYPE_MISMATCH, DEPARTMENT_MISMATCH가 나오면 group-level risk에 반영한다.

3. request type classifier 보강
   - `other`와 명시 유형의 혼합은 최소 `LOW_EVIDENCE` 또는 `REQUEST_TYPE_MISMATCH` 후보로 남긴다.
   - 단속/보상/시설개선/안전조치 키워드 사전을 실제 민원 표현으로 확장한다.

4. 라벨링 평가셋 구축
   - true duplicate, same keyword different event, same event different request, PII risk 사례를 최소 50~100쌍으로 구성한다.
   - precision, recall, blocker recall, draft payload PII leak rate를 별도 지표로 본다.
