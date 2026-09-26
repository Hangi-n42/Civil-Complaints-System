# 회사 지식 워크벤치 — 구현 계획·오픈소스 재사용

- 문서 버전: v1.7
- 문서 정리·코드 정적 확인일: 2026-09-26
- 상태: K2·K3 구현 및 Mac 확인 완료, 나머지는 구현 계획. [K2 실행 결과](../../30_manuals/knowledge_k2_runbook.md).

[PRD](../../00_overview/company_knowledge_prd.md) · [아키텍처](architecture.md) · [마일스톤](milestones.md)

PRD v1.2의 API 초안·재사용 설계·버전 조정 내용을 분리했다. 요구사항을 축소하지 않으며, S1~S22 출처는 [PRD 근거 목록](../../00_overview/company_knowledge_prd.md#15-근거-목록과-요구사항-연결)에 있다.

## 1. 제안 API 목록

필드·상태·endpoint의 단일 기준은 [P0 최소 데이터/API 계약](contracts.md)이다. Pydantic/OpenAPI는 해당 기능 구현 시 함께 작성한다. 이번 문서 고정 때문에 P0 전체 빈 라우터·서비스를 선행 생성하지 않는다. 기존 민원 endpoint는 유지한다.

**P1 연결 결정:** 기존 `/api/v1/qa`의 case_id 계약을 억지로 변환하지 않는다. 별도 `POST /api/v1/knowledge/assist`에서 민원 query, snapshot_id, 선택한 assertion_ids, scope, as_of를 받고 `answer, knowledge_citations, snapshot_id, status_revision, status_checked_at, limitations`를 반환한다. 서버가 선택한 스냅샷의 주장·근거와 최신 사용 가능 상태·적용 범위를 다시 확인한다. 미검토·제외·스냅샷 외 ID는 거부하며 클라이언트의 원문·상태를 신뢰하지 않는다. 적용 범위를 확인할 조건이 부족하면 추가로 필요한 조건을 표시한다. 생성 직전에 사용 상태를 확인하고 응답 확정 전 status_revision이 바뀌면 선택 근거를 재확인한다. 제외된 근거가 있으면 성공 답변 대신 재조회 필요를 반환한다.

생성 저수준 호출은 재사용하되 지식 출처 형식에 맞는 인용 확인을 수행한다. 기존 민원 답변/평가와 구분한다. 기존 QA 자체에 지식을 통합하는 변경은 이 어댑터 검증 후 별도 계약 변경안으로 다룬다.

## 2. 재사용 결정과 선정 이유

**선정 원칙:** 요구를 충족하는 기능은 패키지의 공개 API로 호출한다. 접점 차이는 얇은 어댑터로 변환하고, 패키지 내부를 대폭 바꿔야 하는 기능만 필요한 소스·프롬프트를 이식하거나 같은 방법을 재구현한다. 기존 버전과의 충돌은 조정 작업이며 단독 탈락 사유가 아니다. 선택 기준은 P0 계약 충족, 구현·유지 비용, 로컬 실행과 Windows 호환성이다. 아래는 설계 채택이며 설치·한국어 품질 검증 완료를 뜻하지 않는다.

| 대상 | 채택 방식 | 실제 사용할 기능과 최소 수정 | 연결 요구 |
|---|---|---|---|
| **pdfplumber** [S14] | 패키지 직접 사용 | `open`, 페이지의 단어·좌표·`find_tables` 결과 사용. 페이지/표/셀을 ParsedBlock·Evidence로 변환하는 어댑터만 작성 | FR-02 |
| **python-hwpx** [S14] | 패키지 직접 사용 | K2에서는 공개 `TextExtractor`·`ParagraphInfo` 읽기 API 사용. package part·구역·표·셀 경로를 원문 위치로 매핑. 라이브러리에 없는 위치 메타만 ZIP/XML로 보완 | FR-02 |
| **LinkML + linkml-runtime** [S15] | 패키지 직접 사용 | `SchemaView`로 클래스·슬롯·범위 해석, `JsonSchemaGenerator`로 추출용 JSON Schema 생성. 자체 스키마 컴파일러 대신 기존 생성기를 사용 | FR-03·05 |
| **LangExtract** [S16] | 위치 정렬 부분 직접 사용 | `Extraction`과 `Resolver.align`에 기존 Ollama가 만든 발췌 후보와 원문 블록을 전달. 문자 범위·정렬 상태를 Evidence로 변환. 별도 추출 LLM 호출은 하지 않음 | FR-02·05 |
| **OntoGPT 작성 자산** [S13] | 템플릿·지침·검사 일부 이식 | author-template skeleton의 필드/범위/설명/예시 구조와 validator의 root·range·prefix 검사 부분을 가져와 LH용으로 수정. 원본 전체 CLI·엔진은 호출하지 않음 | FR-03 |
| **AutoSchemaKG** [S17] | 개념화 프롬프트 이식, 실행부 재구현 | 개체·사건·관계 표현을 나누는 개념화 지침을 한국어/CQ/원문 근거 출력에 맞춤. pickle·CSV 중간 그래프 대신 기존 Run/후보를 입력으로 사용 | FR-03 |
| **OntoGPT grounding·TermValidator** [S13] | 방법을 업무 계약에 맞게 재구현 | 추출 표기→공식 ID 조회→별칭/상태 확인을 분리. OAK 서비스 대신 LH 등록부를 조회하고 점검 불가·표기 차이를 검토 상태로 반환 | FR-04 |
| **LightRAG** [S18] | 검색 방법 재구현 | 개체·관계와 텍스트 근거를 함께 사용하는 검색을 SQLite+기존 검색 구성요소에 연결. 병합 설명·원문 목록을 승인 원장으로 사용하지 않음 | FR-11 |
| **Microsoft GraphRAG** [S19] | map/reduce 프롬프트 이식, 실행부 재구현 | 근거 있는 요점 추출→종합 지침을 사용. community report ID를 assertion/evidence ID로 바꾸고 공통점·차이·예외를 명시. 단일 깊이·순차 실행 | FR-12 |
| **DeepDiff + difflib** [S20] | 직접 사용 | DeepDiff는 ID로 대응한 구조화 사실·온톨로지의 필드 변경, difflib는 원문 구간 변경 표시. 변경 결과→재검토 후보 연결만 자체 구현 | FR-07 |
| **SQLite·기존 검색/생성·Next.js** | 기존 자산 직접 사용 또는 어댑터 | 원장 트랜잭션, 제한 관계 조회, 검색 순위 결합, Ollama 호출, 검토 화면의 공통 UI. 민원 전용 객체는 지식 DTO로 대체 | FR-01·06·08~12 |
| **LOT·Ontology 101·CQ4OE/LLMs4OL** [S21] | 방법론 적용 | 질문→필요 개념/관계→원문 대응, 용어 발견과 관계 제약 검토 분리. 총 12개 과제에 포함 | FR-03, PRD §12 |
| **SKOS·PROV-O·SSSOM·N-ary 관계·Graphiti 시간 구분** [S22] | 데이터 모델에 반영 | 대표명/별칭, 출처·생성 활동, 매핑 방법, 조건이 붙은 주장, 업무 적용일/기록일 분리 | FR-03~08 |

OntoGPT 전체 SPIRES의 재귀 추출·OAK grounding은 LH 등록부와 근거 위치·검토 상태에 맞춘 변경이 필요하다. AutoSchemaKG 전체 실행부는 그래프 파일·모델 호출·개념 ID 생성까지 교체해야 한다. LightRAG/GraphRAG 전체 검색기는 저장·문맥·모델·콜백 계약의 적응 범위가 크다. 따라서 이 부분은 **버전 충돌 때문이 아니라 변경해야 할 업무 계약의 범위 때문에** 좁은 자산 이식·재구현을 선택한다. 원본 엔진의 일반적 성능이 낮다는 판정은 아니다.

## 3. 파서·추출·원문 위치 접점

라이브러리 객체는 어댑터 내부에서만 사용하고 API/SQLite에는 [최소 계약](contracts.md)으로 저장한다. 새 모듈을 범용 플러그인 플랫폼으로 만들지 않는다.

```text
CSV/HTML + pdfplumber/Python-HWPX
  → ParsedBlock(source_version, parse_run, block_id, text, locator)
  → 기존 Ollama + LinkML에서 생성한 JSON Schema
  → 추출 레코드 + 필드별 원문 발췌
  → LangExtract 위치 정렬 + 코드의 원문 대조 + 로컬 ID 연결
  → Assertion 후보 → 사람 검토 → 활성 Snapshot
```

- CSV는 `csv`, HTML은 본문 요소만 추출하는 어댑터로 처리한다. PDF는 문자·셀 좌표와 좌표계를 보존한다. HWPX는 공개 모델의 원문 구조를 사용하며 Markdown 출력만을 근거 원장으로 저장하지 않는다. 원본 bytes는 재저장하지 않고 별도로 보존한다. python-hwpx는 커뮤니티 라이브러리이며 한컴 공식 SDK로 소개하지 않는다.
- ParsedBlock에는 원문 버전, 파싱 실행/파서 버전/옵션 해시, 블록 순서, 표의 행/열·병합 범위, 원문 텍스트를 둔다. 같은 bytes를 새 파서로 처리한 것은 새 파싱 실행이며 공식 정정이나 새로운 원문 버전이 아니다.
- LangExtract는 LLM 호출 경로 대신 **후처리 정렬기**로 사용한다. 검증된 추출 JSON의 발췌를 `Extraction`으로 변환하고 `Resolver.align`을 블록 단위로 호출한다. 초기값은 `enable_fuzzy_alignment=False`, `accept_match_lesser=False`다. 선택한 배포본에서 이 호출 계약을 확인한다.
- 정렬 결과와 별개로 저장된 원문의 `text[start:end]`를 발췌와 비교한다. 반복 문구는 블록·셀·주변 문맥까지 확인하며 위치가 복수이면 자동 확정하지 않는다. 원문 정규화가 있으면 원문 offset 대응을 보존한다. offset은 Unicode 문자 기준이며 UTF-8 바이트 위치나 FE의 UTF-16 인덱스와 혼용하지 않는다.
- 하나의 관계·조건이 여러 셀/문장을 필요로 하면 여러 Evidence를 연결한다. 단어 위치가 맞는다는 이유만으로 관계의 의미까지 검증됐다고 표시하지 않는다. 조건·예외를 일치하지 않는 인용에 덧붙일 수 없다.

## 4. 온톨로지와 ID 연결의 구체적 구현

**스키마의 정본은 하나다.** SQLite의 OntologyVersion에 LinkML 스키마 표현을 버전 있는 데이터로 저장한다. YAML 내보내기·조회용 Concept 인덱스·JSON Schema는 여기서 파생한다. 운영자가 별도의 Pydantic 도메인 모델과 LinkML을 각각 편집하게 하지 않는다. Pydantic은 API 봉투·후보·Evidence·Assertion·검토 상태 같은 고정 메타모델을 담당한다.

1. **CQ 기반 범위:** K1의 과제에서 필요한 개념·관계·근거를 연결한다. 모델이 개념을 제안할 때 관련 CQ와 원문 위치를 남긴다. 새 확인용 과제의 정답은 초안 프롬프트에 넣지 않는다. CQ는 제품 질문이고 고정 평가 정답은 별도다.
2. **초기 후보:** 온톨로지가 없으면 고정 출력 구조로 원문 표기·관계 표현을 수집한다. AutoSchemaKG의 개념화 지침을 가져와 상위 업무 개념 후보를 만든다. 임의 이웃 표본·무작위 셔플·개념명 해시를 의미적 동일성 기준으로 쓰는 부분은 가져오지 않는다.
3. **OntoGPT 자산 이식:** `template_skeleton.yaml`의 구조에서 생의학 클래스·prefix·annotator를 LH 개념과 로컬 등록부 정책으로 바꾼다. 프롬프트의 필드 정의·예시는 재사용하되 세미콜론 목록 대신 JSON 배열을 사용한다. `validate_template.py`의 일부 검사를 프로젝트의 SchemaView 입력에 맞춰 이식하고 OntoGPT core import·annotator 다운로드·패키지 디렉터리 복사·Python codegen/import는 제거한다. 수정 후 원본 OntoGPT validator와 동일한 프로그램이라고 부르지 않는다.
4. **승인 스키마 기반 추출:** 승인된 스키마의 클래스·슬롯으로 JsonSchemaGenerator를 실행하여 추출 레코드 계약을 만든다. 원문 발췌·block_id를 붙이는 고정 provenance 봉투와 함께 Ollama에 전달한다. 생성한 JSON Schema로 레코드를 검사한 뒤 슬롯을 Assertion의 주체/관계/객체·값으로 변환한다. 참조 대상 ID의 존재·타입은 DB에서 별도 검사한다.
5. **지원할 표현 범위:** P0는 자료형·필수 여부·목록·enum·허용 클래스/관계·명시적 제약을 중심으로 한다. 복잡한 법률 조건은 원문과 적용 범위로 보존한다. LinkML→JSON Schema→Ollama 변환에서 지원하지 않는 제약은 표시하고 서버 검증/사람 검토로 남긴다. 조용히 제거하거나 임의의 제약으로 대체하지 않는다.
6. **로컬 grounding:** 모델은 원문 표기와 실제 인쇄된 코드 후보를 반환한다. 코드는 `(발행기관/네임스페이스, 공식 ID)` 존재와 대상 문맥을 확인하고 검토된 별칭을 조회한다. 모호한 이름은 후보 목록으로 둔다. 원문 표기·concept_id·entity_id·연결 방법·근거·검토 결과를 구분한다. OntoGPT의 AUTO ID/첫 annotator 결과/검증 생략을 승인된 LH ID로 승격하지 않는다.

새 스키마 후보를 시험 추출에 사용하면 해당 후보 버전을 Run에 기록하고 결과를 비활성으로 둔다. 일반 조회에는 그 스키마와 모든 의존 항목이 검토·활성화된 결과만 사용한다. 스키마가 바뀔 때 영향 받은 사실만 재검토한다.

## 5. Local/Global 검색에서 가져올 것과 바꿀 것

**Local — LightRAG의 검색 구성을 현재 아키텍처로 구현한다.** 공식 ID·검토 별칭으로 대상 후보를 찾고, SQLite에서 활성·사용 가능한 관계를 최대 2단계 탐색한다. 관련 Evidence를 모으고 기존 BM25/벡터 검색 구성요소로 원문 후보를 보완·정렬한다. 문서 필터·상태 확인은 순위 결합 전후에 적용하며 검색 엔진의 필터 경로만 신뢰하지 않는다. 조건·예외 근거를 단순 순위 때문에 버리지 않고 들어가지 않으면 부족 범위를 표시한다.

기존 RRF 단계는 `RetrievedDoc`/stage 계약을 사용하므로 운영 Search 결과를 그대로 넣지 않는다. 지식 `evidence_id`를 `docid`로 매핑하는 작은 어댑터로 재사용하고, 지식 원문은 민원 collection과 분리한다. 단순 두 단계 조회는 SQL로 끝내고 추가 경로 알고리즘이 실제 필요한 경우에만 기존 NetworkX를 파생 그래프로 사용한다. LightRAG의 병합 저장소·자동 추출·모델 공급자·별도 벡터 저장을 중복 도입하지 않는다.

**Global — GraphRAG의 map/reduce 프롬프트를 이식하고 실행 경계를 바꾼다.** [map/reduce 원본](https://github.com/microsoft/graphrag/tree/769542fbf1d8e5b4c6a8677fefc34621c87894c5/packages/graphrag/graphrag/prompts/query)은 근거 있는 요점과 종합을 분리한다. 해당 지침을 한국어 질문·원문 인용·조건/예외 구조로 수정한다. 입력은 community report가 아닌 선택 범위의 활성 Assertion과 Evidence다.

- 전체 입력이 예산 안에 들면 한 번 종합한다. 초과하면 개념/주제와 적용 범위를 기준으로 묶되 자료 출처를 유지하고, 각 묶음 요약 후 한 번 종합한다. 묶음 처리는 순차 실행한다. 정상 처리의 생성 호출은 직접 종합 1회 또는 묶음 수 g에 대해 g+1회이며 실제 실패/재실행은 별도 합산한다.
- 중간 결과는 `points[{text, assertion_ids, evidence_ids, conditions, exceptions}]`와 실제 사용/누락 범위를 가진다. 원본 프롬프트의 report ID 인용을 원문 Evidence 인용으로 바꾸고, 중요도 점수만으로 예외·상충 조건을 삭제하거나 reference ID를 5개로 잘라 원장의 근거 목록을 손실시키지 않는다. 화면 인용을 접더라도 전체 목록은 유지한다.
- 원본 엔진의 점수 기반 요점 선택·병렬 호출·파싱 실패를 빈 점수로 바꾸는 처리는 그대로 가져오지 않는다. 실패한 묶음은 실패/부분 처리로 표시한다. 최종 입력이 여전히 크면 제외 범위와 한계를 표시하고 추가 다층 요약을 자동 생성하지 않는다.
- P0 중간 요약은 요청 안에서만 유지한다. Run에 `snapshot_id`, 사용한 `status_revision`, 자료 범위, **질문/질문 해시**, 모델·프롬프트·스키마 버전과 실제 의존 assertion/evidence ID를 기록한다. 질문 간 재사용·영속 요약 캐시·무효화 시스템을 만들지 않는다. 응답 전 상태 변경으로 사용할 수 없어진 근거는 stale로 반환한다.
- 사용·제외 자료 목록과 상태는 DB에서 계산한다. LLM이 생성한 출처 목록을 전체 처리의 증거로 삼지 않는다. 공통 규칙은 실제 공통 범위가 확인된 경우만 묶고, 개별 완화 조건·현행성 불명을 함께 표시한다. 주요 사실의 최종 인용은 중간 요약 자체가 아닌 원문까지 연결한다.

두 검색은 기존 생성 호출만 재사용하며 민원 Q0~Q7 평가 루프를 호출하지 않는다. 관계 자동화와 기본 검색의 비교는 PRD §12의 B1/B2에 포함하고 LightRAG·GraphRAG 전체 플랫폼별 별도 벤치마크를 추가하지 않는다.

## 6. 변경 관리·표준·검토 도구 적용

- **변경 비교:** 공식 버전 계열 안에서 대응 블록은 `difflib.SequenceMatcher(..., autojunk=False)`로, ID별로 대응한 개념/사실의 구조는 DeepDiff로 비교한다. 순서가 의미 있는 조건·절차·표 행을 `ignore_order=True`로 통째로 비교하지 않는다. 명시적으로 집합인 필드만 정렬하며 AND/OR·부정·단위·예외를 정규화로 지우지 않는다. 정정 여부·영향·철회 결정은 라이브러리 diff 결과와 구분한다.
- **SKOS:** Concept의 대표명·언어·별칭·정의·범위, 상하위/관련 개념을 구분한다. 실제 단지 Entity의 동일성 판단에 개념 매핑 관계를 대신 사용하지 않는다.
- **PROV-O와 N-ary 관계:** SourceVersion/Assertion의 파생 출처, Run/Decision의 작업과 수행자, 조건·시점이 붙은 Assertion을 연결한다. PROV의 Entity는 단지 Entity보다 넓은 출처 객체 개념이다.
- **SSSOM:** 연결 후보에 주체·대상·매핑 관계·방법·근거·작성자·시점을 남기는 방식을 참고한다. 유사도를 exactMatch로 자동 확정하지 않는다. P0 JSON/SQLite 매핑을 SSSOM 적합 파일이라고 주장하지 않는다.
- **Graphiti:** 업무 적용 시각과 시스템 기록 시각을 분리하는 방법을 사용한다. 에피소드 시각이나 문서 수집일로 시행일을 채우는 자동 추론은 채택하지 않는다. Snapshot/AvailabilityHistory는 프로젝트가 직접 구현한다.
- **OpenRefine·Label Studio:** 후보 비교·원문 강조·사람의 선택이라는 검토 방식을 기존 Next.js 화면에 구현한다. OpenRefine은 일회성 CSV 정리에 선택적으로 사용할 수 있으며 결과는 후보 CSV로 다시 등록한다. 외부 도구의 수정이 원장을 직접 덮어쓰지 않는다.

| 이번 기본 구성에 넣지 않는 후보 | 이유와 다시 사용할 조건 |
|---|---|
| Docling | pdfplumber가 필수 표의 행·셀·근거를 복원하지 못할 때 같은 실패 자료로 확인하여 해당 형식의 파서로 교체/선택. 로컬 문서 모델을 그대로 쓰고 Evidence 어댑터만 작성. 자동 다중 파서 fallback은 만들지 않음 |
| pypdf·PyMuPDF/4LLM·Unstructured | 같은 파싱 책임을 중복 배치하지 않음. 본문 PDF만 필요한 범위는 pypdf 대안, 별도 렌더/형식 요구는 후속 검토. PyMuPDF 계열의 배포 라이선스와 모델/시스템 의존성은 별도 확인 |
| OntoGPT 전체 엔진·OAK | 외부 온톨로지 grounding이나 SPIRES 재귀 추출이 실제 필요할 때 해당 adapter/engine 사용. 현재는 LH 등록부와 근거/검수 계약 때문에 필요한 부분만 이식 |
| Instructor | 기존 Ollama JSON Schema·Pydantic 검증과 기능 중복. 추가 공급자·출력 계약에서 실제 중복 코드를 줄일 때 사용 |
| Graphiti·LightRAG·GraphRAG 전체 플랫폼 | 현재 원장·모델 호출·인덱스를 교체하는 비용보다 좁은 재사용이 유리하다는 설계 판단. 규모/외부 계약이 바뀌면 활성 스냅샷의 파생 검색기로 연결할 수 있으나 지금 다중 엔진 체계를 구축하지 않음 |
| RDFLib·pySHACL·Protégé | RDF/OWL 교환 또는 SHACL 검수 산출물이 요구될 때 직접 사용. LinkML 전이 의존성에 RDFLib가 설치되어도 RDF 제품 기능이 구현된 것은 아님 |
| Label Studio·Argilla 서버 | 여러 평가자의 지속적 라벨링이 필요할 때 별도 도구로 사용. 지금의 단일 운영자 검수 화면·활성화 흐름을 중복 구현하지 않음 |

CQ4OE/LLMs4OL의 연구 데이터는 LH 정답으로 가져오지 않고 질문→용어→관계 제약의 분리만 적용한다. RDF/SKOS/PROV/SHACL 표준 준수나 논문 재현을 주장하려면 해당 출력·실험을 별도로 확인해야 한다.

## 7. 구현 위치·유지보수·최소 확인

아래는 신규 코드의 책임 경계이며 고정 파일 수나 범용 adapter 계층을 요구하지 않는다.

| 접점 | 현재 재사용 자산 | 새 코드의 책임 |
|---|---|---|
| `app/knowledge`의 문서 처리 | csv/HTML 처리, pdfplumber, python-hwpx | ParsedBlock/Evidence 변환, 파싱 실행과 원문 버전 분리 |
| 스키마·추출 | LinkML·LangExtract·[Ollama 저수준 호출](../../../app/generation/service.py)·Pydantic | 이식한 템플릿/프롬프트, 근거 봉투·ID 연결, 후보 상태. 민원 정규화·빈 실패 결과를 성공으로 전용하지 않음 |
| 원장·변경 | sqlite3·DeepDiff·difflib, [기존 SQLite 저장 패턴](../../../app/complaint_intelligence/sqlite_repository.py) | 지식 전용 트랜잭션·근거 참조·검토·스냅샷·최신 사용 상태. 민원 repository 클래스 상속/복제는 불필요 |
| 검색·종합 | [기존 RRF 단계](../../../app/retrieval/pipeline/stages/rrf_fusion.py), BM25/Chroma 구성요소, 생성 호출 | 지식 ID 어댑터·자료 필터·Local 관계 조회·Global 종합·원문 인용 |
| API·화면 | 기존 FastAPI 응답 봉투, Next.js 화면/요청 구성 | 별도 knowledge router와 `/knowledge`, P1 assist. 회사 문서에 가짜 case_id를 만들지 않음 |

검색 평가 파이프라인의 [BM25RetrieveStage](../../../app/retrieval/pipeline/stages/bm25_retriever.py)는 bm25s와 선택적 kiwipiepy 토큰화를 사용한다. 지식 전용 collection/index 경로를 지정하는 어댑터로 활용하고, 운영 RetrievalService와 같은 계약이라고 가정하지 않는다. `rank-bm25`는 조사 시 프로젝트 환경에 없었으며 추가할 필요가 없다. `GenerationService.call_ollama`는 스키마·모델·출력 예산·think를 받는 저수준 호출로 재사용할 수 있으나 호출 시간/횟수는 지식 Run에서도 기록한다.

외부 코드를 직접 이식할 때 원 저장소·고정 commit·원 파일·라이선스·수정 요지를 한 재사용 기록에 남기고 저작권/NOTICE를 보존한다. 패키지 설치는 버전을 고정해 호출하고 라이브러리 내부 수정은 피한다. 좁은 수정으로 해결되지 않으면 이식 범위와 재구현 사유를 해당 접점에 기록한다. 모든 후보를 위한 포크·플러그인 등록기·자동 설치기를 만들지 않는다.

확인은 기존 마일스톤 안에서 실시한다. K2는 실제 PDF 표와 HWPX 문단/표의 위치 대응, K3~4는 승인 스키마→추출→정렬→ID 연결, K6~7은 Local/Global 각 3건, K8은 실제 정정·관련 근거 제외를 확인한다. 원문에 없는 주장을 통과시키거나 필요한 조건/예외를 잃으면 해당 어댑터·프롬프트만 수정하고 관련 사례를 다시 확인한다. 이 문서 수정 자체는 패키지 설치·성능 실험·앱 구현을 수행한 결과가 아니다.

## 8. 버전 조정 계획과 확인 범위

2026-09-26 프로젝트 `.venv`의 배포 메타데이터를 직접 조회했다. Python 3.11.9, NumPy 1.26.4, pandas 2.2.3, Pydantic 2.11.7, pydantic-settings 2.10.1, Pillow 11.3.0, Streamlit 1.44.1, Chroma 1.5.5, NetworkX 3.6.1, Ollama SDK 0.6.1이다. 이는 설치 버전 확인이며 해당 기능의 실행 확인이 아니다. 신규 파서·LinkML·LangExtract는 이번 확인 시 미설치다.

| 우선 도입 배포본 후보 | 확인한 선언·조정 사항 | 구현 시 결정 |
|---|---|---|
| pdfplumber 0.11.10 | Python>=3.8, Pillow>=12.2.0, pdfminer.six==20260107, pypdfium2>=5.9.0. 현재 Streamlit 1.44.1은 Pillow<12 요구 | Pillow만 올리지 않고 Streamlit 등 관련 제약까지 맞추고 기존 UI의 영향 경로 확인. 이전 0.11.9만 고집하지 않음 |
| python-hwpx 6.5.0 | Python>=3.10, lxml>=4.9,<7 | 읽기 core를 사용하고 저작·MCP·자동화 companion은 추가하지 않음 |
| LinkML / linkml-runtime 1.11.1 | 배포본 LinkML은 Pydantic>=2,<3, runtime은 >=1.10.2,<3. 기존 조사 main의 Pydantic>=2.13.5와 다름 | **배포본과 main 제약을 구분**. 현재 pin을 바꿀 필요가 있는지는 전체 의존성 해석 후 결정 |
| LangExtract 1.7.0 | Python>=3.10, 정렬 이외 기능과 cloud SDK도 기본 의존성에 포함 | 정렬 API만 사용하고 원격 provider는 호출하지 않음. 선택 배포본의 Resolver 계약을 확인 |
| DeepDiff 9.1.0 | Python>=3.10, core는 cachebox/orderly-set 사용 | core만 추가. dev/test extra의 NumPy/pandas 고정값을 운영 필수 제약으로 오해하지 않음 |

배포본 근거: [pdfplumber](https://pypi.org/pypi/pdfplumber/0.11.10/json), [python-hwpx](https://pypi.org/pypi/python-hwpx/6.5.0/json), [LinkML](https://pypi.org/pypi/linkml/1.11.1/json), [runtime](https://pypi.org/pypi/linkml-runtime/1.11.1/json), [LangExtract](https://pypi.org/pypi/langextract/1.7.0/json), [DeepDiff](https://pypi.org/pypi/deepdiff/9.1.0/json). 위 표는 후보 버전이며 의존성 해석을 완료한 lock 파일이 아니다.

구현 시 기존 동작을 보존하면서 필요한 직접·전이 의존성을 함께 조정한다. 공통 requirements에 조정한 버전을 기록하고 Mac/Windows 전용 차이만 environment marker로 표현한다. 모든 패키지를 최신판으로 일괄 올리거나 충돌을 `--no-deps`로 숨기지 않는다. 기본 운영은 하나의 프로젝트 환경으로 유지하며 임시 의존성 해석 환경을 별도 운영 서비스로 남기지 않는다.

라이브러리 버전 정합성 확인과 영향 받은 기존 경로의 소규모 smoke를 K2~K4에 포함한다. 실제 호환성 문제가 확인되면 해당 조정만 추가 1~2일 작업으로 나누고 마일스톤 추정치를 갱신한다. 현 단계에서 resolver·설치·Mac/Windows 실행·한국어 품질은 아직 확인하지 않았으므로 위 조합을 호환성 검증 완료로 표시하지 않는다.


## 9. 개발 속도를 지키는 적용 범위

- 패키지는 K2 파서, K3 LinkML/온톨로지 자산, K4 정렬, K8 diff 순서로 필요한 때 설치한다. 모든 라이브러리 호환성 검증을 K2 시작 조건으로 두지 않는다. 관련 버전 충돌만 해결한다.
- AI 반례 검토는 온톨로지 생성·변경 묶음 1회, 필요 시 후보 수정 최대 1회다. 사실마다 재평가·자동 재작성·전문가 합의 호출을 추가하지 않는다.
- 스키마 검사는 API/추출 경계, 참조 검사는 DB/활성화 경계, 사용 상태는 검색 시작/변경 시에 배치한다. 같은 검사를 FE·서비스·어댑터마다 복제하지 않는다.
- 원문 위치 어댑터는 실제 선정 형식부터 구현하고 원문을 정규화하지 않는 경로를 우선한다. 정규화 대응표는 실제 정규화할 때만 추가한다.
- 대표 사례 결과는 누적한다. 실패·변경이 없는 전체 테스트 반복, OS 조합 전수검사, 매 단계 36회 비교는 하지 않는다. [측정 계약](evaluation_protocol.md)과 [계획 점검](../../70_research/company_knowledge/planning_scope_review_2026-09-26.md)을 따른다.

## K2 실제 도입 결과 (2026-09-26)

pdfplumber 0.11.10·python-hwpx 6.5.0·BeautifulSoup4 4.15.0을 직접 사용했다. Pillow 12.3.0·Streamlit 1.64.0으로 제약을 함께 맞췄다. Mac 설치·pip check·Streamlit Home 초기 렌더·실제 선정 자료 파싱을 확인했다. 위 §8 후보 표는 계획 당시 조사이며 K3 실제 결과는 아래에 기록한다. K4 이후 후보와 Windows 검증은 미완료다. 패키지 내부 수정·전체 엔진 도입은 없다.

## K3 구현 반영 (2026-09-27)

LinkML/runtime 1.11.1 직접 사용, OntoGPT 작성 구조·검사 방법 및 AutoSchemaKG 개념화 지침의 최소 적용. [재사용 기록](../../third_party/knowledge_k3_reuse.md), [K3 실행·제약](../../30_manuals/knowledge_k3_runbook.md). 코드 생성/import·OAK·외부 그래프 서버는 도입하지 않았다. 분석/설계와 Qwen 반례 검토를 기존 직렬 Run으로 실행하며 수정은 최대 1회다. 전체 FR-03·06 완료나 현업 효용 입증과 구분한다.
