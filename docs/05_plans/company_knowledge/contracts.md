# 회사 지식 P0 최소 데이터·API 계약

- 버전: v1.4 · 2026-09-28
- 상태: K2 자료 계층과 K3 온톨로지 초안·검토 API 구현. K4 개체·사실 후보 저장·추출·검토도 구현되었으며 K5 이후는 계획이다. [K2 실행 결과](../../30_manuals/knowledge_k2_runbook.md), [K3 안내](../../30_manuals/knowledge_k3_runbook.md).
- 기준: [PRD](../../00_overview/company_knowledge_prd.md), [구현 계획](implementation.md), [아키텍처](architecture.md).
- 적용: Python 3.11.9, 기존 FastAPI/Pydantic 응답·오류 봉투, SQLite 한 원장, 단일 작업 실행. 기존 민원 API에는 변경 없음.

## 1. 공통 표현과 저장 경계

ID는 서버가 발급한 불투명 문자열이다. 업무 공식 ID는 `namespace + external_id`로 따로 저장한다. 날짜는 `value`(YYYY / YYYY-MM / YYYY-MM-DD), `precision`(year/month/day), `role`, `evidence_ids`로 표현한다. 시스템 기록 시각은 UTC ISO-8601이다. 모르는 날짜를 취득일로 대체하지 않는다.

`scope`는 P0에서 `{entity_ids: [], text: string|null}`이다. 빈 entity_ids는 문서가 명시한 text 범위를 의미하며 전사/전국 적용으로 자동 확대하지 않는다. 조건·예외는 `{text, evidence_ids}` 배열로 보존하고 법률 실행 규칙 언어를 만들지 않는다. 숫자와 단위·집계 범위를 함께 저장한다.

필수 메타데이터는 아래와 같다. 논리 객체 하나마다 repository/interface/service를 별도로 만들지 않는다. SQLite 외래키·UNIQUE·트랜잭션을 사용하고 가변 payload는 JSON으로 저장할 수 있다. 영속 객체를 덮어쓸 때 검토 이력을 잃지 않는다.

| 논리 객체 | 최소 필드와 의미 |
|---|---|
| Source | id, title, publisher, namespace, external_id?, source_url?, rights{status:unknown/local_only/allowed/restricted,note}, created_at. 외부 ID가 없으면 서버 source_id 사용 |
| SourceVersion | id, source_id, sha256, relative_raw_path, format, acquired_at?, verified_at, dates[], selected_scope, supersedes_version_id?, parse 상태. 동일(source_id,sha256) 재등록은 기존 ID 반환. 다른 source_id의 같은 파일은 출처를 병합하지 않고 파일만 재사용 가능 |
| ParsedBlock | id, source_version_id, parse_run_id, order, text, locator. parse_run에는 parser/version/options_hash 기록. 원문 bytes 변경과 파서 재실행은 다름 |
| Evidence | id, block_id, quote, start_char, end_char, alignment_status:matched/ambiguous/unmatched. `[start,end)`는 저장된 block.text의 Unicode 코드포인트 범위. 원문 locator는 block에서 조회 |
| OntologyVersion | id, parent_id?, linkml_schema, schema_hash, generated_json_schema_hash?, unsupported_constraints[], review_status, run_id. Concept은 그 버전의 안정 ID·정의·예시·허용 관계·CQ·evidence_ids를 가진 항목 |
| Entity / Alias | entity_id, concept_id, official_ids[], labels[]; 별칭마다 scope/evidence_ids/review_status. 합치기 취소를 위해 원래 엔티티·연결 결정 보존, 원본 삭제 없음 |
| Assertion | id, revision, subject_id, predicate_id, object_entity_id XOR value, unit?, scope, conditions[], exceptions[], dates[], evidence_ids(1개 이상), ontology_version_id, run_id, review_status. value는 scalar, 목록 값은 분리 또는 스키마 명시 |
| ChangeSet / Candidate | changeset_id, base_snapshot_id?, revision, source_version_ids, candidates[{id,kind,payload,before_ref?,dependency_ids,evidence_ids,validation_errors,review_status}]. 변경 영향 후보에는 direct/indirect·경로·truncated 포함 |
| Decision | id, changeset_id, candidate_id, action, before/after 또는 patch, reason?, actor, decided_at. 수락 외 결정/활성화 사유 필수; 단순 수락은 묶음 사유 1개 허용 |
| Snapshot | id, parent_id?, ontology_version_id, 검토된 entity/assertion revision/evidence ID 목록, created_at, actor, reason. payload는 불변. 활성 pointer는 별도 한 행 |
| AvailabilityHistory | id, target_type(assertion/evidence/source_version), target_id, state(allowed/needs_review/blocked), reason, actor, recorded_at, status_revision. 전역 증가 정수 한 개. 리뷰 승인 상태와 독립 |
| Run | id, kind(parse/extract/ontology/change/search), input_version_ids, changeset_id?, status, units[{id,status,error?}], model/prompt/schema/parser 설정, llm_calls, model_total_s, elapsed_s, started_at?, finished_at?. 후보와 완료 단위를 저장하고 실패 단위 재실행 |

### locator의 최소 형식

- 공통: `format`, `section?`, `block_order`; locator는 원문 해시와 파싱 실행에 종속된다.
- PDF: `physical_page`(1부터), `printed_page?`, `bbox?[x0,top,x1,bottom]`, `page_width`, `page_height`(point), 표일 때 row/column/merged_span. 좌표계는 왼쪽 위 원점.
- HTML: 본문 selector와 요소 내 순번/표 row·column. 선택 공고의 공식 단지 metadata만 별도 허용; 일반 스크립트 전체를 사실 입력으로 쓰지 않는다.
- CSV: 헤더 포함 `physical_row`(1부터), column_names, 공식 코드. 행 순서가 바뀌면 별도 원문 버전이다.
- HWPX: ZIP member와 XML element 경로/순번, 표/행/셀일 때 해당 위치. pilot의 preorder_index는 `list(root.iter())`의 0부터 인덱스이며 문단 순번이 아니다.

K2는 원문을 재작성하지 않고 추출 block.text를 보존한다. 정규화 텍스트로 위치를 잡을 때만 대응표를 추가한다. 처음부터 모든 형식에 범용 문자 정규화 매핑 엔진을 만들지 않는다. PDF 조판/표 셀→block의 위치 대응은 필수이며 코드포인트 일치만으로 의미를 검증했다고 보지 않는다.

## 2. 상태·검토·트랜잭션

- 처리 상태: registered / parsed / extracted / failed. 부분 실패 세부는 Run.units로 표시하여 성공으로 위장하지 않는다.
- Run: queued → running → succeeded / partial / failed; 취소는 cancel_requested → cancelled. 진행 중 단위는 마치고 다음 단위를 시작하지 않는다. 재시작으로 남은 running은 중단 실패로 표시하고 사용자가 실패 단위만 재실행한다. 작업 큐 서버·자동 무한 재시도 없음.
- 후보: proposed → accepted / deferred / rejected. 수정은 수정내용+accepted 결정, 기존 제안은 보존. accepted가 곧 활성은 아니다.
- K5 스냅샷 생성 시 한 트랜잭션에서 스키마/개체/근거 의존성과 accepted 상태, 선택한 변경 묶음 revision, expected_active_id를 확인한다. 활성화는 저장한 스냅샷의 참조와 expected_active_id를 확인한다. 이후 바뀐 현재 후보 revision 때문에 과거 스냅샷 복원을 막지 않으며 최신 사용 제한은 유지한다. 잘못된 항목은 후보별 validation_errors로 보여준다. 선택 항목에 오류가 남으면 부분 commit하지 않고 422로 반환하여 유효 후보를 다시 선택하게 한다.
- 검토자·운영자·활성화자는 P0에서 같은 한 명이다. 한 화면에서 묶음 수락 후 활성화할 수 있고 별도 사람·승인 티켓·재로그인을 요구하지 않는다. 후보별 수동 승인 클릭 반복도 요구하지 않는다.
- 스냅샷은 새로 만들고 활성 pointer만 바꾼다. rollback도 같은 activate 동작이다. 최신 AvailabilityHistory는 롤백하지 않는다.
- 조회 시작 시 스냅샷과 현재 status_revision을 고정하고, 응답 전에 한 번 revision을 읽는다. 달라졌을 때만 사용한 ID의 상태를 다시 확인한다. 사용 중단된 근거가 있으면 answer=null, status=stale로 반환한다. 별도 감시 서버·질문별 다중 AI 평가 없음.
- 새로운 source version이 생겼다는 이유만으로 이전 버전 전체를 무효화하지 않는다. 명시된 정정과 실제 변경 근거의 관련 주장만 needs_review로 둔다. 영향 범위가 불명확하면 해당 후보를 보류한다.

## 3. 공통 API와 단계별 구현

접두사는 `/api/v1/knowledge`. 성공은 `{success:true, request_id, timestamp, data}`, 실패는 기존 [error_response](../../../app/api/error_utils.py)의 `{success:false,request_id,timestamp,error:{code,message,retryable,details}}`다. Pydantic 타입과 OpenAPI는 해당 endpoint를 구현할 때 같이 만든다. K2 전에 P0 전체 라우터·빈 서비스 파일을 생성하지 않는다.

| 시점 | method/path | 입력 → data |
|---|---|---|
| K2 | POST /sources | multipart file + metadata(JSON: source_id? 또는 title/publisher/namespace/external_id/source_url/rights, dates, selected_scope, acquired_at?) → source_id, source_version_id, disposition(registered/duplicate). 서버가 hash 계산·허용된 데이터 디렉터리에 저장; 등록 응답은 즉시 메타 반환 |
| K2 | GET /sources | source_id? → items[{source,versions,processing_status}]. P0 소량 목록, 일반화된 쿼리 언어 없음 |
| K2~3 | POST /runs | kind=parse 또는 ontology, source_version_ids[], retry_of_run_id?. ontology는 cqs[{id,question}], base_ontology_version_id? 추가. unit_ids는 parse 재시도만 지원. → run_id,status |
| K2 | GET /runs/{id} | → Run, 진행/실패 단위, counts, metrics |
| K2 | POST /runs/{id}/cancel | → {run_id,status}; 이미 종료됐으면 현재 상태 그대로 |
| K2 | GET /sources/{id}/versions/{version_id} | → 출처·날짜·권리·hash·selected_scope·processing_status·raw_url |
| K2 | GET /sources/{id}/versions/{version_id}/raw | 서버 등록 ID로 원본 bytes 스트리밍. 임의 로컬 경로나 외부 URL 요청 인자 없음 |
| K2 | GET /sources/{id}/versions/{version_id}/blocks | → items[ParsedBlock+evidence_id]. 최신 전체 파싱과 재시도 계열의 성공 단위. 이전 근거는 ID 조회로 보존 |
| K2 | GET /evidence/{id} | → Evidence+block.text+locator+source/version metadata. 근거 화면 원문 위치 조회 |
| K3~4 | GET /candidates | changeset_id?, kind?, review_status? → items, changeset_revision, unresolved_count |
| K3~5 | POST /changes/{id}/decisions | expected_changeset_revision, actor, decisions[{candidate_id,action(accept/modify/defer/reject),patch?,reason?}] → decisions, changeset_revision, validation_errors. change 후보의 별도 resolution(no_change/modify/withdraw/defer)도 payload로 기록 |
| K5 | POST /snapshots | selections[{changeset_id,expected_changeset_revision,candidate_ids}], expected_active_id(null 허용), actor, reason → snapshot_id, parent_id, counts. 명시적 전체 선택 집합으로 비활성 생성; parent에 자동 누적하거나 활성화하지 않음 |
| K5 | POST /snapshots/{id}/activate | expected_active_id, actor, reason → active_snapshot_id,status_revision,status_checked_at. 롤백도 동일 API |
| K5 | POST /availability | targets[{type,id}], state, expected_status_revision, actor, reason → status_revision. 근거 사용중단·재검토/재허용은 이 공통 동작 사용 |
| K5 | GET /snapshots | → active_snapshot_id,items[{id,parent_id,created_at,reason}]; 조회·롤백 대상 선택 |
| K5 | GET /snapshots/{id} | entity_id?, as_of? → 동결된 선택·온톨로지·자료 범위, 최신 상태를 적용한 개체/주장/직접 관계·coverage/excluded/status_revision |
| K5 | GET /availability | type/id → 해당 대상의 최신 상태·이력, 전역 status_revision |
| K5 | GET /export | snapshot_id?, format(json/csv) → 구조화 원장 자료. 최신 사용중단 원문/파생 답변 제외; 원문 전체는 포함하지 않음 |
| K6~7 | POST /search | 아래 계약 → 답변·인용·경로·범위·상태·metrics |

파일 등록에서 외부 source_url은 출처 메타데이터이며 자동 다운로드 명령이 아니다. 파일명 경로 순회·지원하지 않는 파일형식은 입력 경계에서 거절한다. 외부 문서의 명령은 데이터로 처리한다. `KNOWLEDGE_ENABLED=false`이면 해당 라우터는 비활성 상태(503 KNOWLEDGE_DISABLED)를 반환한다. DB 기본 경로는 `data/knowledge/knowledge.db`; 로컬 raw/평가 결과도 Git 제외다.

새 오류는 해당 경계에서만 사용: 404 NOT_FOUND, 409 VERSION_CONFLICT 또는 RUN_BUSY, 422 VALIDATION_ERROR, 503 KNOWLEDGE_DISABLED. 모델 연결/timeout은 기존 모델 오류를 재사용한다. 조회상 근거 부족·모호성·부분 처리는 정상 data.status로 구분하며 서버 장애를 빈 성공으로 반환하지 않는다.

## 4. Local/Global 입출력

입력 필수: `query:string`, `mode:local|global`. 선택: `snapshot_id:null|string`(null은 요청 시작 시 활성 버전), `source_ids:null|list[string]`(null은 스냅샷의 등록 범위, 빈 배열은422), `scope:null|{entity_ids:[],text:null|string}`, `as_of:null|YYYY-MM-DD`(업무 적용일).

출력 `data`:

```text
status: answered | partial | insufficient | ambiguous | stale
answer: string|null
snapshot_id, status_revision, status_checked_at
assertion_ids: string[]
citations: [{evidence_id, source_id, source_version_id, locator, quote, url}]
paths: [{entity_ids:[], assertion_ids:[]}]          # Local, 최대 관계2단계
entity_candidates: [{entity_id,label,source_ids}]  # ambiguous일 때
coverage: {selected_source_ids:[], included_version_ids:[],
           excluded:[{source_id,source_version_id?,reason}],
           selected_assertion_count, used_assertion_ids:[],
           omitted_assertion_ids:[], partial:boolean}
validity_status: verified_for_selected_scope | unverified
limitations: string[]
metrics: {llm_calls, model_total_s, elapsed_s}
```

`verified_for_selected_scope`는 등록 원문 범위와 검토 상태를 충족한다는 뜻이며 법률 현행성 인증이 아니다. `as_of`가 주어져도 날짜 근거가 없는 사실을 해당 시점의 확정 지식으로 바꾸지 않는다. 포함/제외·누락 ID는 서버가 계산하고 답변에 사용한 citation은 실제 입력에 포함된 근거 ID로 제한한다. 원문 url이 없으면 등록 raw endpoint를 반환한다.

Global 중간 요약은 P0에서 요청 안에서만 사용한다. 별도 영속 요약 캐시·무효화 서비스는 만들지 않는다. Run에 의존 ID와 처리 범위를 남기므로 사용 중단과 재현 확인은 가능하다. 실패한 묶음은 제외 사유와 partial을 반환한다. 최종 합성이 실패하면 서버 오류로 종료한다.

검색은 내부 kind=search Run을 기록하되 별도 POST /runs로 재요청하지 않는다.

P1 `/knowledge/assist`는 [구현 계획 §1](implementation.md#1-제안-api-목록)의 경계만 유지하며 이번 계약에서 구현하지 않는다. 기존 `/search`·`/qa`·case_id·Q0~Q7 모델/평가를 변경하지 않는다.

## 5. 구현 시 필요한 확인만

K2에서 실제 선정 포맷별 원문 위치 1건과 중복 등록/실패 표시를 확인한다. K3~5에서 관련 개발 과제와 잘못된 근거 제외·활성화 실패 유지·롤백 중단 상태 유지만 확인한다. K6~7 Local/Global 각 3건, K8 실제 날짜 정정, K9 정지 상태 백업/복원 1회 및 가능한 OS 확인을 누적한다. 필드별 테스트·모든 상태 조합·전체 민원 평가 반복을 선행 조건으로 추가하지 않는다. 변경과 직접 관계 있는 실패만 재검증한다.

K2 실행은 단일 프로세스·직렬 작업이다. Evidence는 전체 블록의 `[0,len(text))` 발췌이며 matched는 문자열 위치 일치만 뜻한다. 부분 주장 정렬·검토는 K4 이후다.

## K3 구현 계약 (2026-09-27)

`GET /ontology-cqs`는 개발 질문 id/question만 반환한다. `GET /ontologies`와 `GET /ontologies/{id}`는 draft/reviewed 버전과 LinkML·JSON Schema·해시를 조회한다. `/candidates`·`/changes/{id}/decisions`는 개념·속성·관계 후보를 지원하며 Entity/Assertion은 K4다. Candidate는 proposed→accepted/deferred/rejected, modify는 수정 후 accepted. reviewed는 활성 상태가 아니다.

모델은 근거 ID를 선택하고 인용은 고정 블록에서 구성한다. API 수정 인용은 원문 일치 검사하며 의미 타당성은 별도의 검토 대상이다. 재시도는 저장된 성공 단계 결과를 재사용하며 모델·프롬프트·입력 변경은 새 실행으로 처리한다. [K3 안내](../../30_manuals/knowledge_k3_runbook.md).

## K4 구현 계약 (2026-09-28)

[K4 구현 계획 §3~4](k4_implementation_plan.md)의 저장/API 세부 사항을 이 계약의 K4 부록으로 채택한다. entities/entity_links/assertions/evidence 4개 테이블, kind=extract Run, entity_link/assertion 후보, 링크 전용 unlink 결정을 추가한다. 기존 K2/K3 응답 봉투와 필드는 유지한다. 링크 변경에 직접 의존하는 주장은 재검토 상태로 전환하며, 운영 활성화/일반 영향 전파는 K5/K8에 남긴다. API와 화면을 구현했다. 실제 확인 및 미검증 범위는 [K4 실행 결과](../../30_manuals/knowledge_k4_runbook.md)를 따른다.


K4 실제 오류 보완: link 수정 허용 필드에 `mention`, `evidence_ids`를 추가했다. 원문에 없는 별칭은 수락할 수 없으며 K2 전체 블록 근거도 고정 입력 범위 내에서 수정에 사용할 수 있다. `GET /runs/{id}`는 단위 상태 `counts`와 후보 상태 `candidate_counts`, `processed_block_ids`, `invalid_record_count`를 분리한다. 구조 불량 레코드는 단위의 `invalid_records`에 보존하며 기술 성공과 품질 완료를 구분한다. 단위별 후보 counts는 그 시점의 묶음 누적값이므로 합산하지 않는다.

K4 품질 보완: `POST /changes/{id}/assertions`에 expected_changeset_revision, actor, reason, subject_link_id, predicate_id, block_id, quote, raw_value, scope, object_link_id?를 전달하여 고정 원문에서 수동 후보를 추가한다. 자동 Run 출력/호출 수는 보존하고 `origin=manual`과 생성 결정 이력을 남긴다. 기존 결정 API로 별도 수락한다. [결과](../../30_manuals/knowledge_k4_quality_result.md).

## K5 구현 예정 계약 보충 (2026-09-28)

[K5 계획](k5_implementation_plan.md)이 아직 없는 K5 API의 구체화 기준이다. 두 수락 묶음을 포함할 수 있도록 단일 changeset 입력을 selections로 대체했다. 선택한 주장에 필요한 수락 링크도 명시적으로 포함해야 한다. 스냅샷은 후보/revision·정본·개체·근거를 복사하며 현재 후보 재조회로 과거 내용을 재구성하지 않는다.

사용 불가 상태가 나중에 생긴 스냅샷으로도 롤백할 수 있으나 해당 주장은 최신 상태 필터로 계속 제외한다. 알려진 수락 사실 수정/기각과 직접 링크 변경은 같은 결정 트랜잭션에서 해당 assertion에 needs_review를 기록하고 blocked를 완화하지 않는다. 상태 제한은 주장·필드·주체/대상 링크의 직접 근거와 자료 버전까지 확인한다. 생성/활성화/기본 조회에는 LLM 호출이 없다. 기준일 근거가 없는 사건 날짜는 유효기간으로 추정하지 않는다. 내보내기는 구조화 값·ID·위치·상태만 제공하고 전체 원문/블록 텍스트는 제외한다.
