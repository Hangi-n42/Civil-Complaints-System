# E2 대상별 응답과 명시 보류 — 2026-10-02

- 범위: [#541](https://github.com/Hangi-n42/Civil-Complaints-System/issues/541), 기준 `4f54909`, `feature/ontology-semantic-improvements`. Ponytail full, 기존 동적 schema·직렬 역할·정규화·A3만 확장했다. 실제 모델 생성 호출 0회, 사람 0명/시간 null.
- 이유: D5 Builder의 빈 연결 목록과 Critic의 관측 판정 누락이 성공한 응답처럼 남았다. 대상별 책임을 명시하고 잘못된 한 항목이 정상 형제 판정까지 폐기하지 않게 한다.
- Builder는 최대 5개 `design_relation_ids` 각각을 bind 또는 구체 사유가 있는 defer로 답한다. 실제 묶음을 5개 상한과 맞추고 비교 전용 대상 0개도 허용한다. 누락·중복·무효 끝점은 해당 관계만 pending으로 남기며 정상 연결과 원관계는 보존한다. 연결·보류·응답 수를 분리하고 미완료/보류는 A3에서도 보류한다.
- Critic은 주검토 observation/관계/계층을 선언하고 비교 후보를 분리한다. observation은 기존 RelationCheck 판정 모델을 재사용한다. supported/refuted는 제공 원문 근거, unknown은 구체 이유가 필요하다. expected/coverage가 같은 주검토 집합이며 잘못된 인용·중복·누락·중복 쟁점은 레코드별로 격리한다. JSON 봉투 자체의 파손은 호출 실패다.
- 생성 schema의 항목 수는 제한하지만, 파싱에서는 중복으로 배열 길이가 늘어났다는 이유만으로 정상 형제를 폐기하지 않는다. schema→파싱→대상별 검증을 분리했다. 새 생성 인용은 source_refs 하나로 단순화했고 legacy exact quote와 기존 coverage/fingerprint 해석은 유지했다.
- `review_outcomes`의 지지/반박/미확인과 유효 응답 coverage를 구분한다. A3에 observation 판정도 보존하고 새 계약의 unknown/refuted는 명시 보류한다. 유효 응답·review_ready는 사람 승인이나 실제 의미 완결이 아니다.

## 확인

- 관련 후보 동일성·A2 분석/복구·A3 및 새 계약 회귀 187개 통과. 새 생성 schema를 통과하는 합성 출력, 일반/비교 전용 묶음, 대상 6개 분할, bind/defer/missing/duplicate/무근거/범위 밖 근거, 정상 형제 판정과 A3 보류를 확인했다. 기존 재개·원장·정본 검수 경계도 포함한다.
- 저장 D5의 성공 Builder 출력에 새 대상 계약만 읽기 전용 적용: C2 대상4/빈 binding4 모두 pending; current 성공5묶음의 대상1·1·0·2·0에서 총4개 pending. 대상0개 묶음에는 허위 누락을 만들지 않는다. 새 생성·원본 재작성·품질 점수 개선이 아니다.
- 공통+역할 지침 길이: Builder **3,082→1,403자**, Critic **3,029→1,542자**. 기존 12,000자 입력·32,768 컨텍스트·4,096 출력·3,000자 종합 여유는 유지했다.
- 새 source_refs schema 합성 통합 입력: Scout1,283 / Concept2,423 / Relation3,644 / Builder3,199 / Critic4,581자. 비교 전용 Builder3,195 / Critic4,080자. 작은 fixture의 실제 조립 길이이며 D5 실자료의 효과는 아니다. 저장 D5의 최종 역할·복구 입력 재조립은 E4 범위다.
- raw 출력·성공 unit·DB·D5 동결 결과·E6 설정·untracked 자료를 보존했다. 로컬 진단 `data/knowledge/semantic_e2_20261002/stored_contract_check.json`은 Git 제외.
- 남은 범위: 원문 끝점/유형 ID의 의미 대조와 Critic 지역/전체 범위는 E3, 필수 문맥 축소는 E4, 실제 검수 비용 예약은 E5다. 의미 중복17개 해결과 실제 모델 완결은 입증하지 않았으며 E6에서 고정 조건으로 확인한다. Windows·전체 민원·사람 효용·새 UI 시험은 수행하지 않았다.
- 다음: E3 #542를 순서대로 진행한다. 현재 사용자 결정이 필요한 사항 없음.
