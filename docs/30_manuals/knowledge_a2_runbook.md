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
- `baseline_version`은 회사 정의가 없는 현재 고정 메타모델을 식별한다. 범용 패턴 플랫폼은 추가하지 않았다.
- `base_ontology_version_id` 선택 시 reviewed 버전만 허용. 해당 정의의 근거는 A1이 고정한 parse/block 안에 있어야 한다. 역사 최초 단계는 빈 기준이며 이후 기준은 동일 역사 계보·현재 또는 이전 step만 허용. 현재/역사 기준을 혼합하지 않는다.
- `lineage_id` 생략 시 bundle별 current/historical 계보 사용. CQ 또는 `scope_items`가 최소 하나 필요하며 범위 항목의 내용 필드는 기존 CQ 계약과 같은 `question`이다.
- `GET /discovery/read?run_id=…&file_id=…`, `GET /discovery/search?run_id=…&q=…`: 고정 블록과 현재 K5 사용 상태로 조회. A2 검색은 BM25 순위와 출처군 순환 적용. A1/개발용 조회 유지.
- `GET /discovery/terms?run_id=…&label=…&term_type=any`: 고정 reviewed 기준과 해당 실행의 유효한 미승인 관측만 조회. 미래 단계·다른 실행 후보·활성 민원 collection fallback 없음.
- 기존 `/evidence/{id}`와 원본 다운로드 경로로 동일 원문·locator 재조회 가능.

## 조사·선택·역할

- 모든 완료된 선택 블록을 구조 조사한다. CSV는 모든 행의 필드·결측·형식·고유값 수를 조사하며 관측 분포와 허용 enum을 구분한다.
- 유형/종류/분류/구분/상태라는 열 이름은 범주 조사 신호로 사용한다. 의미가 검증된 필드 사전으로 취급하지 않는다. 그 밖의 고카디널리티 필드는 값별 대표 미선정 사유와 형식 분포를 남긴다.
- CSV 대표는 미충족 특징 최다 → 희소 특징 → 짧은 입력 → 안정 위치/ID의 greedy set cover. 실제 혼합·결측 특징을 포함한다. 완전한 의미 분석을 보장하지 않는다.
- 선택 법령·API·설명 원문은 전 블록 필수 목록. 표의 저장 헤더·행·인접 원문·locator를 함께 제공하며 다단 헤더·단위·각주 연결이 불명확하면 `unconfirmed`를 남긴다.
- 필수 원문, 예외/모순, 미방문 범주 순으로 출처군을 순환한다. Scout의 읽기 요청은 같은 우선순위 내 선택에 반영하며 이유를 저장한다.
- Schema Scout → 묶음별 Concept Miner → Relation Miner → Taxonomy Builder → Ontology Critic. 역할은 모두 기존 worker에서 직렬 호출한다.
- 개념은 type/vocabulary/entity/property_value/unresolved, 명시적 정의/사례 제안, 추상화 수준·검토 신호를 저장. 문서 관측과 기존 개념 대응은 분리하며 먼저 생성한 후보를 정답으로 사용하지 않는다.
- 후보는 근거와 CQ 또는 범위 연결을 검사한다. 범위 밖 발견, 검증 오류 후보를 보존·구분한다. 빈도/고유명사/사례 수로 클래스를 자동 승격·거절하지 않는다.
- 관계의 방향·부정·조건·시점·진술 성격을 저장. 계층은 제안된 쌍만 양방향 검토하고 is_a/instance_of/broader 대상 종류·자기 참조·is_a 순환·별칭 참조를 검사한다. 동치 자동 병합 없음.
- 원문 묶음은 법령/설명 최대 3,200자, CSV 최대 1,600자의 직렬화 비용을 기준으로 분할한다. 한 블록 자체가 한도를 넘으면 원문을 자르지 않고 입력 한도 검사에서 보류한다.
- Critic은 후보명과 예외/변경 질의로 동결 원문에서 별도 검색한 문맥을 받는다. 키워드 히트를 반증으로 간주하지 않는다. 도구 결과는 다음 역할 입력까지 연결하며 실제 제공 근거를 기록한다.
- Critic 쟁점은 서버 `di_` ID로 저장하며 `request_evidence.issue_id`도 같은 ID로 연결한다. 모델의 응답 내 i1/i2 참조는 정규화 후 폐쇄된 원장 참조로 검증한다.
- Pydantic 동작은 read/search/lookup_term/request_evidence/finish만 허용. 임의 URL·파일·shell·SQL·승인·활성화는 dispatch할 수 없다. 자료 밖 참조는 자료 필요로 남긴다.

## 저장·재개·종료

- Run에 입력 A1 ID·frozen_input·CQ/범위·기준 YAML·모델명/digest/컨텍스트·프롬프트/스키마/프로파일 버전·예산을 고정한다.
- `analysis_units`: 입력 해시·실제 prompt·원출력·검증 결과·호출 시도·시간·의존 근거. `frontier/profiles/tool_events/result`가 탐색 및 A3 연결 자료다. 결과 포맷 `a2-analysis-v1`.
- 호출 전후와 재개에서 K5 상태 확인. 원문뿐 아니라 전체 생성 의존성을 가진 요약/관측/lookup 결과도 사용 중단 근거를 포함하면 후속 입력에서 보류한다.
- endpoint는 loopback HTTP만 허용. localhost는 127.0.0.1로 고정하고 proxy·redirect를 사용하지 않는다. 설치 모델 digest와 선언 컨텍스트를 확인하며 실행 중 다운로드나 외부 모델 fallback 없음.
- 기본 상한은 48회/검색 24회/추가 2라운드/묶음 수정 1회. 실패 호출도 포함. 묶음마다 Builder/Critic 호출을 예약한다. 연장·자동 예산 증액 없음.
- 전체 입력 12,000자와 UTF-8 바이트 기반 보수적 토큰 상한·실제 prompt_eval_count를 확인한다. 긴 입력·JSON 오류·출력 절단은 실패이며 원문/결과를 조용히 잘라 빈 성공으로 만들지 않는다.
- `POST /runs/{id}/cancel`: 현재 모델 응답을 저장한 뒤 다음 호출 중단. `POST /runs`의 `{"kind":"discovery","retry_of_run_id":"…"}`로 동일 설정 재개. 성공 단위는 입력 해시가 같은 경우 재사용하고 실제 호출·검색·시간 예산은 누적한다.
- 저장 전 중단 호출은 `interrupted_before_result_commit`으로 구분한다. 다시 호출될 수 있다. 실제 시간 미확인분은 측정값에 합치지 않고 `interrupted_time_reserve_s`로 당시 timeout을 보수적으로 예산 차감한다.
- 구조 조사·실제 원문 제공·분석 성공·검수 쟁점 생성을 구분한다. 프로파일의 전체 의존 행은 원문 제공 건수로 세지 않는다. 주 분석 블록을 근거로 한 Concept/Relation이 모두 있어야 분석 완료 묶음으로 센다. 명시적 공백만 남은 묶음은 검토 의견이 있어도 미처리로 유지한다.
- 필수 미처리·파싱/모델 실패·사용 중단·예산 종료는 `partial`. `review_ready`는 초안 검수 준비이며 정확성·인간 승인·운영 활성화를 의미하지 않는다. 수정 Builder 결과는 미검수 수정 제안으로 별도 표시한다.

## 확인 결과

- Python 3.11.9. 변경 경계와 A1·수동 ontology·parse·K5·검색 회귀 테스트 **104 passed, 1 skipped** (6.67초). skip은 기존 로컬 HWPX 표본 부재. 전체 민원·12과제·다중 모델·Windows 실기는 실행하지 않았다.
- 테스트 실행: `python -m pytest app/tests/unit/test_knowledge_{discovery_inputs,discovery_run,discovery_analysis,service,parsers,api,ontology_run,extraction_run,extraction_store,snapshots,search}.py app/tests/unit/test_generation_ollama_metadata.py -q` (위 중괄호는 셸 파일 확장 표기).
- 실제 입력: 공공주택 특별법 제2조 TXT 3블록 + LH 전국 아파트 단지정보 CSV 6,217행. manifest `eb1379a48588ba7bf6c2be3dc109a797f9da1740ac5599aca85b33bdea315cdf`, current_discovery/step 0. A1 준비는 완료된 parse 2개 재사용.
- 실제 모델: `gemma4:31b-it-q4_K_M` / `qwen3.8:27b-q4_K_M`, digest는 실행에 고정. num_ctx 32,768, num_predict 4,096, think=false. 이번 확인의 호출 상한은 12회이며 자동 증액하지 않았다.
- 최종 실제 실행: `0bd5f59bcb60427b967c5be6c55c6bae` (`discovery-a2-v7`). **partial**. 실제 모델 **9회/501.436초**, 전체 **514.993초**, 검색 **8회**. 두 자료 묶음에서 Concept→Relation→Builder→Critic 결과를 저장했으며 CSV Relation은 명시적 공백으로 종료했다.
- 구조 조사 **6,220블록**, 실제 원문 제공 **15블록**, 주 분석 원문의 개념·관계 근거가 모두 있는 분석 **3블록**, Critic **2묶음/쟁점 5개**. 관측 **7개**, 관계 **4개**. 최종 계층 제안과 양방향 계층 검토는 **0개**이며 Builder의 보류 사유를 저장했다. v4의 4계층 양방향 결과를 최종 실행 성과로 합산하지 않는다.
- CSV 전 행에서 특징 **147개**, 대표·예외 **66행**을 결정적으로 선정했고 선정 기준의 미포함 특징은 0개다. 이는 LLM 분석 완료가 아니다. 원문 미제공 **6,205블록**, 미분석 **6,217블록**, 필수 미처리 **33묶음**, 미처리 특징을 가진 **33묶음**, 후속 원문 요청 미제공 **13블록**을 남겼다.
- 수정 Builder 2건은 **15,281자/16,762자**로 입력 한도를 초과해 호출 전 실패했다. 이후 묶음의 Concept/Relation/Builder/Critic 예약에 필요한 4회가 남은 호출 예산 3회를 넘어 종료했다. 한도를 늘리거나 원문을 잘라 성공으로 바꾸지 않았다.
- 실제 API에서 결과·읽기·BM25 검색·용어·근거를 재조회하고 scope 불일치/미선택 파일 거절을 확인했다. 근거 **13건**의 원문·locator·source version·parse ID 일치. 재개 `74644503da484960aa9a42f00dfdb1e9`는 성공 **9단위**와 후보 ID를 유지하며 **추가 모델 호출 0회**, parse **2개 유지**, 자료 포인터 불변. 재개도 같은 미처리 범위의 partial이다.
- 개발 실행을 포함한 실제 호출 누계는 **49회/3,127.423초**. 재개한 실행의 누적 수치를 중복 합산하지 않았다. 실행 원장과 확인 JSON은 로컬 `data/knowledge/a2_smoke_20260930/`에 보존하며 Git에는 요약만 포함한다.
- 개발 중 실제 실패도 별도 보존: v1 6회/422.293초(partial, action 인자·중복 참조 오류), v2 6회/182.823초(cancelled, 부분 객체 JSON schema 분기 오류), v3 7회/501.267초(cancelled, Critic 복수 local_ref 오류), v4 8회/678.613초(cancelled, 개념 대응 참조·쟁점 ID 미연결 확인), v5 7회/457.550초(cancelled, 보완 문맥 반복·도구 요청만 반환하는 역할 계약 문제), v6 6회/383.441초(cancelled, 빈 Builder 결과·미제안 계층 검토). 완료 증거로 계산하지 않는다. 호출 후 취소는 현재 응답을 저장한 뒤 중단했다.
- 독립 AI 전문가 2명이 실행·근거 계약과 온톨로지 의미 계약 검수. 전체 프로파일 의존성을 실제 원문 제공 수로 세던 문제, 66개 주택유형의 범주 누락, 조회 결과의 후속 입력·K5 의존성 누락, Scout 재개 해시 변경, 허용 ID/조건부 JSON schema 오류를 보완했다. 계층 ID를 Critic 쟁점 대상으로 허용하는 별도 회귀 확인도 통과했다. 추가 근거 요청은 응답의 쟁점 참조를 서버 ID로 치환·검증하고, 비교 대상 없는 개념 대응은 금지했다. 주 분석 원문과 보완 문맥을 분리하고, 빈 도구 요청만으로 분석 성공을 선언하지 않도록 출력 스키마·처리량 집계를 보완했다. 모든 역할에 구체적 결과/미해결 사유를 요구하고 Critic의 계층 검토는 실제 제안 쌍과 개수로 출력 스키마를 제한했다.
- 실제 의미 품질은 미확정: Relation Miner가 긍정 정의를 `negated`로 생성했고, v4 법령 Critic은 계층의 양방향 판정과 법령↔단지 표기 매핑 공백을 저장했으나 이 부정 오류를 쟁점에 모두 명시하지 않았다. CSV의 필드/값 분류도 사람 검수가 필요하다. 최종 CSV Critic에도 선택 원문에 없는 주택법상 상가/주택 구분의 단정과 240자 제한에서 문장이 끝나는 쟁점 2개가 남았다. 형식 통과·근거 ID 존재는 내용의 완결성이나 의미 지지를 보장하지 않는다. AI 전문가 검수는 현업 효용·법률 판단의 검증이 아니다.

## A3 연결과 한계

- A3는 `GET /runs/{id}`의 result 관측·관계·계층·별칭·양방향 판단·Critic 쟁점·공백·서버 후보 ID 및 기존 evidence/parse/version 참조를 소비한다. `unreviewed`, `validation`, 범위 밖 목록과 미처리 목록을 유지해야 한다.
- 다음 작업은 A3 변경 모델/의존 묶음/정본 변환. reviewed 버전 발행, 계보 head 승인 충돌, 검수 UI, K4/K5 소비자 갱신, A6 사람 시험은 후속 범위다.
- 별칭의 의미 동일성, 법률 적용 판단, 모든 범주의 의미 완전성, 실제 사람 검수 효과는 코드 검사나 AI 검수로 입증하지 않는다.
