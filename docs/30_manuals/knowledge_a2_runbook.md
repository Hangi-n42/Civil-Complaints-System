# A2 로컬 자료 탐색·분석 실행

- 대상: [#521](https://github.com/Hangi-n42/Civil-Complaints-System/issues/521), [설계 §5~9](../05_plans/company_knowledge/autonomous_ontology_plan.md). A1 및 Markdown 표 헤더 수정이 반영된 `3dad404`에서 구현.
- 기존 SQLite Run·직렬 executor·`call_ollama` 사용. 별도 DB·큐·프레임워크·패키지 추가 없음.
- [기존 재사용 기록](../third_party/knowledge_k3_reuse.md)의 OntoGPT 구조·grounding 검사와 AutoSchemaKG 개념 추상화 지침을 역할별 JSON 계약에 적용. 전체 엔진·외부 온톨로지·코드 생성은 도입하지 않음.
- 산출물은 근거에 연결된 **미승인 분석 재료**. LinkML/changeset·운영 지식·활성 snapshot을 생성하거나 수정하지 않음. 수동 `kind=ontology`와 A1 입력 준비는 기존 계약 유지.

## 실행과 재조회

1. [A1 절차](knowledge_a1_runbook.md)로 허용 manifest의 파일을 등록·고정한다.
2. 종료된 A1 `run_id`에 분석 설정을 연결한다. 경로·원본 파일·최신 parse 포인터를 다시 받지 않는다.

```json
{
  "kind": "discovery",
  "discovery_mode": "analyze",
  "input_run_id": "A1 실행 ID",
  "cqs": [{"id": "cq1", "question": "공개 자료의 유형 정의와 단지 표기는 어떻게 구분되는가?"}],
  "scope_items": [{"id": "scope1", "question": "공개 임대주택의 유형·식별 필드·조건 발견. 개별 자격 판정 제외."}],
  "baseline_version": "discovery-empty-v1",
  "discovery_budgets": {"model_calls": 48, "searches": 24, "additional_rounds": 2, "revisions": 1, "model_seconds": 7200}
}
```

- `POST /api/v1/knowledge/runs` 반환 후 `GET /runs/{id}`에서 비동기 진행·저장 결과 조회. 기존 응답 봉투 유지.
- 선택 분석은 `analysis_block_ids`와 `analysis_selection_reason`으로 사전에 고정한다. 블록은 A1의 완료된 parse 안에서만 선택할 수 있다. 전체 파일 프로파일과 전체 대표 frontier는 유지하고, 선택 밖 자료와 미처리를 별도 집계한다. 명시 선택 실행은 추가 라운드로 범위를 자동 확장하지 않는다. 읽기·검색의 허용 경계는 기존 A1 파일/scope/step이며, 분석 선택 밖 원문도 비교 문맥으로 조회될 수 있다.
- `baseline_version`은 회사 정의가 없는 현재 고정 메타모델을 식별한다. 범용 패턴 플랫폼은 추가하지 않았다.
- `base_ontology_version_id` 선택 시 reviewed 버전만 허용. 해당 정의의 근거는 A1이 고정한 parse/block 안에 있어야 한다. 역사 최초 단계는 빈 기준이며 이후 기준은 동일 역사 계보·현재 또는 이전 step만 허용. 현재/역사 기준을 혼합하지 않는다.
- `lineage_id` 생략 시 bundle별 current/historical 계보 사용. CQ 또는 `scope_items`가 최소 하나 필요하며 범위 항목의 내용 필드는 기존 CQ 계약과 같은 `question`이다.
- `GET /discovery/read?run_id=…&file_id=…`, `GET /discovery/search?run_id=…&q=…`: 고정 블록과 현재 K5 사용 상태로 조회. A2 검색은 BM25 순위와 출처군 순환 적용. A1/개발용 조회 유지.
- `GET /discovery/terms?run_id=…&label=…&term_type=any`: 고정 reviewed 기준과 해당 실행의 유효한 미승인 관측만 조회. 미래 단계·다른 실행 후보·활성 민원 collection fallback 없음.
- 기존 `/evidence/{id}`와 원본 다운로드 경로로 동일 원문·locator 재조회 가능.

### 선택적 모델 추론

- 서버 시작 전에 `KNOWLEDGE_DISCOVERY_THINK=true`로 설정하면 A2의 기존 recipe에 native 추론 선택을 고정한다. 기본값은 `false`이며, 추론을 지원하는 설치 모델에서만 사용한다. 별도의 끝점 연결 검수는 기존 `binding_think=false`를 유지한다.
- 설정이 바뀌면 새 실행이 필요하다. 기존 실행·검수·실패 기록을 덮어쓰지 않으며, False에서 저장한 원문 발견 결과를 True 실행의 결과로 재사용하지 않는다.
- 추론은 출력 토큰과 시간을 추가 사용한다. 출력 한도 안에서 최종 응답을 내지 못할 수 있으며 자동 증액·반복하지 않는다. 이번 제한된 참조형 정의 검수에서는 정확한 조문 참조와 미제공 외부 정의를 구분했지만, 7197 관계 교정은 4,096토큰 소진 후 최종 응답 없이 실패했다. 일반 품질 향상이나 모든 후보의 수락을 보장하는 설정이 아니다.
- 실제 길이 소진에 따라 추론을 켠 Builder와 문맥 적용성 판단에는 기존 역할별 출력 한도 방식으로 8,192토큰을 배정한다. 기본 False의 해당 호출과 독립 원문 발견의 기존 한도는 유지한다. 입력·출력 합산 컨텍스트 검사와 실행의 호출·시간 예산을 그대로 적용한다.
- 앞선 역할 교정 검증에 사용한 조합은 `THINK=true`, `INPUT_CHARS=40000`, `NUM_CTX=65536`(앞의 세 이름은 `KNOWLEDGE_DISCOVERY_` 접두어), `KNOWLEDGE_DESIGN_TIMEOUT=720`, Gemma `gemma4:31b-it-q4_K_M`이다. 성공한 Builder 467.636초와 역할 Critic 377.446초는 기본 timeout 360초를 넘었다. Boolean만 켜면 같은 결과가 재현된다는 뜻이 아니다. 전체 모델 digest·역할별 한도·실패를 포함한 비용은 [실제 검증 기록](../70_research/company_knowledge/ontology_current_completion_20261004.md)에 구분한다.
- 전체 요구(`requirements`)만 별도 용량이 필요하면 `KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_PREDICT`(기본 8,192), `KNOWLEDGE_DISCOVERY_REQUIREMENTS_NUM_CTX`(기본 0: 공통 문맥 상속)를 새 실행에 선택한다. 실제 review 모델의 지원 문맥, HTTP 옵션, 사전 UTF-8 상한, 사후 실제 토큰 검사에 같은 값을 적용한다. 다른 단계의 설정과 원문 발견·적용성 캐시는 유지한다. 관측된 전체 질문 출력 절단 후 선택한 후속 값은 출력 16,384·문맥 81,920·`KNOWLEDGE_DESIGN_TIMEOUT=1800`이다. 최신 전체 질문 재검수는 `INPUT_CHARS=41000`에서 완성 응답을 받았지만 법적 연결을 추출 누락으로 오판하여 의미 검증은 통과하지 못했다. 용량 선택을 품질 개선이나 운영 완료로 해석하지 않으며 상세 결과는 검증 기록에서 확인한다.
- 전체 질문 입력이 기존 한도를 넘으면 실제 직렬화 크기를 먼저 확인한다. `KNOWLEDGE_DISCOVERY_INPUT_CHARS`(기본 32,000자)와 `KNOWLEDGE_DISCOVERY_NUM_CTX`(기본 49,152토큰)로 새 실행의 한도를 선택할 수 있다. 설치 모델의 선언 문맥 검사와 UTF-8 바이트 수+출력 토큰의 보수적 상한 검사는 유지한다. 지원 문맥과 별개로 실제 처리 시간·메모리는 확인해야 하며 자동 증액하지 않는다. 부분 입력만 검수했다면 문서 간 전체 질문을 충족했다고 보고하지 않는다.

## 조사·선택·역할

- 모든 완료된 선택 블록을 구조 조사한다. CSV는 모든 행의 필드·결측·형식·고유값 수를 조사하며 관측 분포와 허용 enum을 구분한다.
- 유형/종류/분류/구분/상태라는 열 이름은 범주 조사 신호로 사용한다. 의미가 검증된 필드 사전으로 취급하지 않는다. 그 밖의 고카디널리티 필드는 값별 대표 미선정 사유와 형식 분포를 남긴다.
- CSV 대표는 미충족 특징 최다 → 희소 특징 → 짧은 입력 → 안정 위치/ID의 greedy set cover. 실제 혼합·결측 특징을 포함한다. 완전한 의미 분석을 보장하지 않는다.
- 선택 법령·API·설명 원문은 전 블록 필수 목록. 표의 저장 헤더·행·인접 원문·locator를 함께 제공하며 다단 헤더·단위·각주 연결이 불명확하면 `unconfirmed`를 남긴다.
- 필수 원문, 예외/모순, 미방문 범주 순으로 출처군을 순환한다. Scout의 읽기 요청은 같은 우선순위 내 선택에 반영하며 이유를 저장한다.
- Schema Scout → 원문 분석 m묶음의 Concept/Relation → 문서 간 후보 g묶음의 Builder/Critic. 역할은 모두 기존 worker에서 직렬 호출한다.
- 후보는 CQ/scope 역인덱스와 출처 순환으로 조립한다. 여러 연결 중 하나가 겹치는 다른 문서·이전 라운드 후보와 관련 reviewed 기준을 비교 입력으로 제공하며, 한도 밖 비교 대상은 ID를 남긴다. 전 개념 쌍을 비교하거나 미승인 후보를 정답으로 취급하지 않는다. 기본 호출식은 `1 + 2m + 2g + 수정 호출`이고 g는 실제 후보 조립 후 확정한다.
- 개념은 type/vocabulary/entity/property_value/unresolved, 명시적 정의/사례 제안, 추상화 수준·검토 신호를 저장. 문서 관측과 기존 개념 대응은 분리하며 먼저 생성한 후보를 정답으로 사용하지 않는다.
- 새 실행의 `candidate_version=a2-candidates-v1`은 유효 근거의 version/parse/block/span/quote와 이름·종류·정의·조건/예외·시점·범위·근거 성격·설계 출처가 정확히 같은 관측만 실행 내부 대표 ID로 연결한다. 분류 이유·추상화·검토 신호도 보수적으로 구분한다. Relation 입력부터 Builder/Critic·A3까지 대표 뷰를 사용하고, 이름만 같거나 표현·근거가 다른 후보와 승인 정본을 자동 병합하지 않는다.
- 후보는 근거와 CQ 또는 범위 연결을 검사한다. 범위 밖 발견, 검증 오류 후보를 보존·구분한다. 빈도/고유명사/사례 수로 클래스를 자동 승격·거절하지 않는다.
- Builder는 제공된 정의를 먼저 비교하고, 현재 묶음의 규범/정의 관계에 필요한 유형만 `observations`의 `design_proposal`로 제안한다. `source_relation_ids`·설계 이유와 `relation_bindings`를 저장하며 새 t1~t5는 서버 ID로 연결한다. 원문 관계는 보존하고 설계는 Critic·수정·A3 검수를 거친다. 설계 역할을 원문 명시 유형이나 슬롯 필수값으로 승격하지 않는다.
- `design_relation_ids`는 묶음당 최대 5개다. 각 대상의 `relation_bindings`는 `decision=bind`와 실제 유형 끝점 또는 `decision=defer`와 구체 사유 중 정확히 하나다. 비교 전용 묶음은 대상 0개다. `binding_coverage`는 응답/연결/보류/미완료를 구분하며 보류·누락은 `design_pending_relation_ids`로 A3까지 유지한다.
- 관계의 방향·부정·조건·시점·진술 성격을 저장. 계층은 제안된 쌍만 양방향 검토하고 is_a/instance_of/broader 대상 종류·자기 참조·is_a 순환·별칭 참조를 검사한다. 동치 자동 병합 없음.
- 새 관계의 `endpoint_labels.subject/object`는 원문 표현이며 연결 ID와 독립적으로 보존한다. 모델 임시 ID와 같은 문자열이어도 원문 표현은 치환하지 않는다. Critic의 `semantic_checks`는 원문 끝점·조건/예외·진술 종류를 대조한다. 원문 supported와 유형 연결 완료는 별개이며 연결 오류/정의 미제공은 endpoint 쟁점·A3 보류로 남긴다. 원문 표현의 연속 문자열 일치를 의미 지지의 필수조건으로 사용하지 않는다.
- 원문 묶음은 법령/설명 최대 3,200자, CSV 최대 1,600자의 직렬화 비용을 기준으로 분할한다. 한 블록 자체가 한도를 넘으면 원문을 자르지 않고 입력 한도 검사에서 보류한다.
- Critic은 후보명과 예외/변경 질의로 동결 원문에서 별도 검색한 문맥을 받는다. 키워드 히트를 반증으로 간주하지 않는다. 도구 결과는 다음 역할 입력까지 연결하며 실제 제공 근거를 기록한다.
- Critic의 `review_target_ids`는 주관측·주관계·새 설계·계층을 명시하고 `comparison_candidate_ids`와 분리한다. `observation_checks`/`relation_checks`/양방향 `hierarchy_checks`에 근거 있는 supported/refuted 또는 구체 이유가 있는 unknown을 요구한다. expected/coverage는 같은 주검토 집합이며 누락·중복·무효 판정만 미완료로 격리한다. `review_outcomes`는 유효 응답과 의미 판단을 구분한다. 새 생성 schema는 source_refs 경로를 사용하고 기존 exact quote·coverage·fingerprint 읽기는 유지한다. 인용 일치는 의미적 정당성의 증명이 아니다.
- Critic 쟁점은 서버 `di_` ID로 저장하며 `request_evidence.issue_id`도 같은 ID로 연결한다. 모델의 응답 내 i1/i2 참조는 정규화 후 폐쇄된 원장 참조로 검증한다.
- `review_scope`는 실제 제공 source_refs·주검토/비교 범위·미제공 후보를 표시하며 전체 원문 부재를 확정하지 않는다. 재개에서는 같은 검수 범위를 재사용한다. 누락 제안은 실제 `compared_candidate_ids`와 `comparison_reason`을 기록한다. 해당 CQ/scope의 주관측·관계가 있는데 그 종류의 비교 자체가 없으면 지역 미확인으로 보류한다. 모든 동일 블록 후보 ID를 의무 나열하지 않으며 ID 목록 자체를 의미 대조의 증거로 계산하지 않는다.
- Pydantic 동작은 read/search/lookup_term/request_evidence/finish만 허용. 임의 URL·파일·shell·SQL·승인·활성화는 dispatch할 수 없다. 자료 밖 참조는 자료 필요로 남긴다.

## 저장·재개·종료

- Run에 입력 A1 ID·frozen_input·CQ/범위·기준 YAML·모델명/digest/컨텍스트·프롬프트/스키마/프로파일 버전·예산을 고정한다.
- `analysis_units`: 입력 해시·실제 prompt·원출력·검증 결과·호출 시도·시간·의존 근거. `frontier/profiles/tool_events/result`가 탐색 및 A3 연결 자료다. 결과 포맷 `a2-analysis-v2`, 현재 프롬프트 `discovery-a2-v24`. Critic 입력에서 중복 설계 연결과 빈 파생 검증 배열을 생략하며 원문·원관계·조건과 검증 오류는 보존한다. 기존 실행 원장은 수정하지 않으며 레시피가 다르면 재개 대신 새 실행이 필요하다.
- `candidate_identity.raw_to_candidate`와 `discoveries`에 원관측→대표 후보·발견 unit/group을 저장한다. 성공 unit의 ID/output/input_hash와 original_observations/relations는 유지한다. 대표 뷰의 계약상 ID 필드만 연결하며 원문 문자열·원관계 사본은 치환하지 않는다. 재개에서 처음 등록한 대표 ID와 성공 호출을 재사용한다. 검수 fingerprint는 대표 뷰로 계산하고 발견 이력은 별도 관리하므로 발견 추가가 의미 검수 값을 바꾸지 않는다. 과거 원관측 fingerprint/검수는 변경된 대표 뷰를 승인하지 못한다.
- 호출 전후와 재개에서 K5 상태 확인. 원문뿐 아니라 전체 생성 의존성을 가진 요약/관측/lookup 결과도 사용 중단 근거를 포함하면 후속 입력에서 보류한다.
- endpoint는 loopback HTTP만 허용. localhost는 127.0.0.1로 고정하고 proxy·redirect를 사용하지 않는다. 설치 모델 digest와 선언 컨텍스트를 확인하며 실행 중 다운로드나 외부 모델 fallback 없음.
- 기본 상한은 48회/검색 24회/추가 2라운드/묶음 수정 1회. 실패 호출도 포함. 신규 원문 분석 전에 Builder/Critic 호출을 예약한다. 이미 완료된 분석 재사용에는 새 예약을 요구하지 않는다. 연장·자동 예산 증액 없음.
- 전체 입력 12,000자와 UTF-8 바이트 기반 보수적 토큰 상한·실제 prompt_eval_count를 확인한다. 긴 입력·JSON 오류·출력 절단은 실패이며 원문/결과를 조용히 잘라 빈 성공으로 만들지 않는다.
- `POST /runs/{id}/cancel`: 현재 모델 응답을 저장한 뒤 다음 호출 중단. `POST /runs`의 `{"kind":"discovery","retry_of_run_id":"…"}`로 동일 설정 재개. 성공 단위는 입력 해시가 같은 경우 재사용하고 실제 호출·검색·시간 예산은 누적한다.
- 저장 전 중단 호출은 `interrupted_before_result_commit`으로 구분한다. 다시 호출될 수 있다. 실제 시간 미확인분은 측정값에 합치지 않고 `interrupted_time_reserve_s`로 당시 timeout을 보수적으로 예산 차감한다.
- 구조 조사, 분석 선택, 실제 원문 제공, 역할 처리 완료, 근거 연결, 무결과/근거 부족, 미처리, Critic 검토를 따로 기록한다. `processed_analysis_groups`는 Concept/Relation 호출 저장 완료이고 의미 분석 성공을 뜻하지 않는다. `concept_evidence_block_ids`/`relation_evidence_block_ids`는 실제 인용 블록이며 `analysis_succeeded`는 두 집합의 교집합 수다. 한 블록을 인용했다고 묶음 전체를 완료로 세지 않는다. 후보가 없는 역할은 `no_result_groups`와 gaps에 남기며 후보 생성을 강제하지 않는다.
- 필수 미처리·파싱/모델 실패·사용 중단·예산 종료는 `partial`. `review_ready`는 초안 검수 준비이며 정확성·인간 승인·운영 활성화를 의미하지 않는다. 실제 수정 시도가 실패하거나 저장 전 중단돼도 해당 묶음의 수정 1회를 소진하며 재개에서 재호출하지 않고 명시 보류한다. 호출 전 입력 한도 실패는 실제 호출로 세지 않는다. 수정 결과도 미검수 제안이다. revision은 후보 묶음당 최대 1회로 개념·관계·계층의 전체 수정 또는 후보별 명시 보류를 반환한다. 쟁점·수정 대상·필요한 온전한 원문만 다시 조립하며 한도 밖 대상은 보류한다. 비교 후보는 원래 담당 묶음 또는 사람 검수로 보류해 여러 묶음이 같은 ID를 중복 수정하지 않는다. 서버 ID, original_observations/relations, revision_history의 before/after와 유지 계층을 포함한 effective_hierarchies를 보존한다. 검토된 기준 정의는 수정하지 않는다.

## 이전 실행 기록과 집계 정정 (v7, 원장 보존)

- Python 3.11.9. 변경 경계와 A1·수동 ontology·parse·K5·검색 회귀 테스트 **104 passed, 1 skipped** (6.67초). skip은 기존 로컬 HWPX 표본 부재. 전체 민원·12과제·다중 모델·Windows 실기는 실행하지 않았다.
- 테스트 실행: `python -m pytest app/tests/unit/test_knowledge_{discovery_inputs,discovery_run,discovery_analysis,service,parsers,api,ontology_run,extraction_run,extraction_store,snapshots,search}.py app/tests/unit/test_generation_ollama_metadata.py -q` (위 중괄호는 셸 파일 확장 표기).
- 실제 입력: 공공주택 특별법 제2조 TXT 3블록 + LH 전국 아파트 단지정보 CSV 6,217행. manifest `eb1379a48588ba7bf6c2be3dc109a797f9da1740ac5599aca85b33bdea315cdf`, current_discovery/step 0. A1 준비는 완료된 parse 2개 재사용.
- 실제 모델: `gemma4:31b-it-q4_K_M` / `qwen3.8:27b-q4_K_M`, digest는 실행에 고정. num_ctx 32,768, num_predict 4,096, think=false. 이번 확인의 호출 상한은 12회이며 자동 증액하지 않았다.
- 이전 실제 실행: `0bd5f59bcb60427b967c5be6c55c6bae` (`discovery-a2-v7`). **partial**. 실제 모델 **9회/501.436초**, 전체 **514.993초**, 검색 **8회**. 두 자료 묶음에서 Concept→Relation→Builder→Critic 결과를 저장했으며 CSV Relation은 명시적 공백으로 종료했다.
- 구조 조사 **6,220블록**, 실제 원문 제공 **15블록**, 두 역할이 실제 인용한 고유 블록 **1개** (당시 원장의 **3블록**은 묶음 전체를 세던 과대 집계로 정정), Critic **2묶음/쟁점 5개**. 관측 **7개**, 관계 **4개**. 최종 계층 제안과 양방향 계층 검토는 **0개**이며 Builder의 보류 사유를 저장했다. v4의 4계층 양방향 결과를 최종 실행 성과로 합산하지 않는다.
- CSV 전 행에서 특징 **147개**, 대표·예외 **66행**을 결정적으로 선정했고 선정 기준의 미포함 특징은 0개다. 이는 LLM 분석 완료가 아니다. 원문 미제공 **6,205블록**, 두 역할 근거 미연결 **6,219블록** (당시 원장 6,217의 정정), 필수 미처리 **33묶음**, 미처리 특징을 가진 **33묶음**, 후속 원문 요청 미제공 **13블록**을 남겼다.
- 수정 Builder 2건은 **15,281자/16,762자**로 입력 한도를 초과해 호출 전 실패했다. 이후 묶음의 Concept/Relation/Builder/Critic 예약에 필요한 4회가 남은 호출 예산 3회를 넘어 종료했다. 한도를 늘리거나 원문을 잘라 성공으로 바꾸지 않았다.
- 실제 API에서 결과·읽기·BM25 검색·용어·근거를 재조회하고 scope 불일치/미선택 파일 거절을 확인했다. 근거 **13건**의 원문·locator·source version·parse ID 일치. 재개 `74644503da484960aa9a42f00dfdb1e9`는 성공 **9단위**와 후보 ID를 유지하며 **추가 모델 호출 0회**, parse **2개 유지**, 자료 포인터 불변. 재개도 같은 미처리 범위의 partial이다.
- 개발 실행을 포함한 실제 호출 누계는 **49회/3,127.423초**. 재개한 실행의 누적 수치를 중복 합산하지 않았다. 실행 원장과 확인 JSON은 로컬 `data/knowledge/a2_smoke_20260930/`에 보존하며 Git에는 요약만 포함한다.
- 개발 중 실제 실패도 별도 보존: v1 6회/422.293초(partial, action 인자·중복 참조 오류), v2 6회/182.823초(cancelled, 부분 객체 JSON schema 분기 오류), v3 7회/501.267초(cancelled, Critic 복수 local_ref 오류), v4 8회/678.613초(cancelled, 개념 대응 참조·쟁점 ID 미연결 확인), v5 7회/457.550초(cancelled, 보완 문맥 반복·도구 요청만 반환하는 역할 계약 문제), v6 6회/383.441초(cancelled, 빈 Builder 결과·미제안 계층 검토). 완료 증거로 계산하지 않는다. 호출 후 취소는 현재 응답을 저장한 뒤 중단했다.
- 독립 AI 전문가 2명이 실행·근거 계약과 온톨로지 의미 계약 검수. 전체 프로파일 의존성을 실제 원문 제공 수로 세던 문제, 66개 주택유형의 범주 누락, 조회 결과의 후속 입력·K5 의존성 누락, Scout 재개 해시 변경, 허용 ID/조건부 JSON schema 오류를 보완했다. 계층 ID를 Critic 쟁점 대상으로 허용하는 별도 회귀 확인도 통과했다. 추가 근거 요청은 응답의 쟁점 참조를 서버 ID로 치환·검증하고, 비교 대상 없는 개념 대응은 금지했다. 주 분석 원문과 보완 문맥을 분리하고, 빈 도구 요청만으로 분석 성공을 선언하지 않도록 출력 스키마·처리량 집계를 보완했다. 모든 역할에 구체적 결과/미해결 사유를 요구하고 Critic의 계층 검토는 실제 제안 쌍과 개수로 출력 스키마를 제한했다.
- 실제 의미 품질은 미확정: Relation Miner가 긍정 정의를 `negated`로 생성했고, v4 법령 Critic은 계층의 양방향 판정과 법령↔단지 표기 매핑 공백을 저장했으나 이 부정 오류를 쟁점에 모두 명시하지 않았다. CSV의 필드/값 분류도 사람 검수가 필요하다. 최종 CSV Critic에도 선택 원문에 없는 주택법상 상가/주택 구분의 단정과 240자 제한에서 문장이 끝나는 쟁점 2개가 남았다. 형식 통과·근거 ID 존재는 내용의 완결성이나 의미 지지를 보장하지 않는다. AI 전문가 검수는 현업 효용·법률 판단의 검증이 아니다.

## A2 보완 확인 (v8)

- reviewed 기준 조회에서 evidence → block → source version을 따라 검증한다. 실제 publish/decide로 만든 reviewed 버전의 분석 시작·용어 조회 회귀를 포함했다.
- 관련 테스트 **118 passed, 1 skipped**. A2 집중 테스트 43개 포함. 기존 HWPX 표본 부재 skip이며 전체 민원·12과제·다중 모델·Windows 실기는 추가하지 않았다.
- 동일 LH 두 자료의 A1 parse 2개를 재사용했다. 전체 6,220블록 구조 프로파일은 유지하고, 분석 선택을 법령 3블록 + 결정적 greedy 첫 사례 1행으로 사전 고정했다. 전체 대표 frontier 34묶음을 숨기지 않으며 이번 m=2, g=2이다. 전체 선택의 예전 최소 137회 문제를 호출 예산 증액으로 처리하지 않았다. 전체 분석은 `1+2m+2g`와 추가 수정 비용을 별도로 산정해야 한다.
- 첫 실행 `0d0db62392dd4a18a8a0aec351dc1da6`: **9회/522.802초**, 경과 532.975초, 검색 6회, partial. 후보 8개·관계 4개·Critic 2묶음을 저장했다. 두 Critic 모두 수정 필요 플래그를 끄고 매핑 공백을 보류했으며, 둘째 Critic의 추가 근거 요청은 당시 후속 입력으로 전달되지 않았다.
- 위 분기를 보완한 재개 `7b5f9eadbdad49d48b1cb1b5790149ee`: 성공 9단위를 그대로 재사용하고 revision **1회/69.655초**만 추가했다. 입력 **11,184자**, 실제 원문 11블록/K5 의존 12블록으로 필수 문맥을 자르지 않고 한도 안에 전달했다. 모델이 같은 후보를 수정과 보류 양쪽에 제출해 서버가 거절했다. 실패를 성공으로 바꾸지 않았고 추가 수정 호출은 수행하지 않았다.
- 최종 무호출 재개 `0fa455ec4eee4db8a089ba6cf7adbee4`: **누적 10회/592.457초**, 실행 경과 누계 603.272초, 검색 6회, **partial**. 성공 9·실패 1단위, 실패 후보 명시 보류 1건. 마지막 재개의 추가 모델 호출 0회. 두 재개를 별도 9/10회 실행으로 중복 합산하지 않는다.
- 최종 집계: 구조 조사 **6,220**, 분석 선택 **4**, 역할 처리 완료 **2묶음**, 원문 제공 **12블록**, 두 역할의 실제 근거 교집합 **1블록**, 근거 없는 처리 블록 2개, CSV Relation 무결과 1묶음. 분석 미선택 **6,216**, 원문 미제공 **6,208**, 두 역할 근거 미연결 **6,219**. 선택 범위 필수 미처리와 추가 읽기 미제공은 0이지만 전체 자료 분석 완료가 아니다.
- 실제 API 결과·읽기·검색·용어·scope 거절·근거 조회 통과. 후보 근거 **12건**의 원문·locator·version·parse 일치, parse **2개 유지**, 자료 포인터 불변. 이전 v7의 결과와 성공 단위도 변경 없이 재조회했다.
- 독립 AI 전문가 2명 검수로 새 성공 후보의 재개 후 검토 누락, 완료 단위 예산 재예약, Critic 전체 파생 의존 누락, 원문 미제공 ID 인용 허용, 수정 계층의 순환 검사 누락, 다중 CQ/이전 라운드/수정 후보 비교 누락을 보완했다. 실제 성공 9단위의 해시·출력·의존·원문 제공·시도 기록 동일성도 별도 확인했다.
- 의미 확인 한계: 법령 관계 4개는 이번에 모두 `affirmed`로 생성됐고 Critic 인용 7건(고유 관계 4개)은 원문과 일치했다. 원문 밖 법률 단정이나 240자에서 잘린 쟁점 설명은 이번 저장 출력에서 확인되지 않았다. CSV 열/값·코드 분류 오류 3건은 Critic이 놓쳤고 관계 방향은 unresolved다. 실제 계층/양방향 검토 **0개**, 실제 수정 성공 **0개**다. 수정 기능·계층 수정·ID/이력 보존은 집중 회귀로 확인했으며 이를 실제 의미 수정 성공으로 표현하지 않는다.
- 이번 실패 호출 비용 69.655초를 포함한다. 이전 개발 실패·취소 실행 40회/2,625.987초와 이전 v7 확인 9회/501.436초까지 포함한 누계는 **59회/3,719.880초**다. 재사용은 실제 호출로 더하지 않았다. 원장·원출력·확인 파일은 로컬 `data/knowledge/a2_smoke_20260930/knowledge.db` 및 `data/knowledge/a2_fix_20260930/{request,result,result_resume_attempt,result_resumed,verification}.json`에 보존하고 커밋하지 않았다.

## A3 연결과 한계

- D4 복구는 기존 `recovery_requests`에서 원인·실제 대상·역할·허용 범위로 구분한다. `extraction_missing`만 담당 원문 구간의 해당 Concept 또는 Relation에 보낸다. 같은 구간의 여러 누락은 `meanings`에 보존하고, 실행에 제출한 목록은 따로 고정한다. 문구가 달라져도 같은 작업을 반복 호출하지 않으며 뒤늦은 추가 누락은 `unattempted_meanings`에 남긴다.
- E4 복구 비교는 target과 겹치는 근거 span 및 관계의 직접 끝점으로 좁힌다. 담당 원문의 공유 전제·예외·표 헤더와 기존 승인 유형을 포함한 끝점 정의/근거는 필수다. 같은 후보와 정확히 같은 원문 span만 한 번 전달하며 `previous_signatures`는 서버에 둔다. `omitted_recovery_candidates`는 구간 불일치와 legacy span 미확인을 구분하고, `input_allocation`은 축소 전후 길이·예약 여유·한도 초과 사유를 기록한다. 필수 원문을 잘라 맞추거나 입력/출력 한도·종합3000자 여유를 늘리지 않는다.
- E5는 각 분석 뒤 기존 assemble을 복사본에서 실행해 실제 미완료 Builder/Critic 묶음을 `review_reservation`으로 예약한다. `role_time_estimates`는 미관측 역할의 recipe 호출 제한시간과 모델 identity, 관측 후 역할별 최대 elapsed×1.25 추정을 기록한다. 이후 추정은 상향하며 실제 누적 hardbudget과 구별한다. 다음 최소 분석과 예약을 감당할 수 없으면 기존 후보를 먼저 검수하고, 새 성공 unit이 있으면 갱신된 시간으로 같은 round의 남은 분석을 재판단한다. 미검수 또는 진전 없는 예산 거절은 partial로 종료한다. 주분석/검수가 수정·추가복구보다 앞선다.
- `execution_order`는 명시 priority를 유지한 anchor/CQ 순환 순서를 고정한다. CQ를 아직 모르는 분석 frontier는 source_group을 사용하며 Scout 선택은 각 묶음 내부 순서에 반영한다. `budget_transitions`와 그룹 `budget_allocation`은 실제 사용량·예약 추정·검수 전환을 구별한다. 뒤 round의 미완료 검수가 앞 round 재사용을 막지는 않으며 성공 unit/입력 해시는 재사용한다. 순서 배분은 모든 CQ의 분석/의미 해결을 보장하지 않는다.
- `evidence_error`는 기존 revision에서 후보 ID·의미를 유지하고 근거 선택만 보완한다. `endpoint`는 기존 Builder 연결 결과/명시 검수, `alignment`는 해당 기존 정의와 명시 대응 검수로 남긴다. `source_absent`는 부족한 원문·확인 범위, `budget_exhausted`는 실제 종료 사유를 기록한다. 기존 의미 오류는 `content_error`로 기존 수정 한도 안에서 처리한다. 자동 예산 증액은 없다.
- `proposals_created`도 의미 충족·사람 검수 완료가 아니며 `unresolved_recovery_requests`에 남는다. `semantic_status`와 `proposal_review_status`는 `unverified`다. `metrics.recovery_calls/recovery_model_s/recovery_attempted_tasks/recovery_remaining_by_cause`로 복구 호출·시간·실행된 작업·원인별 잔여를 조회한다. 성공 unit은 해시가 달라도 덮어쓰지 않으며 실패한 동일 복구 추출은 재개 시 반복 호출하지 않는다. 비교용 검색 결과는 추가 원문 분석으로 자동 승격하지 않는다.

- A3는 `GET /runs/{id}`의 result v2와 revision_history/effective_hierarchies/명시 보류를 함께 읽어야 한다. 관측·관계 최신값만으로 이전 Critic 판단을 수정 후 검수 완료로 간주하지 않는다. 기존 result 관측·관계·계층·별칭·양방향 판단·Critic 쟁점·공백·서버 후보 ID 및 기존 evidence/parse/version 참조를 소비한다. `unreviewed`, `validation`, 범위 밖 목록과 미처리 목록을 유지해야 한다.
- 다음 작업은 A3 변경 모델/의존 묶음/정본 변환. reviewed 버전 발행, 계보 head 승인 충돌, 검수 UI, K4/K5 소비자 갱신, A6 사람 시험은 후속 범위다.
- 별칭의 의미 동일성, 법률 적용 판단, 모든 범주의 의미 완전성, 실제 사람 검수 효과는 코드 검사나 AI 검수로 입증하지 않는다.

## 필수 문맥·수정 의미 보존·요구 충족 — v60/v61

- `context_contract=scope-v1`은 생성자의 필요한 문맥 제안과 Critic의 `required_meanings`를 구분한다. 의미·적용 대상·원문·현재 필드 또는 계층의 충족 위치를 저장한다. 선택된 관계·계층·끝점 정의가 바뀌면 과거 검수는 현재 판정으로 사용하지 않는다. 주변 문맥은 기존 구조 구간으로 제공하며, 한도를 넘는 문맥은 잘라 넣지 않고 공백으로 남긴다.
- 수정 후 Critic은 기존 이력의 before/after와 정상으로 지지됐던 의미를 직접 대조한다. 유지·근거 있는 정정·소실·판단 불가를 구분한다. 오류 제거와 정상 의미 보존 및 충분성이 모두 지지돼야 `correction_complete`다. 과거 지지는 영구 정답이 아니며 근거 있는 정정도 허용한다.
- `requirements`는 같은 직렬 실행기의 추가 검수 역할이다. synthesize 뒤, 복구 계획 전에 CQ/범위를 현재 후보·선택 구조·원문과 대조한다. 요구·후보·원문 범위·복구 대상 의미의 지문이 같으면 저장 결과를 재사용한다. `finish`는 모델을 호출하지 않는다. 필수 요구의 미충족/판단 불가는 전체 `partial`에 반영하되 개별 후보의 사람 수락과 구분한다.
- 입력이 큰 요구는 기존 분석 구간으로 나누고 해당 구간의 복구 요청만 대조한다. 부분별 누락 해결과 전체 문서 간 결합의 충분성은 별개다. 전체 결합이 확인되지 않으면 unknown을 유지한다. 생성 누락은 기존 Concept/Relation 복구로, 끝점 반박은 출처를 명시한 요구 검수 입력을 기존 Builder 교정으로 연결한다. 새 후보 수나 후보별 지지만으로 누락 의미를 해결 처리하지 않는다.
- 위 계약과 실제 모델의 판단 정확성은 별개다. 실제 확인 및 잔여 미탐은 [2026-10-04 확인 기록](../70_research/company_knowledge/ontology_scope_preservation_20261004.md)에 기록한다. recipe가 다른 과거 실행은 원장을 보존하고 변경 없는 재개를 거절한다.

- v61은 context 36,864를 사용한다. 모델 지원 한도·24,000자·보수적 바이트 상한·실제 입력 토큰 검사를 유지하며 요구 검수 예약을 후속 Builder/Critic/Revision의 실제 호출에서도 보호한다.
