# 업무 지식의 역할별 운영 범위와 저장 교정 표시 — 2026-10-08

시작 커밋은 `c7952c738b489538f63ccb0344bae277516aab8d`다. 기존 실패를 다시 호출하지 않고 실제 저장 요청·응답·receipt와 현행 코드를 대조했다. 이번에 채택한 제품 변경은 **기존 후보로 대체된 교정 결과를 검토 화면에 정확히 표시하는 수정**이다. 새 모델 호출·새 의미 교정·새 승인·새 QA 실행은 모두 0건이다.

## 역할별 증거와 운영 한계

| 역할 | 기존 실제 증거 | 확인 가능한 범위와 한계 |
|---|---|---|
| 1. 원문 의미 해석 | [조건 범위 비교](business_condition_scope_comparison_20261008.md)의 `source_blind`와 `source_exposed` | 기존 해석 없는 원문 읽기는 반납 범위를 확대했다. 기존 해석을 미검증 참고로 노출한 별도 읽기는 일반 구비항목과 지역 번호에 명시된 반납 의무를 구별했다. 원문 해석의 부분 성공이며 안정적인 독립 해석 능력은 입증되지 않았다. |
| 2. 후보 전체의 원문 지지 판정 | 같은 보고서의 좁은 직접 검수·올바른 원문 해석 전달, [의미 범위 비교](business_scope_difference_comparison_20261008.md), [모델·think 비교](business_scope_model_comparison_20261008.md), [구간 연결 비교](business_span_binding_comparison_20261008.md) | c47의 범위 확대를 검출하지 못했다. 구간 연결 첫 실행은 c47을 반환하지 않았고 다음 필수 슬롯 실행은 차이를 검출하지 못했다. 문맥 길이만의 문제로 설명할 근거가 없으며, 새로운 guard나 judge를 더하면 해결된다는 증거도 없다. |
| 3. 오류 위치를 받은 편집 | c116 repair unit `cc91e765f4ed44e1b10bcbc2ede597a0`, receipt `93c2a734b3c74199930312341e763cb0` | 실제 요청에는 `raw.Relation` 오류·이유·원문·정상 c89/c105가 있다. 응답은 `reuse_claim_ids=[c89]`를 반환했고 서버는 기존 정상 후보 대체 분기를 적용했다. 응답에 새 문장·Scope가 있어도 그 문장을 새 claim으로 저장한 사례가 아니다. **오류가 주어진 기존 후보 재사용 성공**과 새 수정문 생성 능력을 구분한다. |
| 4. 수정 후 정상 의미 보존 | c116 이후 assessment `245f637b3ac14d4789e98fed496ea456`의 `preservation_checks`와 [기존 저장·그래프 대조](business_selection_repair_20261007.md) | 같은 R05의 after_repair 판정은 satisfied다. 정상 업무 의미의 위치를 c89/c105로 기록했고 기존 다른 118개 후보 보존과 c116 활성 간선 제거가 이전 대조에서 확인됐다. 이번에는 저장 receipt와 해당 preservation 기록을 읽었다. 이 제한 사례를 모든 교정·모든 정상 의미의 보존 능력으로 일반화하지 않는다. |
| 5. 저장·후속 소비 | c116 저장 run `cedacf0841e540cf83934db6d821140c`, snapshot 및 [후속 R05 QA](business_selection_repair_20261007.md) | 기존 대체·저장·그래프 소비는 확인됐지만 그 상태의 R05 전체 답변은 실패했다. `rechecked`, `satisfied`, `answered` 같은 개별 상태를 종단 의미 품질 통과로 계산하지 않는다. |

위 c47 평가는 제공된 원문 안에서 조건을 확대했는지를 다룬다. 외부 법규의 현재 효력이나 현실 업무의 모든 처리 조건을 확인한 결과가 아니다.

[무라벨 최소 편집 진단](business_native_event_repair_20261008.md)의 run `55d15375fedd43a799e13c11f6a04b5d`도 별도로 구분한다. 오류 위치를 주지 않은 Gemma 편집 제안에서 c47의 Event/Entity는 그대로였고, 정상 c13은 유지됐으며 c46에는 원문에 있는 불필요한 상세사항이 추가됐다. 이는 무라벨 최소 편집의 실패다. 오류 필드·원문 근거를 외부에서 확정해 제공하는 native Event/Entity 편집의 품질은 해당 기록으로 확인할 수 없다. 이전 native 저장 회귀 검사의 합성 응답도 실제 모델 성공으로 세지 않는다.

## 자동 경로와 명시적 검토 경로

- 자동 교정은 `business_run.repair`가 현재 assessment의 허용 대상·오류 필드·근거·보존 의미를 받아 실행한다. 적용 뒤에도 재검수가 필요하다. v8 기본 계약과 명시적으로 선택하는 v13 실험 계약은 그대로 유지했다.
- 업무 지식 승인은 `BusinessDecision`의 `accept_ids`, `actor`, `reason`, `expected_revision`을 명시하는 기존 API와 UI로 수행한다. 자동 검수·교정·대체 저장 자체가 사람의 승인은 아니다.
- 현재 업무 지식 UI/API에는 검토자가 claim의 raw/statement를 직접 편집하는 요청 형식이 없다. 별도 `/changes/.../assertions` 경로는 다른 ontology 변경안 경로이며 업무 지식 직접 편집으로 설명하지 않는다. 이번 작업에서 수동 편집 기능을 새로 만들지 않았다.
- 검토자는 화면에서 원문과 실제 저장 교정 결과를 읽고 승인 대상을 고를 수 있다. 그러나 c47의 오류 검출·전체 답변 품질이 실패한 기록이 있으므로 이것만으로 자동 운영의 신뢰성을 입증할 수 없다.

코드 근거: [교정 적용](../../../app/knowledge/business_run.py), [승인·후속 질의](../../../app/knowledge/business_use.py), [승인 요청](../../../app/knowledge/business_models.py), [API](../../../app/api/routers/knowledge.py), [검토 화면](../../../frontend/components/KnowledgeBusiness.tsx).

## 독립적으로 재현한 표시 결함과 수정

기존 교정 화면은 모든 변경에 `changes[].after.statement`를 그대로 “후”로 표시했다. 정상 후보 재사용 분기는 기존 오류 후보의 이력 문장을 보존하고 `superseded_by`만 기록한다. 실제 c116 receipt는 전·후 statement가 동일하고 c89로 대체돼 있다. 따라서 기존 화면은 실제 대체 결과 대신 옛 오류 문장을 수정 결과로 보여줬다.

변경은 다음 범위에 한정했다.

1. `superseded_by`가 있으면 “기존 후보로 대체”로 표시하고, **해당 repair의 `after` 전체 후보 snapshot**에서 각 대체 ID의 문장·근거를 찾는다. 이후 바뀔 수 있는 현재 `run.claims`로 과거 교정 결과를 재구성하지 않는다.
2. 대체 ID가 snapshot에서 확인되지 않으면 확인 불가를 표시한다. 옛 오류 문장을 새 결과로 되살리지 않는다. 여러 대체 후보도 각각 표시한다.
3. 교정 시점의 대체 저장 내용이며 승인 여부는 별도 검토 결과임을 안내한다. 직접 수정과 누락 복구의 기존 전·후 표시는 유지한다.

`business_run.repair`는 `receipt['after'] = deepcopy(run['claims'])`를 저장한다. 이 기존 역사 snapshot을 사용하며 서버·승인 계약은 바꾸지 않았다. c47/정답 문구/특정 후보 ID를 제품 코드에 넣지 않았다.

실제 저장 receipt에서 만든 [최소 fixture](../../../frontend/__tests__/fixtures/knowledgeBusinessReplacement.json)는 원본 DB 해시·run·repair ID를 포함한다. before/after의 ID·문장·superseded_by와 receipt.after 안의 c89를 투영하고, 근거는 원래 교정 원문 b146으로 제한했다. 합성된 정상/오류 정답을 실제 교정으로 포장한 자료가 아니다. 여러 대체·누락 ID·일반 수정 검사는 별도 합성 경계 검사다.

## 기각한 변경과 미확인 경계

- **후보별 적격성과 전체 출처·요구 승인 보호의 차이:** `eligibility`의 후보 단위 허용과 `decide`의 전체 출처·요구 검사가 다른 이유를 조사했다. 현재 snapshot은 선택 후보뿐 아니라 전체 sources/blocks/requirements/assessments/concepts를 저장한다. 후속 query는 snapshot 전체 출처 제한을 확인하며 document 기준선은 전체 blocks를 입력으로 소비한다. 따라서 승인 검사만 후보 단위로 축소하면 제한된 출처가 후속 입력에 남는다. 현재 구조에서 독립된 승인 결함으로 입증되지 않아 완화를 기각했다. snapshot 분리 설계로 범위를 확장하지 않았다.
- **같은 c47 프롬프트·모델 비교 반복:** 이미 좁은 문맥, 올바른 원문 해석 참조, think, 모델, 명시 구간 연결, 무라벨 편집이 실패했다. 이번에는 재실행하지 않았다.
- **새 judge·차단 조건·고정 정답:** 오류 원인의 입증을 대신하지 못하며 이번 표시 결함에 필요하지 않아 추가하지 않았다.
- **수동 편집기 신설:** 현재 경로의 부재는 확인했으나 승인 요청은 편집 계약이 아니다. 새 기능을 조용히 덧붙이지 않았다.
- **아직 측정하지 않은 편집 경계:** 검증된 오류 필드·근거를 받은 native Event/Entity 편집을 무라벨 탐지와 분리해 측정한 c47 증거는 없다. 필요하면 별도 원인 가설·입력 계약·보존 기준을 먼저 검토해야 한다. 현재 보고서는 그 실험을 수행하거나 성공 가능성을 확정하지 않는다.

## 검증과 원본 보존

| 확인 | 결과 | 의미 |
|---|---|---|
| 표시 수정 전 관련 5개 검사 | 2 실패 / 3 통과 | 실제 c116 대체 표시와 여러 대체/누락 ID에서 옛 문장이 “후”로 표시되는 결함 재현 |
| 표시 수정 후 같은 5개 검사 | 5 통과, 157ms | 기존 2개 및 새 3개 검사. 전·후 실행 수를 합산하지 않음 |
| 변경 컴포넌트·검사 lint | exit 0 | 정적 검사 |
| frontend TypeScript 전체 확인 | exit 0 | 타입 검사, 서버·모델 종단 검증 아님 |
| 실제 fixture의 컴포넌트 정적 렌더와 브라우저 화면 | 확인 | 전 문장, 교정 당시 c89 대체 문장, 원문 줄바꿈, 별도 승인 안내가 표시됨. 전체 앱의 실시간 API 시나리오 검증은 아님 |
| 원본·c116 저장 DB SHA-256 | 기존 해시와 일치 | 아래 JSON에 경로·해시 및 fixture 대응 검사 보존 |

직전 서비스 계약 정렬의 13개 검사는 반복하지 않았다. 이번 UI 검사·렌더를 새 모델 의미 교정이나 #617 전체 통과로 계산하지 않는다. 기존 실패 DB·동결 기록은 읽기 전용으로 확인했고 새 자료는 `data/knowledge/evaluations/business_operating_scope_20261008/`에만 저장했다. 로그는 `ui_before.log`, `ui_after.log`, `ui_lint.log`, `typecheck.log`; 정적 화면은 `repair_preview.html`이다. Git에는 최소 실제 fixture와 이 보고서·[추적 JSON](business_operating_scope_20261008.json)을 남긴다.

## 남은 작업과 사용자 결정

검토 UI 결함은 #617의 기존 작업 범위로 수정했다. 역할별 확인 결과는 원문 해석의 제한 성공, c47 판정·무라벨 편집 실패, c116의 기존 정상 후보 대체·보존 성공, 후속 R05 전체 QA 실패다. 서로 다른 책임의 증거를 한 성공 점수로 합치지 않는다.

다음 품질 작업은 새 호출보다 먼저, c47의 오류 발견과 오류가 주어진 편집을 분리하는 원인 가설 및 실제 운영의 검토 책임을 확정하는 것이다. 부산의 수정 상태에서 정확한 전체 답변을 생성하는 기준도 여전히 남아 있다. [#616](https://github.com/Hangi-n42/Civil-Complaints-System/issues/616), [#617](https://github.com/Hangi-n42/Civil-Complaints-System/issues/617), [#620](https://github.com/Hangi-n42/Civil-Complaints-System/issues/620)은 조회 시 모두 OPEN이며 전체 필수 기준 미완료로 닫지 않았다. merge·배포는 수행하지 않았다. 현재 사용자 결정이 필요한 사항 없음.
