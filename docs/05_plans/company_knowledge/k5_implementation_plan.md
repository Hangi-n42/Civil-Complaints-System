# K5 구현 계획 — 검토된 지식의 스냅샷·사용 상태·기본 조회

- 기준일: 2026-09-28. **아래 계획에 따른 K5 구현·공고군 확인 완료.** 구현 이슈 #503. [실제 결과·한계](../../30_manuals/knowledge_k5_runbook.md). 아래 절차·추정은 구현 전 계획 기록이다.
- 근거: [PRD FR-06·08·09](../../00_overview/company_knowledge_prd.md), [최소 계약](contracts.md), [K4 보완·최종 검토 결과](../../30_manuals/knowledge_k4_quality_result.md).
- Ponytail 적용: 기존 SQLite·검토 API·Next.js 재사용. 새 모델 호출·의존성·작업 큐·그래프 DB·별도 승인 화면 없음. 다음 구현 단계는 K6 Local 검색이다.

## 1. 실제 수락 결과와 첫 입력

K4의 수락은 원문과 연결을 검토한 후보 상태다. 운영 활성화 또는 외부 현업 승인을 뜻하지 않는다. 이번 결정자는 AI 보조 개발 검토자이며, 기관 이용·전체 자동 정확도는 미확인이다.

| 입력 | 고정 ID / 결과 |
|---|---|
| 온톨로지 | `30728ffce1c84cf78e7752c595898503`, reviewed LinkML 버전 |
| 전체 자료 묶음 | `9153c2e4c2e249b2b60b45adaa3737d8`, revision **4**, 수락 134·보류 4·기각 2 |
| A5 설명 보완 묶음 | `f894d2df9dfb420295305942e31cf121`, revision **4**, 수락 5·기각 1 |
| K5 첫 선택 | **139개 후보 = 연결 32 + 주장 107(속성 101·관계 6)**. 공식 개체는 단지 6·공고 1 |
| PDF 포함 범위 | 인쇄 4쪽, 물리 2쪽 오른쪽 표 2의 6행. 연결 6·명칭/호수/최초입주월 사실 18 수락 |

정확한 후보 ID와 자료 해시는 [선택 기록](../../../configs/knowledge/pilot_v1/k5_review_selection.json)에 저장했다. 이는 기존 로컬 원장이 필요한 인계 자료다. 다른 컴퓨터에서 코드만 내려받으면 같은 데이터가 생기지 않으며, 원문·DB는 Git에 포함하지 않는다. `data/knowledge/pilot_v1/k4_final_review.json`에는 원본 Run·결정 이력을 포함한 로컬 상세 기록이 있다.

이전 실험에서 수락된 중복 후보는 삭제하거나 결정을 번복하지 않는다. **새 스냅샷에 명시적으로 선택된 후보만 포함**하고 나머지 Run은 제외한다. 139개는 고유 업무 사실 수가 아니다. 출처·근거별 연결 및 동일값 주장을 보존하므로 화면의 개체 수·연결 수·주장 수를 구분한다.

A5 CSV 990, PDF 985, HTML 메타데이터 521, 설명의 전체 985/국민임대 521/영구임대 464는 같은 값으로 합치지 않는다. 집계 범위 미확인은 그대로 표시하며 설명문의 범위를 메타데이터에 전이하지 않는다. 금산 입주예정월 2011-05와 최초입주월 2011-06도 다른 속성이다.

## 2. 사용자 흐름과 완료 범위

1. 기존 사실 검토에서 묶음별 수락 후보를 선택한다. 미선택·보류·기각 수와 선택한 연결/사실 수를 표시한다.
2. 동일 reviewed 온톨로지를 사용하는 선택으로 비활성 스냅샷을 만든다. 새 스냅샷은 **완전한 선택 집합**이며 parent에 자동 덧붙이지 않는다.
3. 개체·관계·근거와 제외 사유를 확인하고 활성화한다. 한 운영자가 같은 화면에서 처리하며 재로그인·별도 승인자를 요구하지 않는다.
4. 활성 스냅샷의 사용 가능한 주장을 조회하고 원문을 열거나 JSON/CSV로 내보낸다.
5. 주장·근거·자료 버전의 사용 상태를 변경하고 이전 스냅샷으로 되돌린다. 사용 중단 이력은 되돌리지 않는다.

K5는 기본 목록·개체 상세·직접 관계·원문·사용 상태·기준일 조회까지다. 자연어 답변, 2단계 검색, Global 종합, 자동 변경 영향 분석은 K6~K8에 남긴다. K3/K4의 수락·수정·보류·기각 UI를 재구현하지 않는다.

## 3. 최소 저장 구조

기존 `KnowledgeRepository`에 다음 작은 테이블만 추가한다. 새 저장소 추상화나 범용 이벤트 엔진은 만들지 않는다.

| 테이블 | 저장 내용 |
|---|---|
| `snapshots` | id, parent_id, created_at, actor, reason, payload. payload에 선택 묶음/revision·후보/revision, LinkML 정본/해시, 개체·연결·주장·필요 근거/위치·자료 버전/해시를 복사 |
| `knowledge_state` | singleton 1행: active_snapshot_id(nullable), status_revision(0부터) |
| `availability_history` | 상태 배치별 revision, 대상 종류/ID, allowed/needs_review/blocked, actor, reason, recorded_at. 이력 없는 대상의 기본값은 allowed |
| `snapshot_events` | 활성화/롤백의 before_id, after_id, actor, reason, 시각. pointer 변경과 같은 트랜잭션 |

스냅샷 내용은 생성 후 UPDATE하지 않는다. 원장 후보의 현재 값이나 리뷰 상태를 화면에서 다시 조합하여 과거 스냅샷을 만들지 않는다. 원본 bytes는 기존 raw 파일을 참조하며 복사하지 않는다. JSON Schema는 저장한 LinkML에서 파생한다. 런타임에서 임의 Python 생성/import는 없다.

SKOS의 개념/명칭 구분, SSSOM의 연결 근거·방법, PROV의 출처/실행/결정자, N-ary의 범위·조건·근거가 붙은 주장 표현은 기존 ID/payload에 이어서 적용한다. RDF 저장소·새 온톨로지 다운로드는 필요 없다.

사용 상태는 리뷰 상태·이용허락 상태와 별개다. allowed는 의미 정확도나 재배포 허락을 인증하지 않는다. 상태 ID는 스냅샷에 복사한 원래 assertion/evidence/source_version ID이며, 동일 ID가 과거 스냅샷에도 있으면 최신 제한을 같이 적용한다. 범위가 좁은 주장의 allowed가 상위 근거·자료의 blocked를 무시할 수 없다.

## 4. 저장·활성화·사용 상태 동작

### 생성

- `selections[{changeset_id, expected_changeset_revision, candidate_ids}]`로 **두 묶음을 명시적으로 선택**한다. 한 묶음도 길이 1로 같은 계약을 쓴다. 아직 K5 API가 없으므로 기존 단일 묶음 API의 호환 분기를 만들 필요가 없다.
- SQLite 쓰기 트랜잭션에서 active ID·묶음 revision, 중복/소속, accepted 상태, 동일 ontology, 링크 revision/대상, 속성/관계 참조, 실제 근거를 확인한다. 기존 K4 검사 함수를 재사용한다.
- 선택한 주장의 주체·관계 대상 링크도 명시적으로 선택되어 있어야 한다. 의존 후보를 몰래 수락하거나 끼워 넣지 않고 누락 ID를 422로 돌려준다. 필요한 개체·근거·정의의 복사는 후보 자동 수락과 다르다.
- 선택한 후보의 사용 불가 상태도 확인한다. 오류가 있으면 저장하지 않고 유효 후보를 다시 선택하게 한다. 실패 시 활성 pointer 및 기존 스냅샷은 그대로다.
- 변경 없는 과거 실행을 재추출하지 않는다. 모델 호출은 0회다.

### 활성화·롤백

- `expected_active_id`를 트랜잭션 안에서 비교하고 다르면 409. 유효한 스냅샷의 pointer와 활성화 이력만 함께 갱신한다.
- 스냅샷 내부의 동결된 accepted 상태·참조를 사용한다. 생성 후 바뀐 현재 changeset revision을 이유로 과거 스냅샷 복원을 막지 않는다.
- 이후 근거가 중단된 스냅샷으로도 롤백할 수 있지만, 해당 주장은 조회·내보내기에 계속 제외된다. 응답에 사용 가능/제외 건수와 최신 status_revision을 표시하여 전체 복구로 오해하지 않게 한다.
- 수락된 사실의 수정·기각 또는 링크 변경으로 직접 의존 사실이 재검토로 전환되면, 기존 결정 트랜잭션에서 해당 assertion ID에 needs_review를 기록한다. 이미 blocked이면 완화하지 않는다. 단순 재수락만으로 allowed로 되돌리지 않는다. 과거 스냅샷이 알려진 오류를 계속 제공하는 경로만 막으며 범용 영향 전파는 K8에 남긴다.

### 조회·사용 상태

- 대상 최신 상태는 이력의 가장 큰 revision으로 판정한다. 주장의 직접 근거, 필드별 근거, 선택된 주체/대상 링크와 그 연결 근거, 해당 자료 버전까지 확인한다. 어느 하나가 needs_review/blocked이면 해당 주장 제외. 별도 재귀 그래프 탐색·캐시 없음.
- 상태 배치 수정은 `expected_status_revision` 확인 후 한 번 증가시킨다. 명시적 actor·reason과 함께 재허용할 수 있다. rollback은 이 값을 변경하지 않는다.
- 기본 조회/내보내기는 사용 가능한 주장만 반환하고 제외 ID·사유·범위·수는 별도 표시한다. 감사 목적의 기존 후보/원문 화면에는 사용 불가 상태를 표시한다.
- 기준일은 명시적 유효 시작/종료 근거가 있을 때만 적용한다. 준공일·최초입주월 같은 사건 날짜를 지식 유효기간으로 해석하지 않는다. 현재 파일럿에 유효기간 판정 근거가 없는 항목은 `validity_status=unverified`로 남긴다.
- 조회/내보내기 요청에서 snapshot ID와 status_revision을 고정한다. 응답 직전 상태 revision이 바뀐 경우에만 같은 선택 ID의 상태를 다시 적용한다. 동기 로컬 응답을 한 번 구성하며 새 감시 작업을 만들지 않는다.

## 5. API·화면·수정 파일

기존 `/api/v1/knowledge` 응답·오류 봉투를 유지한다. 활성 버전이 없는 기본 조회는 `active_snapshot_id=null`, 빈 목록과 안내를 반환한다.

| API | 입력/결과 |
|---|---|
| `POST /snapshots` | selections, expected_active_id, actor, reason → snapshot_id, parent_id, counts. 생성만 수행 |
| `GET /snapshots` | active_snapshot_id와 버전 목록·건수·작성자·사유 |
| `GET /snapshots/{id}` | 선택 이력·온톨로지·자료 범위·상태 적용한 주장/개체/직접 관계. entity_id/as_of 필터, coverage/excluded/status_revision |
| `POST /snapshots/{id}/activate` | expected_active_id, actor, reason → active_snapshot_id, 사용/제외 건수, status_revision, status_checked_at |
| `GET /availability` | type/id 지정 대상의 현재 상태·이력, 전역 status_revision |
| `POST /availability` | targets[{type,id}], state, expected_status_revision, actor, reason → status_revision |
| `GET /export` | snapshot_id 생략 시 active, format=json/csv, entity_id/as_of → 동일 상태 필터의 구조화 지식 |

JSON/CSV는 ID·값·범위·날짜·근거 ID/위치·출처·상태 revision을 포함한다. JSON은 구조 보존, CSV는 주장 1개당 1행과 복합 필드의 JSON 문자열이다. 전체 원문/블록 텍스트는 내보내지 않는다. 필요한 원문 확인은 기존 원문 API로 한다. 제3자 배포 허락을 이번 작업에서 인증하지 않는다.

- `repository.py`: 네 테이블과 기존 get/save 허용 목록의 필요한 부분만 확장.
- `snapshots.py` 하나: 생성·활성화·사용 상태·조회/내보내기의 공통 필터. 기존 서비스에서 위임. 범용 snapshot 프레임워크 없음.
- `extraction_store.py`: 이미 탐지한 수락 사실 변경/직접 의존 변경에 needs_review 기록만 연결.
- `schemas.py`, `service.py`, `app/api/routers/knowledge.py`: 요청·응답·기존 에러 변환 연결.
- `frontend/components/KnowledgeSnapshots.tsx`, 기존 `/knowledge/page.tsx`: **지식 버전** 탭. 수락 묶음/후보 선택 → 만들기 → 활성화/롤백, 개체/관계 목록과 근거 패널, 상태 변경·이력, 내보내기. 검토 화면은 기존 컴포넌트 재사용.

버전 선택 화면에서 같은 온톨로지의 수락 항목만 선택 가능하게 하고, 서버도 같은 경계를 확인한다. UI는 보류·기각된 7개 후보와 미선택 과거 실행을 첫 활성 지식에 포함하지 않는다.

## 6. 구현 순서·필요한 확인

| 순서 | 작업 | 확인 |
|---|---|---|
| 1일차 | 저장·생성·활성화·최신 상태 필터·직접 변경 연결·API | 기존 수락 데이터로 스냅샷 생성, 잘못된 선택/충돌 시 pointer 유지, 과거 payload 불변 |
| 2일차 | 기존 화면 연결·조회/내보내기·공고군 실제 흐름·결과 문서 | 생성→활성화→사용 중단→롤백→명시적 재허용→재조회 |

2일은 추정치이며 납기 보장은 아니다. 자동 확인은 다음 경계에 한정한다.

1. 여러 묶음의 명시적 선택·연결 의존성·revision 충돌·잘못된 참조에서 부분 생성/활성화 없음.
2. 이후 후보 수정이 저장된 스냅샷 내용을 바꾸지 않으며 알려진 직접 변경은 needs_review로 제외됨.
3. 근거/자료 blocked 및 주장 needs_review가 현재/과거 스냅샷과 JSON/CSV에 동일하게 적용되고 롤백 후에도 유지됨.
4. A5 수량의 서로 다른 범위, 월/일·날짜 역할, 시점 미확인 및 링크 근거 제외가 보존됨.

실제 확인은 **현재 공고군 1회, LLM 0회**다. S1은 전체 묶음의 수락 134개, S2는 A5 보완을 더한 139개를 명시적으로 선택한다. S1→S2 활성화 후 둘에 공통인 PDF 수량 근거 하나를 blocked로 변경한다. S1으로 롤백하여 해당 주장 제외가 유지되는지 확인하고, 시험 종료 시 사유를 남겨 allowed로 복원한 다음 S2를 재활성화한다. 선택 기록·호출 0·제외 ID·상태 이력을 보고한다. 아직 이 절차를 실행한 것은 아니다.

전체 12과제·민원 전체 테스트·다중 모델 비교·Windows 환경 확보·외부 현업 승인을 K5 구현 선행 조건으로 추가하지 않는다. 실제 문제가 나온 경계만 재확인한다.

## 7. 다음 단계·결정

바로 시작할 작업은 `snapshots.py`와 SQLite 저장/API다. 구현 완료 후 K6에서는 이 상태 필터를 재사용하여 활성 지식만 Local 검색에 제공한다. 자유 서술 추출의 완전성·다른 PDF 양식은 K5 완료 주장에 포함하지 않는다. **현재 사용자 결정이 필요한 사항 없음.**
