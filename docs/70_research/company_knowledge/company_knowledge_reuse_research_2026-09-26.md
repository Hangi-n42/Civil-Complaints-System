# 회사 지식 PRD 구현을 위한 오픈소스·방법론 재사용 조사

> **후속 채택 결정:** 이 문서는 최초 조사 기록이다. 이후 사용자가 기존 의존성의 버전 조정을 허용했으며, [PRD v1.2 §10.4~10.9·§11.1](../../00_overview/company_knowledge_prd.md)에 직접 사용·부분 이식·재구현 방침을 구체화했다. 아래의 ‘기존 pin 유지’, ‘PDF 파서 하나만 추가’, ‘LinkML/LangExtract 유보’, ‘검색은 P1 후보’ 권고는 현재 구현 방침이 아니다. 하위 조사 3개도 조사 당시의 판단으로 읽는다. 기능/제약 조사 근거는 유지하되 구현 결정은 최신 PRD를 따른다. 이번 재확인에서 LinkML 1.11.1 배포본의 Pydantic 제약은 기존에 조사한 main과 다름을 확인했다. 설치·성능 확인을 완료했다는 뜻은 아니다.

- 확인일: 2026-09-26
- 대상: [회사 지식 온톨로지·지식그래프 PRD](../../00_overview/company_knowledge_prd.md)
- 조사 방식: 담당 AI 에이전트 3개와 주 에이전트가 분야를 분담하여 공식 문서·저장소·핵심 코드·패키지 메타데이터를 확인했다.
- 제약: Python 3.11.9, Mac/Windows 네이티브, 로컬 Ollama, 기존 의존성·민원 API 보존.
- 확인 수준: 기능·구현 경로·선언된 의존성에 대한 조사다. 설치·의존성 resolver 실행·LH 자료 추출 정확도·실행 속도·양 OS 동작은 검증하지 않았다.
- 상태: 도입 제안. 이 조사로 PRD나 앱 코드를 변경하거나 패키지를 설치하지 않았다.

## 1. 결론

**기존 Pydantic·Ollama·SQLite를 중심으로 구현하고, 외부 프로젝트에서는 추출/ID 검증, 개념 초안 생성, 출처/시간 모델, 검토 방식을 선택적으로 재사용하는 것이 현재 PRD에 맞는다.** 직접 추가할 가능성이 가장 높은 의존성은 문서 파서다. OntoGPT나 GraphRAG 제품 전체를 넣는 것을 출발점으로 삼지 않는다.

이 결론은 기존 계획을 고수하기 위해 내린 것이 아니다. 실제 확인된 기능 중 재사용 가치가 높은 것과, 프로젝트의 고정 의존성·업무 검토 계약에 맞지 않는 것을 분리한 결과다. 직접 재사용하지 않는 도구도 후속 비교 후보로 남긴다.

| 판정 | 의미 |
|---|---|
| 기존 재사용 | 현재 저장소의 패키지·호출 경계를 활용 |
| 직접 도입 후보 | 기존 코드보다 적은 구현으로 요구를 해결할 가능성이 있어, 제한된 실자료 확인 후 추가 |
| 설계 차용 | 알고리즘·데이터 모델·작업 흐름을 참고하되 전체 패키지는 추가하지 않음 |
| 조건부/후속 | 특정 품질 부족·규모·외부 계약이 확인될 때 별도 환경에서 비교 |

초기 온톨로지를 만드는 일과, 이미 정의된 온톨로지에 맞춰 데이터를 추출하는 일은 다르다. 두 단계를 분리해야 라이브러리를 잘못 선택하지 않는다.

## 2. 현재 코드에서 먼저 재사용할 부분

| 현재 자산 | 사용할 부분 | 그대로 가져오면 안 되는 부분 |
|---|---|---|
| [requirements.txt](../../../requirements.txt) | Pydantic, jsonschema, PyYAML, httpx, NetworkX, SQLAlchemy 등이 선언되어 있음 | 선언되어 있다는 것이 현재 환경에서 모두 설치·실행 확인됐다는 뜻은 아님 |
| [generation/service.py](../../../app/generation/service.py) | Ollama 요청의 `format=response_schema`, 모델·예산·think 설정 전달 패턴 | 민원 응답 정규화·프롬프트·case_id 계약을 회사 지식 추출기에 이식하지 않음 |
| [structuring/llm_extractor.py](../../../app/structuring/llm_extractor.py) | JSON 파싱과 Pydantic 검증, 제한된 오류 재시도 구조 | 민원 4요소 전용 스키마, 입력 길이 절단, 실패 시 빈 출력 정책은 지식 구축용 성공 판정으로 전용하지 않음 |
| [structuring/legal_dictionary.py](../../../app/structuring/legal_dictionary.py) | 로컬 사전에서 표기와 정식 식별자를 연결하는 패턴 | 부분문자열 매칭·임의 confidence를 동일 대상 확정 또는 일반 온톨로지 정답 검증으로 쓰지 않음 |
| [structuring/verifier.py](../../../app/structuring/verifier.py) | 후보와 원문을 대조하고 검토 결과를 남기는 구조 | 원문 span이 있으면 검증을 생략하는 경로, 미보정 confidence는 의미·범위·시점의 정확도를 보장하지 않음 |
| 기존 Chroma/BM25·FE | P1 검색 실험과 신규 지식 화면 구현 기반 | 기존 민원 collection 및 API 응답 타입에 회사 문서를 무조건 혼합하지 않음 |

[Ollama 공식 structured outputs](https://docs.ollama.com/capabilities/structured-outputs)는 JSON Schema 입력을 지원한다. 따라서 JSON 형식을 맞추는 목적만으로 Instructor나 또 다른 LLM 프레임워크를 추가할 필요는 없다. JSON 형식 준수와 원문 의미의 정확성은 별도 확인 대상이다.

## 3. OntoGPT와 추출 도구

상세 조사: [추출·grounding·스키마 비교](company_knowledge_reuse_extraction_research_2026-09-26.md).

| OntoGPT에서 확인한 기능 | 가져올 부분 | 우리 제품에 맞출 부분 |
|---|---|---|
| `ontogpt-author-template` skill·skeleton·validator | 필드 정의, 자료형, 예시, ID prefix와 annotator 일관성 점검 | 회사 자료의 정의·반례·업무 질문·근거를 가진 후보 생성 절차. validator 실행은 OntoGPT 환경을 요구하므로 스크립트만 독립 실행 가능하다고 가정하지 않음 |
| LinkML/SPIRES 템플릿 기반 추출 | 스키마와 추출 지침을 명시하고 단계적으로 처리 | P0는 얕은 출력 구조와 원문 절/표 단위 호출. 재귀 호출 전체를 그대로 도입하지 않음 |
| 이름 추출→grounding 분리 | LLM의 표기 추출과 코드의 ID 연결을 분리 | LH 공식 ID·검토 별칭을 로컬 등록부에서 찾음. LLM이 지어낸 ID나 첫 검색 결과를 정답으로 확정하지 않음 |
| TermValidator | 존재·폐기·label/alias 상태와 검증 불가 상태 구분 | 검증 생략/예외는 통과가 아님. 의미·조건·적용 시점은 별도 검토 |

**보완된 이해:** 초기 템플릿 작성을 돕는 공식 [agent skill](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/skills/ontogpt-author-template/SKILL.md)은 실제 존재한다. ‘OntoGPT에는 초안 설계 지원이 없다’고 단정하면 안 된다. 다만 이 작성 절차와 회사 자료 전체에서 업무 온톨로지를 자동 완성하는 엔진은 다르다.

[TermValidator 코드](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/validation/term_validator.py)는 점검 생략·label 차이 등의 상태를 가진다. README의 표현만 읽고 모든 반환 ID가 의미적으로 검증됐다고 보지 않는다. [knowledge engine](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/engines/knowledge_engine.py)의 개체 정규화 경로는 `original_spans=None`을 설정하므로, OntoGPT 도입만으로 PRD의 원문 위치 계약까지 충족되는 것도 아니다.

**전체 설치 보류 근거:** 확인한 OntoGPT main은 `numpy>=2.0.0`으로 프로젝트의 `numpy==1.26.4`와 충돌한다. LinkML main은 Pydantic 하한이 기존 pin보다 높다. 과거 버전 전부가 설치 불가하다는 뜻은 아니며, 버전을 낮춰 도입하는 대안도 전체 의존성과 필요한 기능을 다시 확인해야 한다. [OntoGPT 메타데이터](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/pyproject.toml)

| 대안 | 가치 | 도입 판단 |
|---|---|---|
| LinkML/OAK | 스키마 생성·다양한 온톨로지 접근 | 외부 온톨로지/교환 형식이 확정되면 별도 작성·변환 도구로 검토. 임의 회사 SQLite가 OAK에 곧바로 연결되는 것은 아님 |
| LangExtract | 문자 위치·alignment 상태를 가진 추출 | 위치 복원 문제가 남을 때 별도 비교. fuzzy 정렬과 정확한 원문 일치 구분. Ollama provider는 현재 `output_schema` 미지원이며 네이티브 Ollama와 기능 차이 존재 |
| Instructor | Pydantic 응답 모델과 재시도 | 현재 코드와 중복. 조사한 main의 일부 의존성 하한도 기존 pin과 충돌하므로 기본 도입 보류 |

LangExtract는 [로컬 Ollama 연동](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/README.md#using-local-models-with-ollama)과 코드의 `think=False` 전달이 확인됐다. 한글 tokenizer 처리도 있지만 LH 문서에서의 추출 정확도는 미확인이다. 원문 위치를 찾는 기능, PDF/HWPX의 원래 위치를 복원하는 기능, 문장이 주장을 뒷받침하는지 판단하는 기능은 각각 따로 필요하다.

## 4. 초기 온톨로지 생성에 추가로 참고할 방법

### 4.1 Ontology Development 101·LOT: 먼저 답해야 할 질문을 고정

[Stanford Ontology Development 101](https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html)은 사용 목적과 답할 질문으로 범위를 정하고 반복적으로 모델을 다듬는 접근을 설명한다. [LOT](https://lot.linkeddata.es/)은 요구 정의·구현·배포·유지보수를 구분하며 도메인 전문가와의 요구 확인을 포함한다. 단일한 정답 온톨로지나 자동 검증 보증으로 해석하지 않는다.

**적용 제안:** PRD의 12개 평가 작업에 ‘이 지식으로 답해야 할 질문(CQ)’을 연결한다. 각 질문에는 필요한 개념·관계·출처·조건을 기록한다. AI가 개념을 제안할 때 어느 질문에 필요한지 설명하게 한다. 근거도 업무 질문도 연결되지 않는 개념은 후순위로 둔다.

사용할 질문 유형은 PRD에서 이미 정한 대상 단지, 조건별 제출서류, 정정의 영향, 근거의 적용 시점이다. 조사되지 않은 업무 질문을 실제 현업 요구라고 표시하지 않는다. LOT 전체의 OWL·공개 URI 배포 절차까지 도입할 필요는 없다. LOT 사이트의 그림·템플릿을 복제하는 것은 방법론을 참고하는 것과 별도이며 해당 자료의 이용 조건을 확인한다.

문헌: Poveda-Villalón et al. (2022), *LOT: An industrial oriented ontology engineering framework*, [DOI](https://doi.org/10.1016/j.engappai.2022.104755). LOT4KG 후속 페이지도 발견했지만 본문 취득이 실패하여 구체적인 도입 근거로 사용하지 않았다.

### 4.2 AutoSchemaKG: 자료에서 개념 후보를 만드는 방향

[AutoSchemaKG 공식 저장소](https://github.com/HKUST-KnowComp/AutoSchemaKG)는 텍스트의 개체·사건·관계 추출 후 conceptualization으로 스키마를 유도하는 구현을 제공한다. [논문](https://arxiv.org/abs/2505.23628)의 벤치마크 성과를 LH 자료의 품질로 일반화하지 않는다.

확인한 코드:

- [concept_generation.py](https://github.com/HKUST-KnowComp/AutoSchemaKG/blob/main/atlas_rag/kg_construction/concept_generation.py): 개체·사건·관계 표현을 나누어 개념 생성 입력을 구성.
- [concept_to_csv.py](https://github.com/HKUST-KnowComp/AutoSchemaKG/blob/main/atlas_rag/kg_construction/concept_to_csv.py): 추출 대상과 개념 노드를 연결. 개념명 기반 해시 ID 생성 경로 존재.
- [llm_generator.py](https://github.com/HKUST-KnowComp/AutoSchemaKG/blob/main/atlas_rag/llm_generator/llm_generator.py): OpenAI 호환 API와 직접 모델 추론 경로. Ollama에 대한 실제 호출 검증은 하지 않음.
- [pyproject.toml](https://github.com/HKUST-KnowComp/AutoSchemaKG/blob/main/pyproject.toml): 조사 시 main 버전 `0.0.5.post1`, Python >=3.9, MIT. Neo4j 드라이버·graphdatascience·transformers·datasets·accelerate 등의 의존성 포함. nvembed extra는 sentence-transformers==2.7.0을 요구하여 현 선언 3.4.1과 다름.

**판정: 설계 차용.** ‘문서 표현→추출된 개체/사건/관계→업무 개념 후보’의 분리를 사용한다. 개념 노드가 생성됐다고 해서 정의·domain/range·조건·검토 상태가 완성된 온톨로지라고 간주하지 않는다. 개념명 해시를 회사 전체의 의미적 동일성 기준으로 사용하지 않는다. 전체 런타임을 도입하지 않고 현재 모델에서 초안 단계만 구현하는 안이 우선이다.

### 4.3 CQ4OE·LLMs4OL: 생성 단계를 나누고 평가 단위도 분리

[CQ4OE 공식 저장소](https://github.com/oeg-upm/cq4oe-benchmark)는 질문에서 필요한 클래스·속성을 찾는 CQ2Term과 전체 온톨로지 생성 CQ2Onto를 구분하고, 질문과 용어·공리의 연결을 평가 자료에 남긴다. [LLMs4OL](https://github.com/HamedBabaei/LLMs4OL)은 온톨로지 학습을 다루는 연구 구현이다. 둘을 완성된 회사 지식 관리 서비스로 취급하지 않는다.

**적용 제안:** 먼저 용어·관계 후보의 누락/불필요함을 검토한 뒤, 개념 계층·관계 제약을 검토한다. 한 번에 완성 온톨로지를 생성하고 전체가 맞는지 LLM에게 점수만 받는 방식은 피한다. 기존 PRD 평가에 질문→필요 개념/관계→실제 근거의 대응표를 추가하는 것으로 충분하다. 외부 벤치마크 자료를 LH 정답으로 사용하지 않고, 코드/데이터의 재배포 조건을 확인하기 전 복제하지 않는다.

## 5. 원문 추출·변경 비교

상세 조사: [문서 처리·변경 비교 후보](company_knowledge_reuse_documents_research_2026-09-26.md).

**직접 도입 1순위 후보는 `pdfplumber==0.11.9` 하나다.** LH 자료의 표·셀·페이지 좌표 요구에 맞는 API를 제공한다. 본문 추출만 필요한 범위라면 pypdf가 더 작은 대안이다. 두 패키지를 동시에 추가하는 것으로 시작하지 않는다. [pdfplumber 공식 API](https://github.com/jsvine/pdfplumber/blob/stable/README.md), [pypdf 추출 문서](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)

| 후보 | 가져올 기능 | 현재 판단 |
|---|---|---|
| `pdfplumber` | 문자/표/셀 좌표와 원문 대조 | 최신 0.11.10은 Pillow>=12.2.0으로 기존 11.3.0과 충돌. 0.11.9는 해당 제약을 충족하는 비교 후보이며 전체 호환성은 미검증 |
| `pypdf` | 페이지별 텍스트·문서 메타데이터 | 표의 구조까지 필요하지 않을 때 대안. OCR/표 의미 이해 제공으로 해석하지 않음 |
| `Docling` | 문서 계층·읽기 순서·표 구조·provenance | 가벼운 파서가 필수 복잡 표에서 실패할 때 조건부 비교. 코드와 모델 라이선스·다운로드 별도 |
| `PyMuPDF/4LLM` | 페이지·단어·표/셀 bbox, 구조화 추출 | AGPL/상용 선택을 고려해야 함. HWP/HWPX는 Pro 확장이므로 무료 기본 기능으로 계산하지 않음 |
| `Unstructured` | 다양한 문서의 요소별 partition·표 HTML | 최신 PDF 추론 경로의 torch/onnxruntime 제약과 기존 값 충돌. 현 P0 기본 후보에서 제외 |
| HWPX `zipfile/ElementTree` | 구역·문단·표·셀 구조 위치 | 추가 의존성 없이 최소 어댑터 작성. 렌더링 페이지 재현 기능과 구분 |
| `python-hwpx` | 커뮤니티 HWPX 구조 처리 | 중첩표·각주 때문에 최소 어댑터가 복잡해질 때 비교. 한컴 공식 SDK로 소개하지 않음 |
| `difflib` / `DeepDiff` | 텍스트 구간 / 중첩 데이터의 변경 경로 | P0는 공식 ID별 dict 비교+difflib. 중첩 비교가 반복될 때만 DeepDiff 추가 |

위 버전 제약의 직접 근거: [pdfplumber 0.11.10 배포 메타](https://pypi.org/pypi/pdfplumber/0.11.10/json), [0.11.9](https://pypi.org/pypi/pdfplumber/0.11.9/json), [Unstructured inference 1.6.13](https://pypi.org/pypi/unstructured-inference/1.6.13/json). 모든 transitive dependency를 해결한 결과는 아니다.

**방법론에서 중요한 부분:** 파일 해시 변경, 문서 텍스트 변경, 사실 변경, 공식 정정, 파생 지식 영향은 각각 다른 사건이다. 파일 해시·문자열 diff만으로 뒤의 세 가지를 확정하지 않는다. 파서 버전/옵션과 원문 버전을 별도로 보존해야 파서 교체에 따른 차이도 구분할 수 있다.

HWPX는 [한컴 형식 설명](https://tech.hancom.com/hwpxformat/)에 따라 패키지·XML 구조를 읽는다. 텍스트 전체를 합치는 것만으로 표의 행/셀 관계와 근거 위치를 보존했다고 보지 않는다. PDF의 물리 페이지와 인쇄 쪽수도 분리한다.

## 6. 그래프·출처·매핑·검증

상세 조사: [그래프·시간·검증 후보](company_knowledge_reuse_graph_research_2026-09-26.md).

### 6.1 표준에서 빌릴 데이터 모델

- **SKOS:** 개념의 대표 표기·별칭, 상하위·관련 개념을 구분하는 어휘. 단지 같은 실제 개체의 동일성 판단과 개념 간 매핑을 혼동하지 않는다. [공식 Reference](https://www.w3.org/TR/skos-reference/)
- **PROV-O:** 무엇이 어떤 자료로부터 어떤 작업을 거쳐 만들어졌는지 연결하는 출처 모델. 사실이 참이라는 인증 모델은 아니다. [공식 Recommendation](https://www.w3.org/TR/prov-o/)
- **SSSOM:** 개념 매핑의 주체·관계·대상뿐 아니라 매핑 방법·작성자·시점 등을 기록하는 방식. 이름 유사도를 exactMatch로 자동 승격하지 않는다. [공식 저장소](https://github.com/mapping-commons/sssom)
- **N-ary relation 패턴:** 관계 자체에 대상·조건·시점 같은 추가 정보를 붙이는 모델링 참고. PRD의 Assertion 객체에 대응한다. [W3C Working Group Note](https://www.w3.org/TR/swbp-n-aryRelations/)

위 패턴은 SQLite/JSON에 필요한 필드로 반영할 수 있다. RDF 변환·표준 적합성 검증을 하지 않았다면 ‘SKOS/PROV/SSSOM 준수 구현’이라고 표현하지 않는다. 특히 W3C Note를 Recommendation과 같은 표준 지위로 소개하지 않는다.

### 6.2 무엇을 검사하는지 구분

1. **형식:** JSON 필드·자료형·필수값 — 기존 Pydantic/JSON Schema.
2. **참조:** 공식 ID 존재·네임스페이스·근거 위치 — 로컬 등록부/DB 제약·원문 대조.
3. **관계 제약:** 허용 개념 조합·개수·자료형 — 우선 기존 검증 코드, RDF 교환이 필요하면 SHACL/pySHACL 검토.
4. **업무 의미:** 이 문장이 이 대상·범위·시점의 주장을 뒷받침하는지 — 자료와 업무 기준에 따른 검토.

앞의 세 단계가 통과해도 네 번째가 자동으로 통과하지 않는다. OWL의 domain/range 추론과 입력 검증도 동일하지 않다. 새로 추가할 검사는 PRD의 오류 사례와 직접 연결된 것만 둔다.

### 6.3 그래프 프레임워크별 차용 지점

| 후보 | 가져올 부분 | 채택 범위·제약 |
|---|---|---|
| [Graphiti](https://github.com/getzep/graphiti) | 출처 문서/에피소드와 관계 연결, 사실 적용 시각과 기록 시각 분리 | 원리 차용. 현재형 사실의 valid_at을 reference time으로 채우는 프롬프트 규칙은 법적 시행일 추출에 사용하지 않음. 그래프 백엔드와 모델 설정이 추가로 필요 |
| [LightRAG](https://github.com/HKUDS/LightRAG) | 개체/관계 검색과 텍스트 근거 검색의 결합 | P1 별도 비교 후보. 기본 로컬 저장이 가능하므로 서버 DB가 필수라고 설명하지 않음. 병합된 설명과 제한될 수 있는 source 목록은 승인 원장 대체 불가 |
| [Microsoft GraphRAG](https://microsoft.github.io/graphrag/index/default_dataflow/) | 원문 text unit 연결, 추출/요약 구분, 전역 주제별 요약 | 전역 요약이 필요할 때 후속 비교. 특정 공고의 변경 검토와 목적이 다름. 조사한 3.2.0 main이 기존 NumPy/pandas/PyArrow/Pydantic과 충돌 |
| [RDFLib](https://rdflib.readthedocs.io/en/stable/)·[pySHACL](https://github.com/RDFLib/pySHACL) | RDF 읽기/쓰기/질의, shapes 기반 검증 | 외부 RDF/SHACL 계약이 필요할 때 조건부 직접 도입. 메모리 그래프 검사는 서버·LLM 불필요지만 추가 Python 의존성은 존재 |
| SQLite·기존 NetworkX | 제한된 관계 조회·경로 탐색 | P0 기본. SQLite 원장을 유지하고 NetworkX는 필요할 때 파생 그래프로 사용 |

Graphiti의 [시간 추출 프롬프트](https://github.com/getzep/graphiti/blob/ba4a9cb32495b6864160616f8dfa2b898f4a500c/graphiti_core/prompts/extract_edges.py)를 보면 시간 값이 원문에서 직접 확인된 값인지 모델 규칙으로 보충된 값인지 구분해야 한다. 우리 제품은 시행일 근거가 없으면 미확인으로 유지한다.

Microsoft GraphRAG의 [조회 커밋 의존성](https://github.com/microsoft/graphrag/blob/769542fbf1d8e5b4c6a8677fefc34621c87894c5/packages/graphrag/pyproject.toml)은 NumPy~=2.4, pandas~=3.0, PyArrow~=25.0, Pydantic~=2.13이다. 현재 프로젝트는 각각 1.26.4/2.2.3/23.0.1/2.11.7로 고정되어 있다. 이 비교는 직접 제약 충돌이며 실제 설치 실패를 재현한 것은 아니다.

PRD의 최대 2단계 관계 조회는 [SQLite recursive CTE](https://www.sqlite.org/lang_with.html) 또는 작은 관계 테이블 조회로 구현할 수 있다. NetworkX 최신판을 무조건 올리지 않는다. 현 3.6.1은 Python3.11.9를 허용하지만 조사 시 3.7의 Python 하한은 3.12다. [배포 메타데이터](https://pypi.org/pypi/networkx/3.7/json)

## 7. 검토 UI와 데이터 정리 도구

| 후보 | 확인한 기능·조건 | 적용 판정 |
|---|---|---|
| [OpenRefine](https://openrefine.org/docs/manual/reconciling) | 표 데이터 정리, reconciliation 후보와 사람의 확인. 문자열 clustering과 의미적 연결을 공식 문서에서 구분. Windows/Mac 배포, Java 기반, BSD-3-Clause | 일회성 CSV/별칭 정리에 외부 도구로 사용 가능. P0 앱 내부에는 후보 비교·수락 방식만 차용. LH 로컬 데이터와 직접 reconciliation하려면 서비스 연결이 필요하므로 원문 CSV가 있다는 이유만으로 즉시 의미 연결 가능하다고 보지 않음 |
| [Label Studio](https://labelstud.io/templates/relation_extraction) | 텍스트 개체·관계 라벨링 템플릿. Apache-2.0, main 개발 계열 메타 Python>=3.10,<4 | 평가용 관계/근거 라벨 작성의 후속 후보. 온톨로지 버전·지식 활성화·철회를 대신하는 제품은 아님 |
| [Argilla](https://docs.argilla.io/) | 모델 제안과 사람의 피드백을 모으는 데이터 검토 서비스. Apache-2.0; 공식 Docker 배포는 서버·검색엔진 등을 포함 | 이미 FE가 있는 단일 운영자 P0에는 도입 보류. 여러 평가자의 지속적 라벨링이 필요할 때 별도 검토 |
| Protégé | 수동 온톨로지 설계·검토 도구 및 Ontology 101 방법론을 탐색 | OWL 산출물의 외부 전문가 검토가 필요할 때 후보. 현재 P0 검토 화면을 통째로 대체하지 않음 |

OpenRefine의 [clustering 설명](https://openrefine.org/docs/technical-reference/clustering-in-depth)은 문자열 유사성만으로 의미적 동일성을 결정할 수 없음을 명시한다. 우리 시스템에서도 후보 생성과 최종 통합을 분리한다.

Label Studio 개발 브랜치의 [pyproject](https://github.com/HumanSignal/label-studio/blob/develop/pyproject.toml)는 `python-json-logger==2.0.4`를 요구하여 현재 프로젝트의 `4.0.0` 고정과 충돌한다. 도입하더라도 같은 venv에 설치하는 전제로 삼지 않는다. [Argilla 배포 문서](https://docs.argilla.io/v2.1/getting_started/how-to-deploy-argilla-with-docker/)는 서버·DB·검색엔진 운영을 설명한다. 이 부대 구성이 현재 P0의 필수 기능은 아니다.

코드 라이선스 출처: [OpenRefine](https://github.com/OpenRefine/OpenRefine/blob/master/LICENSE.txt), [Label Studio](https://github.com/HumanSignal/label-studio/blob/develop/LICENSE), [Argilla](https://github.com/argilla-io/argilla/blob/main/LICENSE). 각 저장소는 조사 시 GitHub API상 archived=false였으나, 활동 여부만으로 품질이나 유지보수를 보증하지 않는다.

## 8. 실제 구현 조합과 PRD 연결

| PRD 요구 | 권장 재사용 | 우리가 작성해야 하는 접점 |
|---|---|---|
| FR-01 자료/버전 | stdlib hash·파일 처리, SQLite | 자료군·공식 정정 계열·권리 상태와 source_version 연결 |
| FR-02 근거 추출 | PDF 파서 하나, HWPX ZIP/XML | 원문 페이지/표/셀·좌표계→Evidence 변환 |
| FR-03 온톨로지 초안 | LOT/CQ, AutoSchemaKG 개념 유도, OntoGPT 템플릿 작성 절차 | 질문·원문·기존 스키마에 연결된 개념 제안 및 검토 |
| FR-04 개체 연결 | OntoGPT grounding/검증 방식, OpenRefine 후보 검토, SKOS/SSSOM 구분 | LH 공식 ID 등록부·별칭·불확실 연결·통합 취소 |
| FR-05 사실/조건 | Pydantic/JSON Schema, PROV·N-ary 관계 패턴 | 조건·범위·유효일·근거에 대한 업무 제약 |
| FR-06 검수 | 기존 Next.js, OpenRefine/Label Studio의 대조·후보 UI 방식 | 개념·관계·사실의 묶음 수락/수정/보류/기각 |
| FR-07 변경 영향 | difflib·ID별 비교, Graphiti의 시간 구분 참고 | 공식 개정/정정 확인과 원문→주장→파생 지식 의존 추적 |
| FR-08 활성화/복원 | SQLite 트랜잭션·참조 제약 | 불변 스냅샷과 별도 사용 가능 상태 이력 |
| FR-09 조회/내보내기 | SQLite 관계 조회, 필요 시 기존 NetworkX·Chroma/BM25 | 사용 가능 상태·범위·기준일 필터, 근거 경로, JSON/CSV 출력 |
| FR-10 민원 활용 | 기존 생성 호출, LightRAG 등의 개체/관계 검색 아이디어 | 기존 case_id 계약과 구분한 knowledge assist 및 인용 확인 |

**코드 재사용의 우선순위:** 기존 패키지 기능 호출 → 필요한 문서 파서 추가 → 외부 코드의 좁은 부분 이식 또는 알고리즘 재구현 → 전체 플랫폼 도입 순서다. 좁은 부분을 직접 복사한다면 해당 커밋·라이선스·저작권 고지와 필요한 의존성도 함께 확인한다. 설계를 참고한 자체 구현과 코드 복제를 같은 의미로 쓰지 않는다.

PRD 보완 제안은 다음 네 개다. 아직 본 PRD에는 반영하지 않았다.

1. FR-03에 **질문→개념/관계→원문** 대응과 ‘초기 개념 유도 / 승인 스키마 기반 추출’의 분리를 명시한다.
2. FR-04에서 **원문 표기, 개념 ID, 실제 개체 ID, 매핑 방법/검토 상태**를 별개로 관리한다.
3. FR-02/07에 **파서 버전/옵션, 원문 위치 체계, 정규화 전후 대응**을 넣어 원문 변경과 파싱 차이를 구분한다.
4. 구현 의존성 후보를 **PDF 파서 하나**로 좁히고 RDF/그래프 플랫폼은 필요 조건이 충족될 때만 비교한다.

추가 시험은 설치 전에 필요한 호환성을 확인한 뒤, 기존 양산 공고의 날짜 정정·단지 표와 HWPX 구조를 동일하게 사용한다. 작은 파서가 필수 근거 위치를 복원하지 못할 때만 Docling을 같은 자료로 비교한다. 전체 오픈소스 도구를 한 번에 설치하거나 대규모 비교 플랫폼을 만들 필요는 없다.

## 9. 확인한 범위와 남은 확인

- 읽은 문서·코드의 기능 존재와 선언된 의존성 충돌은 확인했다. 패키지 전체 의존성 충돌이 모두 탐지됐다고 주장하지 않는다.
- PyPI 배포본과 GitHub main/develop의 선언은 다를 수 있다. 실제 도입 버전을 선택한 뒤 그 배포본의 메타데이터를 다시 확인해야 한다.
- 코드 라이선스와 모델 가중치·학습 데이터·예제 문서의 이용 조건은 별개다. 이번 조사는 설치·라이선스 법률 검토·재배포 승인이 아니다.
- 한국어를 입력할 수 있다는 것, 한국어 OCR 모델이 있다는 것, LH 표·조건을 정확히 추출한다는 것은 서로 다른 주장이다. 마지막 항목은 실자료로 확인하지 않았다.
- PRD의 SourceVersion/Evidence/Assertion/Decision/Snapshot을 한 번에 충족한다고 확인된 패키지는 이번 조사에서 찾지 못했다. 작은 도구를 사용하더라도 이 업무 계약과 연결하는 코드는 필요하다.

분담 결과는 세 상세 보고서에 남겼으며, 주 에이전트가 통합표를 실제 코드/의존성 선언과 대조했다. 문서 처리 담당은 통합 보고서의 파서 선택과 FR 매핑 부분을 다시 읽고 중요 불일치가 없음을 확인했다. 이는 AI 기반 조사 검토이며 독립적인 인간 전문가 승인이나 실제 호환성 시험은 아니다.
