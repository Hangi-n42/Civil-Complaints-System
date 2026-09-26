# 회사 지식 계층 재사용 조사: 그래프·검증·시간·출처

기준일: 2026-09-26. 대상: [회사 지식 PRD v1.0](../../00_overview/company_knowledge_prd.md)의 P0 구축·검수·갱신과 P1 근거 활용. 공식 문서·소스·릴리스·Python 패키지 메타데이터를 확인했다. 설치, 모델 호출, 성능 비교, Mac/Windows 실행 검증은 수행하지 않았다. 아래 ‘권고’는 문서·코드 조사에 근거한 설계 판단이다.

## 1. 결론

**P0는 SQLite 원장과 기존 Pydantic·NetworkX를 유지하고, SKOS·PROV-O의 개념 구분을 데이터 계약에 차용하는 것이 적절하다.** RDF 교환이나 독립 SHACL 검사가 실제 요구가 되면 RDFLib·pySHACL을 작은 추가 구성으로 검토한다. Graphiti·LightRAG·Microsoft GraphRAG 전체를 지식 원장으로 채택할 근거는 현재 없다.

세 프레임워크는 그래프 추출·검색·요약에 유용한 구현을 제공한다. 그러나 이번 핵심인 **원문별 적용 범위·효력 시점·검토 상태·불변 스냅샷·최신 사용 중단 상태**를 그대로 충족하는지 확인되지 않았다. 자동으로 합쳐진 관계나 요약을 승인된 사실로 취급해서는 안 된다. 이 판단은 프레임워크의 일반적 성능이 낮다는 뜻이 아니다.

직접 비교 후보를 하나만 남기면 **LightRAG를 P1 그래프 검색의 별도 실험 후보**로 둔다. 기본 로컬 저장 구성이 있어 시작 조건이 비교적 작다. P0 변경 검토의 효과가 확인되기 전에 검색 플랫폼부터 도입하지 않는다.

## 2. 핵심 후보 비교

Python 범위는 아래 명시한 배포판 또는 조회한 소스의 선언이다. 범위에 들어간다는 사실만으로 모든 전이 의존성과 OS 실행이 검증된 것은 아니다.

| 후보 | 확인 버전·라이선스·Python | 저장·서버·모델 조건 | 현재 권고 |
|---|---|---|---|
| Graphiti | 0.30.2 · Apache-2.0 · `>=3.10,<4` | 그래프 백엔드 필요. Neo4j/FalkorDB 등. 기본 OpenAI, Ollama 구성 가능 | 시간·출처 분리 원리 차용. P0 원장 채택 보류 |
| HKUDS LightRAG | 1.5.7 · MIT · `>=3.10` | 기본 JSON KV·벡터·NetworkX·문서상태 로컬 저장. LLM와 embedding 필요, Ollama 지원 | 검색 비교 후보. 승인 원장과 분리 |
| Microsoft GraphRAG | 3.2.0 · MIT · `>=3.11,<3.14` | 로컬 파일·LanceDB 가능. 추출/요약 LLM와 embedding, 구조화 출력 필요 | 기존 의존성과 직접 충돌. 현재 환경 도입 보류 |
| RDFLib + pySHACL | 7.6.0 BSD-3-Clause + 0.40.1 Apache-2.0 · 각각 `>=3.8.1`, `>=3.9` | RDF 메모리 그래프 검사에 외부 서버·모델 불필요 | RDF 교환/SHACL 요구가 생길 때 조건부 직접 도입 |
| W3C SKOS·PROV-O·SHACL | 표준 문서. Python 패키지 아님 | 개념 차용에 서버·모델·추가 패키지 불필요 | 용어·출처·구조 검증의 의미를 지금 차용 |
| SQLite + 기존 NetworkX | Python 표준 `sqlite3` + NetworkX 3.6.1 BSD-3-Clause · 3.6.1은 `>=3.11,!=3.14.1` | 로컬 파일 원장과 메모리 그래프. 모델 불필요 | P0 기본 유지. 그래프 알고리즘이 필요할 때만 NetworkX 사용 |

배포판 Python 근거: [Graphiti](https://pypi.org/pypi/graphiti-core/0.30.2/json), [LightRAG](https://pypi.org/pypi/lightrag-hku/1.5.7/json), [GraphRAG](https://pypi.org/pypi/graphrag/3.2.0/json), [RDFLib](https://pypi.org/pypi/rdflib/7.6.0/json), [pySHACL](https://pypi.org/pypi/pyshacl/0.40.1/json), [NetworkX 3.6.1](https://pypi.org/pypi/networkx/3.6.1/json).

## 3. Graphiti: 시간 그래프는 유용하지만 자동 추론한 시간을 시행일로 쓰면 안 됨

공식 구현은 에피소드에서 관계를 추출하고 관계의 `valid_at`, `invalid_at` 등을 관리한다. 다만 조회한 추출 프롬프트는 현재형의 진행 중 사실에 대해 에피소드 시각 또는 `REFERENCE_TIME`을 `valid_at`으로 지정한다. 날짜만 주어지면 자정으로 해석하는 규칙도 있다. 이는 모델에게 주어진 자동 해석 규칙이지 원문에 그 효력 발생 시점이 명시됐다는 증거가 아니다. [시간 추출 프롬프트](https://github.com/getzep/graphiti/blob/ba4a9cb32495b6864160616f8dfa2b898f4a500c/graphiti_core/prompts/extract_edges.py)

LH 자료에서는 수집일·공고일·규정 시행일·신청 기간·사실 적용 기간이 다르다. 따라서 Graphiti 시간을 그대로 법적 유효시점으로 매핑하지 않는다. 출처가 명시한 날짜와 AI가 제안한 날짜를 구분하고, 미확인 효력일은 미확인 상태로 보존해야 한다. PRD의 검토·스냅샷·사용 가능 상태는 별도 계약으로 유지한다.

현재 README는 Neo4j 5.26+, FalkorDB 1.1.2+, Neptune 구성을 제시하고 Kuzu 경로는 deprecated로 표시한다. 소스의 임베디드 `falkordblite` extra는 Python 3.12 이상 조건이어서 3.11.9를 유지하는 대안으로 바로 선택할 수 없다. Ollama는 OpenAI 호환 주소로 연결할 수 있으나 추출 LLM뿐 아니라 embedding·reranker 설정도 함께 확인해야 한다. [README](https://github.com/getzep/graphiti), [의존성 선언](https://github.com/getzep/graphiti/blob/ba4a9cb32495b6864160616f8dfa2b898f4a500c/pyproject.toml)

**차용:** 원본 에피소드/문서와 관계의 연결, 시스템 기록 시각과 사실 적용 시각 구분. **보류:** 자동 동일성 판정·관계 무효화를 승인 원장에 직접 반영하는 구조. 설치된 EXAONE/Qwen으로 한국어 규정 추출 품질이 유지되는지는 미확인이다.

## 4. LightRAG: 로컬 비교는 가능하지만 병합 그래프가 원문 원장을 대신하지 않음

조회한 기본 클래스는 `JsonKVStorage`, `NanoVectorDBStorage`, `NetworkXStorage`, `JsonDocStatusStorage`를 사용한다. 따라서 ‘LightRAG에는 반드시 별도 그래프 DB 서버가 필요하다’는 주장은 맞지 않는다. README는 기본 저장을 시험·평가 용도로 설명하고 운영 규모 저장 옵션도 별도로 제시한다. [기본 저장 선언](https://github.com/HKUDS/LightRAG/blob/4a319ecdc14f36446ae98b34952ab6719b2c322b/lightrag/lightrag.py), [공식 README](https://github.com/HKUDS/LightRAG)

재사용 후보는 entity·relationship 중심 검색과 텍스트 검색의 결합, 원문 chunk ID 연결이다. 반면 요약·병합된 entity/relationship 설명과 제한될 수 있는 source ID 목록을 유일한 근거 저장소로 사용하면 PRD의 문서 버전별 증거 보존과 맞지 않는다. `SOURCE_IDS_LIMIT_METHOD` 등 제한 설정이 존재하므로 근거의 완전성은 별도 원장에서 보장해야 한다. [저장·source 설정 안내](https://github.com/HKUDS/LightRAG#storage)

Ollama 구현이 제공되며 `think` 처리는 Ollama Python SDK 0.5.4 이상을 요구한다. 프로젝트의 `ollama==0.6.1`은 이 선언 조건에 들어간다. 그러나 로컬 지원 자체가 현재 설치된 소형 모델의 추출 정확도를 입증하지는 않는다. 로컬 실행 시 host와 모델을 명시해야 하며, 소스에는 cloud 모델 이름에 따른 원격 host 처리도 있다. [Ollama 구현](https://github.com/HKUDS/LightRAG/blob/4a319ecdc14f36446ae98b34952ab6719b2c322b/lightrag/llm/ollama.py)

전체 설치는 `nano-vectordb`, `json_repair`, `pipmaster`, `tiktoken`, Google API 관련 패키지 등 추가 의존성을 가져온다. 같은 구현에 누락 패키지를 import 시 설치하는 코드도 있어 이 패턴을 공통 코드에 복사할 이유는 없다. [의존성 선언](https://github.com/HKUDS/LightRAG/blob/4a319ecdc14f36446ae98b34952ab6719b2c322b/pyproject.toml)

**차용:** 검색 시 텍스트 근거와 관계 경로를 함께 반환하는 원리. **조건부 실험:** 검토된 스냅샷에서 파생시킨 검색 인덱스로만 사용하고, 기존 메타데이터 RAG와 동일 자료·모델로 비교한다. 프레임워크가 작성한 사실을 검토 없이 활성화하지 않는다.

## 5. Microsoft GraphRAG: 전역 요약 목적과 현재 환경 비용을 구분

공식 인덱싱 흐름은 text unit 생성, entity·relationship 추출/요약, 선택적 claim 추출, community detection, community report, embedding으로 구성된다. 전체 코퍼스의 주제·집단을 요약하는 흐름은 P0의 특정 공고 변경 영향 검토와 목적이 같지 않다. [공식 데이터 흐름](https://microsoft.github.io/graphrag/index/default_dataflow/)

현재 `packages/graphrag/pyproject.toml`과 기존 [requirements.txt](../../../requirements.txt)의 직접 제약은 다음처럼 충돌한다. Python 3.11을 허용한다는 이유로 현 가상환경에 그대로 추가할 수 없다.

| 의존성 | 현재 프로젝트 | 조회한 GraphRAG main 3.2.0 선언 |
|---|---|---|
| NumPy | `1.26.4` | `~=2.4` |
| pandas | `2.2.3` | `~=3.0` |
| PyArrow | `23.0.1` | `~=25.0` |
| Pydantic | `2.11.7` | `~=2.13` |

근거: [조회 커밋의 패키지 선언](https://github.com/microsoft/graphrag/blob/769542fbf1d8e5b4c6a8677fefc34621c87894c5/packages/graphrag/pyproject.toml). 이는 실제 설치 실패 재현 결과가 아니라 선언 범위의 충돌 확인이다. `graspologic-native` 등 네이티브 구성의 Mac/Windows 설치도 이번에는 검증하지 않았다.

로컬 파일과 기본 LanceDB를 사용할 수 있어 클라우드나 별도 그래프 DB가 필수인 것은 아니다. 모델 설정은 OpenAI 기본 구성과 다른 provider 경로를 제공하지만 구조화 JSON을 제대로 생성하는 모델이 필요하다. Ollama/OpenAI 호환 경로의 존재와 현재 Qwen·EXAONE 품질 보장은 별개다. [저장·설정](https://microsoft.github.io/graphrag/config/yaml/), [모델 요구](https://microsoft.github.io/graphrag/config/models/)

**차용:** 추출 단위를 원문 text unit과 연결하고, 파생 요약을 원문과 구별하는 방식. **보류:** 기존 Python 환경에 전체 패키지 설치. 전역 코퍼스 요약 비교가 필요해지면 별도 가상환경에서 수행한다.

명칭도 구분한다. 사용자가 참조한 Hu 등의 **GRAG, arXiv:2405.16506**은 textual subgraph retrieval과 text/graph view를 이용한 생성 연구다. Microsoft GraphRAG를 설치하거나 SQL 관계를 검색에 넣었다는 이유만으로 그 논문을 재현했다고 표현하지 않는다. [GRAG 원논문](https://arxiv.org/abs/2405.16506)

## 6. RDFLib·pySHACL과 W3C 표준: 재사용할 의미와 도입 조건

### 6.1 RDFLib·pySHACL

RDFLib는 RDF 파싱·직렬화·질의 기능을, pySHACL은 SHACL 검증을 제공한다. 메모리 RDF 그래프를 검사하는 데 외부 서버나 LLM은 필요하지 않다. pySHACL 0.40.1 소스는 `rdflib[html]>=7.3.0,<8`, `owlrl>=7.6.2,<8` 등을 요구하므로 ‘추가 의존성 없음’은 아니다. RDFLib 배포판 7.6.0은 Python 3.8.1 이상, 조회한 main은 3.10 이상이므로 배포판과 개발 브랜치를 구분한다. [RDFLib 문서](https://rdflib.readthedocs.io/en/stable/), [pySHACL 소스](https://github.com/RDFLib/pySHACL/blob/469cca7a22a078b36c167c1e8dadecf5e5ec6c75/pyproject.toml)

**직접 도입 조건:** 다른 도구에 RDF를 전달하거나 SHACL shapes를 독립 검사 계약으로 사용해야 할 때. 현재 JSON/Pydantic·SQL로 표현 가능한 필수 필드·ID·상태 검사만을 위해 두 번째 정본 스키마 체계를 만들지는 않는다.

### 6.2 SHACL: 구조 제약 통과와 의미적 진실은 다름

SHACL은 RDF 데이터 그래프를 shapes에 따라 검사한다. 필수 값 개수, 데이터형, 허용 값, 클래스·노드 종류 같은 제약을 명시할 수 있다. 따라서 출처 연결 누락이나 허용하지 않은 관계 형식은 검사 가능하다. 그러나 원문의 문장이 해당 주장을 뒷받침하는지, 예외가 적용되는지, 해당 날짜에 법적으로 유효한지는 구조 검사만으로 확정되지 않는다. [W3C SHACL](https://www.w3.org/TR/shacl/)

이번 PRD에서는 세 단계를 구분한다: ① ID가 등록부에 존재함 ② 스키마·관계 제약에 맞음 ③ 원문·범위·시점에 비추어 그 주장과 연결이 맞음. 앞의 두 단계가 통과했다고 세 번째를 자동 승인하지 않는다.

### 6.3 SKOS: 한국어 명칭·별칭·정의와 관계 구분

SKOS의 `prefLabel`, `altLabel`, `definition`, `scopeNote`는 한국어 용어 사전의 출발점으로 쓸 수 있다. `broader`, `related`, `exactMatch`, `closeMatch`를 구분해 유사어를 모두 동일 ID로 합치는 일을 피한다. `broader` 자체는 전이 관계로 선언되지 않으며 전이적 확장은 `broaderTransitive`로 구분된다. [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)

**제안:** PRD Concept에 대표명·별칭·정의·적용 범위를 두고 공식 단지·부서 ID의 Entity 연결은 별도 검토한다. 개념 간 `exactMatch`를 실제 조직·단지의 무검토 자동 병합 규칙으로 쓰지 않는다. 표준 의미를 참고하는 것과 SKOS 적합 RDF를 실제로 발행하는 것은 구분한다.

### 6.4 PROV-O: 근거와 생성·검토 활동 연결

PROV-O는 Entity·Activity·Agent와 `wasDerivedFrom`, `wasGeneratedBy`, `used`, `wasAttributedTo`, `wasRevisionOf` 등의 출처 관계를 제공한다. [W3C PROV-O](https://www.w3.org/TR/prov-o/)

**제안 매핑:** SourceVersion·Assertion을 출처 모델의 Entity로, 추출 Run·검토를 Activity로, 모델 소프트웨어와 실제 검토자를 구분한 Agent로 기록한다. 여기서 PROV의 Entity는 PRD의 회사·단지 Entity 테이블보다 넓은 의미다. AI 검토 활동을 기록했다고 사람이 승인한 사실로 바꾸지 않는다. 생성 시각을 규정의 시행일로 대체하지 않으며, JSON 필드 명칭을 차용한 단계에서 PROV-O 완전 준수를 주장하지 않는다.

## 7. SQLite·기존 NetworkX로 먼저 해결할 경계

SQLite는 recursive CTE를 지원한다. PRD의 최대 2-hop 영향 후보는 단순 관계 테이블 조회나 제한된 재귀 질의로 구현할 수 있다. 이 요구만으로 그래프 DB를 추가할 필요는 없다. NetworkX는 이미 프로젝트에 있으므로 별도 경로·연결성 알고리즘이 필요할 때 메모리 파생 그래프로 사용할 수 있다. SQLite와 NetworkX 양쪽을 수정 가능한 정본으로 유지하지 않는다. [SQLite recursive CTE](https://www.sqlite.org/lang_with.html)

현재 `networkx==3.6.1`은 Python 3.11.9 대상에 맞는 선언을 가진다. 조사 시점 최신 3.7은 Python 3.12 이상을 요구하므로 최신판으로 무조건 올리는 선택은 환경 조건에 맞지 않는다. [3.6.1 메타데이터](https://pypi.org/pypi/networkx/3.6.1/json), [3.7 메타데이터](https://pypi.org/pypi/networkx/3.7/json)

구체적인 최소 접점은 다음과 같다.

| PRD 요구 | 지금 재사용할 것 | 직접 구현·보존할 계약 |
|---|---|---|
| 온톨로지 초안 | SKOS의 명칭·정의·관계 구분, 기존 구조화 LLM 호출 | 사람의 수락·수정·보류·기각, 개념 의존성 검토 |
| 근거 있는 Assertion | PROV의 파생·활동·버전 구분 | SourceVersion·원문 위치·짧은 인용·범위·시점 |
| 형태·참조 검사 | 기존 Pydantic, SQL 제약·명시적 조회 | 의미 검토와 분리. 필요 시에만 SHACL export 검사 |
| 변경 영향 후보 | SQLite 관계 조회, 필요한 경우 기존 NetworkX | 최대 2-hop·연결 이유·검토 결과 기록 |
| 활성화·중단·복원 | SQLite 트랜잭션 | 불변 Snapshot과 별도 AvailabilityHistory, 복원 시 최신 중단 상태 적용 |
| P1 답변 보조 | 기존 검색·생성 모델 호출. 후속 LightRAG 비교 가능 | assertion IDs·snapshot·scope·as-of 재검증과 응답 전 상태 재확인 |

## 8. 유지보수 판단과 남은 확인

확인한 최신 릴리스는 Graphiti [0.30.2, 2026-09-08](https://github.com/getzep/graphiti/releases/tag/v0.30.2), LightRAG [1.5.7, 2026-09-02](https://github.com/HKUDS/LightRAG/releases/tag/v1.5.7), Microsoft GraphRAG [3.2.0, 2026-09-24](https://github.com/microsoft/graphrag/releases/tag/v3.2.0), RDFLib [7.6.0, 2026-02-13](https://github.com/RDFLib/rdflib/releases/tag/7.6.0), pySHACL [0.40.1, 2026-07-28](https://github.com/RDFLib/pySHACL/releases/tag/v0.40.1)이다. 최근 배포와 실제 Python 제약을 확인했으며 stars를 적합성 근거로 사용하지 않았다. 최근 릴리스는 유지보수 활동의 증거이고 우리 자료의 정확도·보안·장기 지원 보장은 아니다.

패키지 라이선스는 저장소 코드 기준이다. 사용 모델·별도 DB·전이 의존성·입력 자료의 이용조건까지 같은 라이선스라고 해석하지 않는다. 코드 직접 복사나 배포를 결정할 때 해당 고지 조건을 보존한다.

추가 확인은 선택한 후보에만 한정한다. RDF 교환 요구가 확정되면 RDFLib·pySHACL의 고정 버전 의존성 해석과 소수 제약 검사를 확인한다. 검색 실험이 필요하면 LightRAG를 별도 환경에서 동일한 검토 자료·모델로 비교한다. 검수 시간·누락·오탐 측정 없이 자동 그래프 구축이 정확하거나 저렴하다고 결론 내리지 않는다. 전체 파이프라인 효과와 그래프 관계만의 효과도 구분한다.

조사 원문 소량 사본과 조회 커밋·릴리스 메타데이터는 로컬 `/tmp/company-knowledge-graph-research/`에 보관했다. 임시 디렉터리는 저장소 배포 자산이 아니므로 재확인은 본문의 공식 링크를 기준으로 한다.
