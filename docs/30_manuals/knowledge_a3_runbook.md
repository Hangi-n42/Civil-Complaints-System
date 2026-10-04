# A3 근거 기반 온톨로지 변경 검수 모델

- 대상: [#522](https://github.com/Hangi-n42/Civil-Complaints-System/issues/522), [설계 §7.2·7.3·13](../05_plans/company_knowledge/autonomous_ontology_plan.md).
- 분기 기준: 검수된 A2 `ff2f9ed4d114ccc047b02b64da2f38d3749456c9`, `feature/a3-ontology-change-model`. A2 PR #529의 main 병합은 별도로 확인했다.
- 기존 SQLite changeset·decisions·ontology_versions를 확장한다. 신규 테이블은 계보별 검토 head 하나다. 현재 LinkML/Pydantic·표준 라이브러리를 재사용하며 DB·큐·추론기·LLM 호출을 추가하지 않는다. [재사용 기록](../third_party/knowledge_k3_reuse.md).

## 입력과 보존

- 종료된 A2 실행의 result를 명시적으로 변환한다. 같은 run의 재요청은 같은 changeset을 반환한다. 새로운 A2 재개 run은 별도 변경 묶음이며 기존 묶음을 덮어쓰지 않는다.
- `payload_version=2` changeset에 정규화 후보와 오류를 먼저 저장한다. 잘못된 후보가 있어도 조회·수정·보류가 가능하며 독립된 정상 후보의 수락을 막지 않는다. LinkML 컴파일은 preview 또는 닫힌 수락 집합에서 수행한다.
- A2 status, 전체 analysis_result, 원제안, 수정 전후, 성공 revision의 보류와 실패 후 보류, 공백·미처리·분석 선택을 보존한다. 원출력·모델 시도 기록은 원래 run에 그대로 남는다.
- `type/vocabulary` 관측은 미승인 클래스/어휘 변경 후보로 옮긴다. `entity/property_value/unresolved`와 instance 사실은 `reference_material`이다. 관계 방향 미확정과 계층 predicate의 일반 슬롯화는 오류로 남긴다. CSV의 잘못된 분류를 자동 정답으로 수정하지 않는다.
- 서버가 `change_id`, 안정 `target_id`, LinkML symbol을 부여한다. `id_mapping`은 A2 서버 후보 ID와 local_ref를 함께 저장한다. local_ref만으로 다른 단위의 후보를 합치지 않으며 이름 변경은 ID/symbol을 바꾸지 않는다.
- 원문/반례는 기존 evidence·source version·parse·block·span·quote·locator로 검증한다. 줄바꿈을 포함한 정확한 인용을 유지하며 현재 K5 사용 중단 상태와 A2 생성 의존성도 확인한다. 파싱이나 최신 포인터 갱신은 수행하지 않는다.

## 최소 API

기존 `KNOWLEDGE_ENABLED`, `/api/v1/knowledge` prefix와 응답 봉투를 유지한다.

| API | 동작 |
|---|---|
| `POST /runs/{a2_run_id}/ontology-changes` | 저장 A2 결과 변환, changeset ID 반환, LLM 0회 |
| `GET /candidates?changeset_id=…` | 전후·근거·반례·의존·직접 참조·diff·오류·미해결·decisions·현재 head 조회 |
| `POST /changes/{id}/ontology-candidates` | 검수자가 add/update/merge/deprecate 후보 추가. revision, actor, reason, candidates 필요 |
| `POST /changes/{id}/decisions` | accept/modify/edit/defer/reject. v2는 expected revision과 expected head(null 포함), actor, 후보별 reason 필수 |
| `GET /changes/{id}/schema-preview` | 기본은 오류와 의존을 제외한 미승인 파생 스키마. 반복 `candidate_ids` 쿼리로 명시 선택 묶음과 기존 수락 항목의 최종 의존 검증도 가능. 포함/제외 ID 표시, 버전 저장 없음 |
| `GET /ontologies/{id}` | 불변 YAML, JSON Schema, 어휘 registry, 세 해시, 상속 유효 슬롯 조회 |
| `GET /runs/{id}`, `GET /evidence/{id}` | 기존 A2 결과·근거 원문 재조회 |

- `items[].id`는 결정 요청의 `candidate_id`이며 v2 `change_id`와 같다. `target_id`는 정의/관계의 장기 ID다. 새 클래스를 추가한 후 반환 ID를 조회하여 속성·계층의 domain/range/child/parent에 연결한다.
- add는 서버가 새 target을 부여한다. update/merge/deprecate는 해당 실행의 reviewed 기준에 존재하는 target을 지정한다. 같은 대상의 중복 변경은 새 후보 대신 기존 후보를 수정한다. 기존 대상의 종류는 바꿀 수 없다.
- `edit`는 미승인 수정이며 `modify`는 수정 후 수락이다. 서버 ID·원제안·기준 버전은 patch 대상이 아니다. 전후 결정 이력과 actor/reason이 남는다. 수정을 이유로 LLM 재평가를 호출하지 않는다.
- 오류 후보는 `can_accept=false`다. 참조하는 후보가 미수락이면 `unresolved_dependency_ids`를 보여준다. `can_accept_with_dependencies`는 함께 검수할 구조 후보를 찾는 보조값이며 최종 수락 집합 검사를 대신하지 않는다.
- 기각·보류·오류 계층은 현재 검수 구조와 preview에 반영하지 않는다. 기존 계층의 잘못된 수정안은 기준 계층을 지우지 않으며, 기각/보류 결정과 원제안은 이력으로 보존한다.

```json
{
  "expected_changeset_revision": 0,
  "expected_ontology_head_id": null,
  "actor": "검토자",
  "decisions": [{"candidate_id": "oc_조회한_ID", "action": "defer", "reason": "적용 범위 자료 필요"}]
}
```

## 정본·의미·충돌 경계

- 클래스·속성·업무 관계와 is_a/part_of/클래스 별칭은 LinkML 소유다. 어휘 개념·broader/related·어휘 별칭·이전 ID→정본 대응은 같은 불변 버전의 registry 소유다. 별도 편집 가능한 정의 사본을 만들지 않는다.
- 저장 YAML을 직접 SchemaView/JsonSchemaGenerator에 전달한다. 상속과 annotation을 유지한다. schema_hash, registry_hash, 두 값을 결합한 version_hash로 표시·어휘 변경도 식별한다. v1 YAML/ID/조회는 유지하고 registry는 빈 값으로 읽는다.
- 공통 metamodel에는 회사 정의가 없고 선택형 패턴은 정의·관계·적용/비적용·출처·라이선스·버전만 제공한다. 자동 적용·회사 지식 승격은 없다.
- 계층 끝점 종류·자기 참조·is_a 순환을 검사한다. is_a는 단일 부모 계약이며 추가 부모는 보류한다. instance_of는 개체 표본과 유형의 관계로 구별해 보존하며 개별 사실 수락은 K4 대상이다. 클래스 계층으로 변환하지 않는다.
- Builder/기존 Critic의 양방향 supported/refuted/unknown·근거/반례를 보존한다. 양방향 지지는 `possible_equivalence`로 표시하며 자동 병합하지 않는다. unknown을 반증이나 비소속으로 해석하지 않는다. A2 Builder 계층은 검수 전 design_proposal이며 해당 끝점의 CQ/scope만 연결한다.
- design_proposal은 출처와 이유가 필요하지만 정의 자체의 문자 그대로 인용을 강제하지 않는다. statement_type을 rule/instance로 표시해 원문 의무·사실로 포장하는 조합은 거절한다. 이는 법률적 진위 판정이 아니다. 구조 통과, 인용 일치, AI 검수는 의미 정확성의 증거가 아니다.
- 병합은 old ID 삭제가 아닌 deprecated+replaced_by다. A→B 뒤 B→C를 수락하면 새 버전의 A/B는 최종 정본 C를 가리키며 과거 버전의 대응은 바꾸지 않는다. 순환·누락·다른 종류·대체 없는 폐기 대상을 최종 정본으로 수락할 수 없다.
- 폐기된 속성/관계의 정의·ID·원래 필수 조건은 이력에 보존하되 현재 클래스와 상속 슬롯 및 JSON Schema 필수 조건에서는 제외한다. 폐기 클래스의 root items 슬롯도 제거한다.
- 클래스·슬롯·어휘와 추출 매핑·개체·사실·snapshot·추출 run의 직접 ID 참조를 보여준다. 정의 내부 참조는 함께 수정/폐기하여 닫힌 집합으로 수락 가능하다. 기존 운영 소비자의 미해결 참조가 있는 병합/폐기/의미 변경은 보류해야 한다. K8 전이 영향 분석이나 전체 재추출은 수행하지 않는다.
- v2 수락 집합 변경은 SQLite `BEGIN IMMEDIATE` 안에서 revision/head 확인→새 불변 버전→결정→head를 함께 저장한다. 실패하면 모두 rollback한다. 다른 changeset이 head를 갱신하면 expected ID만 바꿔 우회할 수 없고 새 기준 run이 필요하다. 미수락 후보의 edit/defer/reject는 head를 바꾸지 않는다.
- v1 기준은 선택된 ID를 계보의 초기 head로 등록한다. current/contrast 계보와 historical 계보는 A2가 고정한 lineage를 사용한다. K5 active snapshot과 별개다.

## 확인 결과 — 2026-09-30

- Python 3.11.9/macOS. 초기 구현은 A3 집중 20개 포함 관련 회귀 **100 passed**. 근거·scope/버전, v1 조회, 상속, 어휘, 잘못된 후보 보존, 독립 수락, 폐기 동반 변경, 병합 정본, 두 별도 연결의 동시 결정, 결정 저장 실패 rollback, 기존 A1/A2/K3/K4/K5 API 경계를 확인했다.
- PR #530 보완: 폐기 필수 슬롯/클래스 노출, 기각·보류·오류 계층, 연속 병합의 8개 재현이 `bb2d03b`에서 실패한 뒤 수정 후 통과했다. 병합 대상 오류 4개와 독립 AI 전문가 2명의 검수·후속 재현에서 확인한 기존 계층 수정의 기준 그래프 유실 3개(누락 참조·순환·의존 오류)를 추가했다. 검수 구조와 preview가 같은 후보·의존 제외 경로를 사용한다. A3 집중 **35개**, 같은 관련 회귀 **115 passed**. 검수자가 발견한 경로도 수정 후 재확인했다. 추가 LLM 호출·원본 DB 변경은 없으며 실제 업무 의미 검증을 뜻하지 않는다.

```sh
python -m pytest app/tests/unit/test_knowledge_ontology_changes.py app/tests/unit/test_knowledge_ontology_schema.py app/tests/unit/test_knowledge_ontology_run.py app/tests/unit/test_knowledge_discovery_analysis.py app/tests/unit/test_knowledge_discovery_run.py app/tests/unit/test_knowledge_api.py app/tests/unit/test_knowledge_extraction_run.py app/tests/unit/test_knowledge_extraction_store.py app/tests/unit/test_knowledge_snapshots.py -q
```

- 독립 AI 전문가 2명이 저장/원자결정과 온톨로지 의미 계약을 검수했다. range 기본값 유실, 비정상 target/review 입력의 500, 폐기 계층의 잘못된 순환 판정, 성공 revision 보류 승계, 폐기 정본으로 병합, 계층의 명시 근거 승격·무관 CQ 연결, 정의 동반 폐기 거절, A2 기준 어휘/속성 분류 누락과 Critic 원문 의존 누락을 수정하고 재현 검증했다. 현업 사람 검수 효과의 검증은 아니다.
- 실제 입력은 A2 `0fa455ec4eee4db8a089ba6cf7adbee4`의 저장 결과다. 원본 DB를 보존한 별도 사본에서 API 변환→후보 조회→표시명 edit→defer→재조회·근거·preview를 확인했다. 추가 LLM 호출 **0회**, 누적 A2 호출 **10회 그대로**.
- 실제 후보 **9개(클래스 5·관계 4)**, 참고 표본 **3개**. 관계 4개는 방향 미확정/계층 predicate이므로 수락 불가다. A2 partial·실패 1건·원래 보류 1건·전체 result/analysis_units를 유지했다. 동작 확인 보류를 더해 보류 2·미검수 7이며 실제 수락은 0개다.
- 후보 근거 **9건**의 span/quote·locator·version·parse, 참고 표본 근거 **3건**의 원문·위치 일치. 관계 Critic 판단 **7건**도 후보에 연결해 보존했다. source version 2·parse 2·block/evidence 6,220·최신 포인터 불변. ontology_versions 0·head null·운영 assertions/snapshots 불변이다. 원본 DB SHA-256은 `d96c67abc0aeedebbfc2320f6af4d8d25741d1f0079ca3829e9781e7e5a8cd34`다.
- 실제 계층·별칭·병합·폐기 제안이 없으므로 해당 경계와 reviewed 수락은 합성 fixture로 확인했다. 실제 의미 정확성·CSV 오분류 개선·법률 판단·사람 검수 효용을 완료로 보고하지 않는다.
- 증적: 로컬 `data/knowledge/a3_smoke_20260930_final_check/{verification.json,changeset.json,knowledge.db}`. 원본·DB·증적은 Git에 포함하지 않는다. 전문가 대조 사본은 `a3_smoke_20260930_verified/`에 유지한다. 후보별 Critic 연결·전체 의존 승계 보완 후 final_check 사본에서 같은 경로를 재확인했다. 앞선 확인 스크립트의 evidence 응답 필드명(run_id/parse_run_id) 착오는 별도 `a3_smoke_20260930/` 실패 시도에 남겼으며 최종 통과 증적과 구분한다.

## A4/A5 연결과 남은 범위

- A4: 위 후보 API의 before/after, origin, analysis_result의 공백/실패/미처리, 반례·양방향 판단·구조/의미 구분을 카드에 연결한다. edit와 modify의 승인 차이, dependency 및 head 충돌을 화면에 반영한다.
- A5: reviewed v2의 `effective_class_slots`, 안정 target ID와 registry/hash를 K4 전용 매핑·K5 snapshot에 연결한다. 현재 v2 추출/로컬 개체 등록은 명시적으로 미지원 응답이며 기존 v1 경로는 유지한다. 기존 사실·snapshot·매핑을 새 정의로 자동 승격하지 않는다.
- 전체 민원 테스트, 12과제 평가, 다중 모델 비교, Windows 실기, 현업 검토자 시험은 미실시다. UI·운영 활성화·재추출·간접 영향 탐색은 A3 범위 밖이다.
- 현재 사용자 결정이 필요한 사항 없음.

## 필수 문맥과 수정 검수의 현재성 — 2026-10-04

- A2의 필수 문맥 판단과 수정 전후 의미 보존 판단을 후보 origin 및 검토 화면에 유지한다. 선택 구조의 참조를 정본 target ID로 연결하고 전이 의존 정의의 지문을 보존한다. 정본에서 의존 구조가 달라지면 검수 현재성을 무효화하며 K4에는 선택된 구조·정의와 현재성만 전달한다.
- 사람의 정의 수정은 기존 생성·검수 이력을 보존하면서 현재 AI 판정을 해제한다. 요구 전체의 충족 여부, 개별 후보의 구조적 수락 가능 여부, 사람 결정은 별도다. required_meanings가 있다는 사실이나 AI supported를 의미 품질의 보증으로 해석하지 않는다.
