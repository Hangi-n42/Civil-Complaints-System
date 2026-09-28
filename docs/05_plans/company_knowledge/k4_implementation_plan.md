# K4 구현 계획 — 개체 연결과 근거가 붙은 사실·관계 후보

- 버전: v1.0 / 확정일: 2026-09-27.
- 상태: **K4 기능 구현 및 제한된 실제 확인 완료(2026-09-28)**. 모델 추출의 누락·슬롯 오류는 잔여이며 [결과·한계](../../30_manuals/knowledge_k4_runbook.md)를 따른다. 아래는 확정 당시 설계와 범위다.
- 기준: [PRD FR-04·05](../../00_overview/company_knowledge_prd.md), [공통 계약](contracts.md), [재사용 결정](implementation.md), [K3 후보 정리 결과](../../70_research/company_knowledge/k3_candidate_review_2026-09-27.md).
- 목표: 검토한 온톨로지로 첫 공고군을 추출하여 실제 6개 단지를 연결하고, 출처·범위·시점이 붙은 사실/관계를 원문 옆에서 수정·결정할 수 있게 한다.
- 완료 경계: 검토 가능한 지식 후보까지. 운영 활성화·롤백은 K5, Local/Global 검색은 K6/K7, 정정 영향 전파는 K8. K3의 reviewed를 운영 활성 상태로 사용하지 않는다.

## 1. 입력과 선행 정리

1. K3 정리 버전 `46bfe87d89ea48caaf4d1ddde9fe9a7a`(개념 1+속성 8)를 기준으로 한다. 이는 AI 보조 개발 검토이며 현업 승인이 아니다.
2. `RentalType`, `FirstOccupancyMonth`, `Notice`, `NoticeIdentifier`, `NoticeIncludesComplex`의 최소 보충 정의를 추가한다. 근거·CQ·포함/제외를 가진 파일럿 JSON과 `scripts/prepare_knowledge_k4_schema.py`에서 기존 publish/decide를 재사용한다. 수동 입력 Run(origin=manual, llm_calls=0)을 명시하여 모델 산출물로 위장하지 않는다. 같은 보충 묶음을 재실행하면 기존 결과를 반환한다. 범용 YAML 편집기·스키마 업로드 UI는 만들지 않는다.
3. 보충 묶음에는 기존 HTML/CSV와 최신 PDF의 실제 선택 블록·파싱 버전을 새로 고정한다. 이전 K3 Run을 수정하지 않는다. 파일럿 JSON에는 짧은 근거와 출처 해시/locator를 두고 기기별 블록 ID는 등록 원장에서 해석한다. 기존 고정 평가 파일은 바꾸지 않는다.
4. 첫 K4 실행 입력은 최신 양산 공고 HTML `20796`, 관련 6개 단지 CSV, 같은 공고 PDF의 **단지 현황 표(인쇄 4쪽)**다. PDF는 이름 표기·최초입주를 확인하는 데 필요하므로 포함한다. PDF 전체/옛 공고/규정까지 확장하지 않는다.
5. 업무 질문은 DEV-02·DEV-04의 질문 문장만 사용한다. 조건·수량 범위는 추출 계약으로 보존하되 평가 기대값/정답 목록을 모델 입력에 넣지 않는다.
6. 시작 시 ontology_version_id, source_version_ids, parse_run_ids, 선택 block_ids·원문, 모델·프롬프트·매핑 버전을 Run에 고정한다. 기준 스키마나 자료 선택이 바뀌면 새 실행이다.

## 2. 추출·정렬·연결 흐름

```text
검토한 스키마 + 선택한 고정 블록
  → 명시적 필드 매핑(CSV/HTML 공식 단지 메타데이터)
  → 나머지 설명·표 문맥을 EXAONE으로 한 번씩 추출
  → 발췌 위치 정렬 + 공식 ID/검토 별칭 연결
  → 개체 연결·사실·관계 후보 저장
  → 원문 옆에서 수정·수락·보류·기각 / 연결 취소
```

### 2.1 구조가 명확한 값은 코드로 처리

- CSV의 단지코드·단지명·세대수·임대유형·주택유형·준공일·입주지정일, HTML에서 이미 추출한 해당 공고의 단지 메타데이터는 명시적 필드 매핑으로 처리한다.
- 매핑은 **검토된 슬롯 ID**를 사용하고 source_field→predicate_id 대응과 버전을 Run에 기록한다. 후보 이름 유사도로 슬롯을 추측하지 않는다. 원문에 없거나 해석 불가능한 값은 원문과 오류를 보존한다.
- `hshCnt` 값에는 해당 공고 메타데이터라는 출처 범위를 붙인다. 집계 의미는 명시적 설명이 있을 때만 구체화한다. 단지 전체라고 일괄 가정하지 않는다.
- CSV 날짜 문자열과 숫자의 단순 파싱만 수행한다. 복합 주택유형은 원문 문자열을 유지한다. 명시적 필드와 설명문에서 같은 숫자가 나와도 범위/출처가 다르면 별도 주장이다.
- 처음엔 선택 CSV에 있는 6개 단지만 등록한다. 전국 등록부 확장은 별도 필요가 생길 때 한다.

### 2.2 설명문·표는 기존 모델로 추출

- `STRUCTURING_MODEL`을 사용한다. 현재 EXAONE이며 민원 생성·평가 설정은 변경하지 않는다.
- LinkML의 `SchemaView`/`JsonSchemaGenerator`로 스키마를 해석하고 레코드 타입을 생성한다. 레코드는 선택된 개념과 속성/관계만 허용한다. 필드별 block_id·quote, 원문 단위·범위·조건·날짜 역할은 고정 provenance 봉투에 둔다.
- JSON Schema 생성 과정에서 정규화된 클래스 이름을 원래 안정 ID와 대응시킨다. 특히 `CONCEPT_001`과 JSON Schema의 `CONCEPT001`을 같은 문자열이라고 가정하지 않는다. LinkML root의 개념별 collection slot과 생성된 JSON Schema의 해당 property/$ref로 대응표를 만들고 경계에서 한 번 확인한다. 이름에서 밑줄을 임의로 제거하는 규칙은 만들지 않는다.
- 레코드 검사 후 각 슬롯을 개별 Assertion으로 변환한다. 원문 표기는 raw_value, 정규화 값은 value에 두고 월 정밀도는 string/precision=month로 유지한다. 201106→2011-06은 형식 정규화이며 2011-06-01 생성은 금지한다.
- 한 표 행을 쪼개지 않고 제목·열 이름·단지명·값 셀을 함께 제공한다. 설명문은 문단 단위. 이미 필드 매핑으로 처리한 동일 블록/필드만 LLM 대상에서 제외하고 제외 이유를 기록한다. 표/문맥을 구성할 수 없는 단위는 실패 또는 미해결로 보여준다.
- 원문 4,000자/묶음, 완성 프롬프트 12,000자, 출력 4,096토큰·컨텍스트 32,768을 초기 예산으로 한다. 모델 선언 범위 내에서 지정한다. 원문 단위 경계로 나누며 임의 뒤 자르기·추가 요약을 하지 않는다. 최초 실행에서 부족한 단계만 조정한다.
- **모델 호출은 비구조화 묶음당 1회, 정상 총 n회**다. 구조화 매핑·위치 정렬·ID 연결은 0회. n은 시작 전 실제 입력으로 계산해 표시한다. 사실별 채점·Qwen 재평가·자동 재작성 루프를 붙이지 않는다.
- 출력 잘림/JSON 오류는 해당 단위 실패. 유효 JSON 내 개별 후보의 잘못된 ID·근거는 그 후보의 validation_errors로 보존하고 수락에서 제외한다. valid/invalid/미처리 개수를 구분하여 무조건 전체 완료로 표시하지 않는다.

### 2.3 LangExtract는 정렬만 사용

- 선정 배포본: `langextract==1.7.0`. PyPI wheel의 Resolver.align 인자와 Python>=3.10 선언을 확인했다. 설치·프로젝트 통합 실행은 K4에서 한다.
- `Extraction(extraction_class=..., extraction_text=quote)` → `Resolver().align(..., token_offset=0, char_offset=0, enable_fuzzy_alignment=False, accept_match_lesser=False)`를 블록별로 호출한다. 반환 iterator를 소비해 문자 위치를 받는다.
- token-level exact 판정과 별도로 `block.text[start:end] == quote`를 확인한다. 반복 문구의 서로 다른 위치가 남으면 ambiguous다. 문맥/셀 또는 사용자가 선택한 정확한 구간으로만 해소한다. 토큰/바이트/브라우저 UTF-16 인덱스와 Unicode 코드포인트를 혼용하지 않는다.
- 표의 대상·열 제목·값은 여러 Evidence로 연결한다. 상위 표 제목은 데이터 값의 일부로 합성하지 않는다. 위치 일치가 관계·조건의 의미를 증명하지 않음을 화면에서 구분한다.
- `lx.extract`, provider, 원격 API, 별도 Ollama 호출은 사용하지 않는다. 필요한 패키지 충돌만 조정하며 병렬 파이프라인이나 대체 정렬기 다중 fallback을 만들지 않는다.

### 2.4 개체 연결과 취소

- 공식 ID는 `(namespace, official_id)`로 조회한다. 단지와 공고는 별도 namespace. CSV 등록부의 ID 존재·유형과 원문에서 해당 표기/코드가 같은 대상을 가리키는지 확인한다.
- 공식 코드가 명시된 경우 연결 대상을 결정적으로 제안한다. 후보 수락과 운영 활성화는 별개다. 원문에 없는 코드를 모델이 출력하면 승인 가능한 공식 ID로 승격하지 않는다.
- 코드가 없는 PDF 명칭은 검토된 별칭과 그 자료 범위를 우선 조회한다. 없으면 같은 선택 공고의 6개 단지를 후보 목록으로 제시하고 원문 이름·주소를 보여준다. 사용자가 연결하고 별칭을 수락한다. 임베딩 검색·유사도 임계값·LLM 판정은 추가하지 않는다.
- 별칭은 표기+대상+출처 범위+근거+검토 상태로 저장한다. 이름만 같은 다른 지역의 단지를 자동 병합하지 않는다.
- 물리적인 개체 삭제/병합 대신 **원문 표기→canonical entity 연결 결정**을 저장한다. 취소 시 연결 대상을 비우거나 이전 대상으로 되돌리고 전후 값을 이력에 남긴다. 실제 사실의 원문 표기는 보존한다.
- 해당 연결 revision에 직접 의존하는 사실은 accepted에서 proposed(재검토 필요)로 돌리고 dependency_changed 이유를 남긴다. 같은 트랜잭션으로 적용한다. 무관한 사실·2단계 이상 영향 탐색·모델 재추출은 실행하지 않는다. K8 변경 영향 엔진을 미리 만들지 않는다.

## 3. 저장 계약 — 기존 SQLite에 필요한 객체만 추가

기존 `runs/blocks/changesets/decisions/ontology_versions`를 재사용하고 아래 **4개 테이블**을 추가한다. 기존 JSON payload 저장 방식을 유지하며 전용 그래프 DB·ORM·이벤트 버스는 도입하지 않는다.

| 테이블 | 저장 내용·식별 규칙 |
|---|---|
| entities | 안정 entity_id, concept_id, namespace, official_id(없으면 null), 대표 표기, 등록 근거. `(namespace,official_id)` 고유 제약. P0는 개체당 주 공식 ID 하나, 추가 표기는 entity_links. 공식 ID가 없으면 서버 UUID를 쓰되 미확정 상태를 명시 |
| entity_links | 원문 mention/검토 별칭의 ID·revision, 원문 text·block/evidence, 대상 entity_id 또는 null, 연결 방법 official_id/accepted_alias/manual/unresolved, scope, review_status. 후보 대상 목록과 원래 연결을 보존 |
| assertions | ID·revision, subject_id/predicate_id, object_entity_id XOR value, raw_value, unit, scope, conditions[], exceptions[], dates[], evidence_ids[], field별 evidence 연결, ontology_version_id/run_id, 의존 link ID/revision, review_status·validation_errors |
| evidence | 부분 발췌 ID, block_id, quote, start/end, alignment_status. 블록과 유효 위치가 같으면 같은 근거 재사용; unmatched는 위치 null. 기존 K2의 블록 전체 evidence_id 조회도 유지 |

- 개체·관계 ID는 문자열 이름 변경으로 새로 만들지 않는다. 링크가 바뀌면 주장 대상을 몰래 덮어쓰지 않고 재검토 상태로 남긴다. 수락할 때 현재 link revision의 대상을 확정한다.
- 날짜 값 자체와 사실의 유효기간은 다르다. 준공일을 모든 사실의 valid_from으로 사용하지 않는다. 날짜 근거가 없으면 null/unknown, 문서 발행일·수집일은 별도 provenance다.
- 521/985/990처럼 범위가 다른 값은 공존하며 unknown 범위는 추정 보충하지 않는다. 수량 단위도 원문의 세대/호를 보존한다.
- 재시도 중 중복 방지는 `(run_id,unit_id,local_candidate_key)` 고유 키로 한다. 다른 원문 버전·범위의 동일 숫자를 내용 해시로 합치지 않는다.
- changesets는 kind=ontology(기존) 또는 extraction으로 구분. 개체 연결·사실 후보 ID와 검토 revision을 담는다. 기존 온톨로지 후보 응답 필드를 바꾸지 않는다.
- 수정 전후 payload와 결정자는 기존 decisions에 기록한다. 최신 payload+결정 이력이 K4 범위이며 불변 활성 snapshot 저장은 K5다.

## 4. Run·API·화면

### 실행 상태

기존 단일 executor에서 kind=extract 분기만 추가한다. 시작 전 고정 입력으로 단위를 만들고 각 단위의 성공 결과를 저장한다. 성공 단위를 재시도에서 재호출하지 않는다. 취소는 현재 호출 종료 후 적용하고 실패 단위만 다시 실행한다. 모델·프롬프트·매핑·정렬기 버전이 바뀌면 새 Run이다. parse 포인터와 ontology Run 결과를 변경하지 않는다. 범용 DAG는 만들지 않는다.

Run에 mapped/LLM 단위, processed/excluded blocks, succeeded/failed/unresolved 후보 수, 호출 수·모델 대기·전체 시간, frozen ontology/source/parse ID를 기록한다. 실패 호출도 집계한다. 미해결 후보가 있는 실행과 기술 실패는 별도 필드로 표시한다.

### API 확정

기존 `/api/v1/knowledge` 응답 봉투를 유지한다. 이 표는 K4 확정 계획이며 현재 endpoint 구현을 뜻하지 않는다.

| API | K4 추가 내용 |
|---|---|
| POST /runs | kind=extract, ontology_version_id, source_version_ids, 선택 block_ids, cqs. 단지 등록부 source_version_id를 별도 명시. 최초 실행은 reviewed만 사용. 재시도는 retry_of_run_id만 |
| GET /runs/{id}, POST /runs/{id}/cancel | 기존 경로 재사용, 추출 진행·사용 범위·호출 수·결과 changeset_id |
| GET /candidates | kind=entity_link/assertion 지원, 변경 묶음별 payload·근거·검토/정렬/오류 상태. 기존 concept/attribute/relation 조회 보존 |
| POST /changes/{id}/decisions | extraction 묶음에도 expected_changeset_revision과 accept/modify/defer/reject 사용. 수정은 허용 필드만. 링크 취소는 action=unlink(링크만), 짧은 사유 필수. 오래된 화면은 409 |
| GET /entities | concept_id?, namespace?, official_id?, q?에 해당하는 소량 후보. canonical ID·명칭·연결 상태. fuzzy 자동 병합 없음 |
| GET /entities/{id} | 명칭·공식 ID·검토된 별칭·연결/사실 후보 조회. 운영 지식 조회로 표시하지 않음 |
| GET /evidence/{id} | 신규 부분 발췌와 기존 K2 전체 블록 근거를 같은 봉투로 조회 |

modify 대상: 링크 target_entity_id/별칭 scope, 사실 value/raw_value/unit/scope/conditions/exceptions/dates/evidence와 subject/object link. stable id·run/source provenance를 임의 변경하지 않는다. 새 대상은 등록된 동일 타입 개체만 선택한다. 존재/타입/정렬 검사 후 저장하며 invalid 후보를 수정할 수는 있어도 해소 전 수락은 불가다.

### 화면

`/knowledge`에 ‘개체·사실’ 탭 추가. 자료/온톨로지 선택 → 추출 → 후보 목록과 원문 대조 순서다. 공식 코드·원문명·연결 대상·방법을 보여주고 사실은 값/단위/범위/날짜 역할을 편집한다. 대상 후보 선택·별칭 수락·연결 취소·묶음 결정을 지원한다. 참조 개체 연결을 먼저 또는 같은 요청에서 수락하며 숨은 자동 수락은 하지 않는다. 기존 온톨로지 UI 전체를 범용 폼 엔진으로 재작성하지 않는다.

## 5. 파일별 작업과 재사용

| 파일 | 최소 변경 |
|---|---|
| app/knowledge/repository.py, schemas.py | 4개 테이블·추출/링크/주장/부분 근거 DTO |
| app/knowledge/extraction.py (신규) | 명시 필드 매핑, 스키마 기반 추출·정렬·연결·단위 실행. 커지기 전 범용 계층 분리 금지 |
| app/knowledge/service.py, ontology_schema.py | extract dispatch·근거 조회, extraction 결정 분기. K3 저장/검증을 무관하게 리팩터링하지 않음 |
| app/api/routers/knowledge.py | 위 API 접점·기존 오류 봉투 |
| frontend/components/KnowledgeExtraction.tsx (신규), app/knowledge/page.tsx | 개체·사실 탭, 원문·링크·편집·결정 UI |
| scripts/prepare_knowledge_k4_schema.py + 파일럿 보충 JSON | 첫 공고군의 누락 정의만 기존 정본/결정 경로로 추가 |
| requirements.txt, docs/third_party/knowledge_k3_reuse.md | LangExtract pin·필요한 전이 의존성, 출처/라이선스/사용 범위 기록 |

LinkML은 직접 호출, LangExtract는 정렬 API만 직접 호출한다. OntoGPT의 표기→ID 조회→검토 분리 방법만 로컬 등록부로 재구현한다. SKOS식 별칭, PROV식 출처, 조건이 붙은 N-ary 주장 표현은 필드 설계로 반영하며 RDF 서버·규칙 엔진을 설치하지 않는다.

## 6. 필요한 확인과 완료 기준

자동 확인은 새 기능의 아래 4개 경계 묶음에 한정한다. 기존 13개 전체나 민원 테스트를 반복하는 것을 선행 조건으로 두지 않는다.

1. **참조·형식:** 등록부에 없는/다른 타입 ID, 잘못된 슬롯, 정렬 실패·반복 인용을 수락하지 않음. 연결 근거와 값 근거가 독립적으로 남음.
2. **보존·검토:** 서로 다른 범위 수량·월/일 역할 보존, 수정/별칭/연결 취소 이력, 직접 의존 후보 재검토, 오래된 revision 충돌.
3. **재시도:** 성공 호출 재사용·중복 없음·입력 고정·기존 parse 포인터 보존.
4. **기존 경계 호환:** K2 전체 근거와 K3 후보/결정 응답 유지. 새 정렬 어댑터의 실제 한국어 발췌 1건·반복 문구 1건 확인.

실제 통합은 **같은 공고군 1회**: HTML+CSV+PDF 단지표 → 6개 단지 코드 연결 → PDF 별칭 검토 → 범위가 다른 수량과 금산 날짜 역할 확인 → 사실 수정/보류 → 연결 취소 후 직접 의존 상태 확인 → 재조회. 오류가 나면 해당 단위만 수정·재확인한다. 전체 12과제·모델 비교·현업 승인·Windows 장비 확보는 K4 선행 조건이 아니다.

완료 보고에는 실제 대상/후보 수, 근거 일치·미해결 수, 호출 수·시간, 수락/수정/보류/기각, 발견 오류와 미검증 범위를 기록한다. 데이터 정답/기관 도입/운영 활성화 입증과 구분한다.

## 7. 구현 순서·일정·결정

- **1일차:** 5개 정의 보충 → 저장/DTO → 필드 매핑·EXAONE 추출·LangExtract 정렬·공식 ID 연결·추출 Run. 확인: 첫 단위가 근거를 가진 후보로 저장됨.
- **2일차:** 개체·사실 검토 화면·연결 취소·재시도 → 위 경계 확인 → 첫 공고군 통합 → 결과 기록. 확인: 수정/취소 후 재조회에서 상태와 근거 유지.
- 2일은 기존 마일스톤 추정치이며 납기 보장이 아니다. 새로운 품질 문제가 나오면 그 문제만 잔여로 기록한다. 품질을 높이겠다는 이유로 자동 평가 루프·다중 모델 비교·안전 플랫폼을 추가하지 않는다.
- 다음 단계 K5: 검토된 정의·개체·주장·근거를 묶은 활성 스냅샷과 사용 상태 관리.
- 현재 사용자 결정이 필요한 사항 없음. 이 계획에서 일반 구현 선택을 확정했으며 K4 코드 구현·패키지 설치·모델 실행·GitHub 변경은 아직 수행하지 않았다.

## 근거·의존성 확인

- [LangExtract 1.7.0 배포 메타데이터](https://pypi.org/pypi/langextract/1.7.0/json): Python>=3.10. wheel SHA-256 `908f8ec696ab13578cdc3862efcf1a4fda929ae426410d99e86977d50e52136d`의 Resolver.align 인자를 정적으로 확인. 설치/의존성 resolver 결과는 아님.
- [고정 소스의 Resolver](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/resolver.py): align iterator·offset·fuzzy/lesser 선택 접점. 원본 코드의 토큰 일치와 원문 문자/의미 일치를 구분.
- 선정 원문·수량·날짜 근거는 위 K3 정리 기록 및 로컬 원장의 실제 블록을 사용. 평가 정답 파일은 이번 정리에 사용하지 않음.
