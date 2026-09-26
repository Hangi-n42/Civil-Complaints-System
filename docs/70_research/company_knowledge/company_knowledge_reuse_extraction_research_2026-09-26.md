# 회사 지식 추출·초기 온톨로지 OSS 재사용 조사

기준: 2026-09-26, `company_knowledge_prd.md` v1.0의 P0. 공식 저장소의 main 코드·선언된 의존성·문서를 정적으로 확인했다. 설치·모델 실행·한국어 품질 비교·Windows 실행은 하지 않았다. 아래 권고는 구현 제안이며 성능 확인 결과가 아니다.

## 1. 결정 요약

**기존 Pydantic·Ollama를 직접 재사용하고, OntoGPT의 초안 작성 지침과 추출→ID 연결→용어 검증 분리를 차용한다. OntoGPT·LinkML·OAK·Instructor 전체 패키지는 지금 추가하지 않는다. LangExtract는 원문 위치 복원이 실제 병목일 때 독립 비교할 첫 후보로 둔다.**

이 결론은 해당 도구가 불필요하다는 뜻이 아니다. P0는 문서 버전 20개+CSV 1개, 단일 운영자, 기존 의존성 유지이며 이미 JSON Schema를 Ollama에 전달하는 코드가 있다. 전체 프레임워크 도입과 이번에 필요한 일부 기능의 재사용을 구분해야 한다. 현재 [호출 코드](../../../app/generation/service.py)는 `format=response_schema or "json"`을 지원한다. 기존 [민원 구조화 검증기](../../../app/structuring/verifier.py)를 회사 지식의 범용 의미 검증기로 간주하지 않는다.

| 후보 | 실제 확인한 강점 | P0 판단 | 해결하지 않는 부분 |
|---|---|---|---|
| OntoGPT | 템플릿 작성 agent skill, SPIRES 구조 추출, OAK grounding, 용어 검증 상태 | 원리·프롬프트 설계 차용 | 승인 가능한 온톨로지 자동 완성, 업무 조건·시점의 정확성, 변경 검토 업무 |
| LinkML / OAK | 선언적 스키마·생성기 / 여러 온톨로지 backend의 공통 접근 | 개념 차용, 런타임은 유보 | LH ID 등록부 자동 제공, 원문이 관계를 뒷받침하는지 판단 |
| LangExtract | 추출 문자열의 문자 위치·정렬 상태, 로컬 Ollama provider | 별도 비교 후보 | 원문 span의 의미적 진실성, PDF/HWPX의 원래 표·페이지 자동 보존 |
| Instructor | Pydantic 출력 검증·제한 재시도, Ollama 연동 | 기존 기능과 겹쳐 유보 | 온톨로지 유도, 개체 동일성·근거·유효기간 검증 |

## 2. OntoGPT: 무엇을 가져올 것인가

### 2.1 초기 온톨로지 작성 지원은 실제 존재한다

최신 main에 `ontogpt-author-template` skill, 템플릿 skeleton, ontology 선택 guide, `validate_template.py`가 있다. 외부 코딩 에이전트가 목표 필드·유형·관계·프롬프트·annotator를 작성하도록 안내하고, 스키마의 root·range·prefix·코드 생성 가능 여부 등을 점검한다. 따라서 **‘OntoGPT는 기존 스키마 추출만 하며 새 스키마 작성 지원이 전혀 없다’는 설명은 부정확하다.** 다만 이는 에이전트용 작성 절차이며, 데이터 전체에서 회사 개념을 발견하고 근거·포함/제외 정의·버전·사람의 검토까지 완결하는 제품 기능은 아니다. [작성 skill](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/skills/ontogpt-author-template/SKILL.md), [검증 script](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/skills/ontogpt-author-template/scripts/validate_template.py), [agent skill 문서](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/docs/agent_skills.md)

CLI도 확인했다. `suggest-templates`는 제공된 주제에 맞는 **기존 템플릿 선택**이다. `generate-extract`는 텍스트를 생성한 뒤 지정 템플릿으로 추출하며 템플릿이 없으면 오류를 낸다. `iteratively-generate-extract`도 템플릿을 전제로 한다. 확인한 CLI에 독립적인 `generate-template` 명령은 없었다. 생성한 설명을 회사 원문 근거로 취급하는 흐름은 채택하지 않는다. [CLI](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/cli.py#L541)

**적용 제안:** PRD의 자료 분석→온톨로지 설계→반례 검토 순서를 유지하되, 입력은 등록한 원문 절·CSV 필드·실제 값으로 제한한다. 출력은 실행 코드가 아닌 `개념 후보/정의/포함·제외/허용 관계/근거/미확인` 데이터다. 고정 메타모델 안에서 후보를 작성하고 사람이 수락한 버전만 추출 계약으로 사용한다. OntoGPT 작성 지침의 필드별 설명·적은 중첩·자료형·prefix 일관성은 가져오되, 임대업무 개념 사전이 이미 완성됐다고 가정하지 않는다.

### 2.2 추출, grounding, 검증을 분리한다

SPIRES는 스키마의 클래스·슬롯을 따라 추출하며 중첩 값에 재귀 추출을 적용한다. 중첩 항목 수에 따라 호출이 늘고, 하위 호출에는 추출된 문자열이 입력될 수 있다. 우리 P0에서는 제한된 절·표 단위의 명시적 출력 스키마로 시작한다. 이를 SPIRES 전체 알고리즘 재현이라고 부르지 않는다. [SPIRES 코드](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/engines/spires_engine.py)

`normalize_named_entity`는 grounding 결과를 정규화해 반환한다. 해당 경로는 `NamedEntity.original_spans=None`으로 개체를 생성하고, 연결에 실패하면 설정에 따라 `AUTO:` 계열 식별자 또는 원래 문자열을 남긴다. **ID를 반환했다는 사실과 원문 위치를 보존했다는 사실은 다르다.** 첫 grounding 결과 반환을 승인된 동일성 판단으로 복사하지 않는다. [knowledge engine](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/engines/knowledge_engine.py#L504)

TermValidator는 adapter를 통한 ID 존재·폐기 상태·label/alias를 확인한다. adapter가 없거나 점검 예외가 생기면 `SKIPPED`, 존재하는 ID의 표기가 다르면 `LABEL_DIFFERS`가 될 수 있다. 일부 경우 대체 ID도 찾는다. 즉 **모든 반환 ID가 검증 통과한 것은 아니며, ID 존재 검증은 관계·조건·시점 검증이 아니다.** [용어 검증 코드](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/validation/term_validator.py#L294)

**LH 적용 제안:** 코드가 `(발행기관/네임스페이스, 공식 ID)`를 CSV 등록부에서 조회한다. 공고에 실제 명시된 코드와 대상인지 별도로 확인한다. 이름만 매칭되면 별칭 후보, ID 미존재·범위 불명은 미연결 상태로 둔다. `VALID / unresolved / review_required` 같은 구분은 제품 요구에 맞게 최소화하되, 점검하지 못한 결과를 통과로 취급하지 않는다. OAK의 생의학 온톨로지 adapter를 설치한다고 LH 코드 grounding이 생기지 않는다.

### 2.3 직접 복사하지 않을 구현

- 사용자 YAML을 설치 패키지의 templates 디렉터리에 복사하고 Python 모델을 생성·import하는 흐름: 검토 전 후보와 활성 스키마를 구분해야 하는 P0에는 불필요하다. 버전이 있는 데이터와 기존 Pydantic 검증으로 시작한다. [template loader](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/io/template_loader.py)
- LiteLLM·디스크 캐시·다수 공급자 추상화 전체: Ollama 모델/API 주소는 지원하지만 로컬 LLM 설정만으로 외부 ontology adapter까지 오프라인이 되지 않는다. 필요한 호출 경계가 현재 프로젝트에 이미 있다. [LLM client](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/src/ontogpt/clients/llm_client.py)
- 자동 대체 ID를 활성 지식에 즉시 반영: 대체는 검토 후보로만 남긴다. 이는 이 프로젝트의 동일성·버전 요구에 따른 설계 결정이다.

## 3. LinkML / OAK: 표준화 자산과 런타임 도입을 구분한다

LinkML은 클래스·속성·자료형·필수 여부·enum·prefix 등을 선언하고 Pydantic 등으로 생성할 수 있다. 의미와 구조를 명시하는 데 유용하지만 생성 모델의 데이터가 실제 원문에서 성립하는지까지 보장하지 않는다. **지금은 기존 Pydantic 객체와 버전 있는 개념 사전에 동일 정보를 담는다.** 외부 기관과 LinkML/RDF 계약을 교환해야 할 때 오프라인 export·생성기의 도입을 다시 판단한다. [Pydantic 생성기 공식 문서](https://linkml.io/linkml/generators/pydantic.html), [LinkML 저장소](https://github.com/linkml/linkml)

OAK는 로컬 OWL/OBO/OBOJSON/온톨로지 SQLite 및 원격 서비스에 공통 인터페이스를 제공한다. `sqlite:obo:cl`과 같은 연결은 해당 온톨로지와 adapter 계약을 전제로 한다. 회사의 임의 SQLite 테이블을 그대로 넣어 업무 개체 검색기로 쓸 수 있다는 뜻이 아니다. LH CSV와 별칭의 작은 등록부에는 기존 SQLite 조회가 우선이다. OAK 도입은 실제 재사용할 외부 온톨로지·형식·질의가 정해졌을 때 검토한다. [OAK 공식 README](https://github.com/INCATools/ontology-access-kit/blob/5f88047efa9f699d7d023e33086df6ff5a1c3820/README.md)

## 4. LangExtract: 원문 위치를 보존하는 추출의 비교 후보

공식 코드의 `Extraction`에는 `char_interval`, `alignment_status`가 있고, resolver는 exact·lesser·fuzzy 정렬을 구분한다. 기본 설정에 fuzzy alignment가 활성화되어 있다. **원문과 비슷한 span을 찾았다는 것은 정확한 인용 일치도, 그 문장이 추출 관계를 지지한다는 증명도 아니다.** 실제 quote를 원문 slice와 대조하고 정렬 상태를 유지해야 한다. 한국어를 위한 Hangul 문자 처리도 현재 tokenizer에 존재하지만, LH 자료에서의 정확도·표 복원 품질은 확인하지 않았다. [데이터 모델](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/core/data.py), [resolver](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/resolver.py), [tokenizer](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/core/tokenizer.py#L248)

Ollama provider는 로컬 호출을 지원하며 `think=False`를 기본값으로 넣고 실제 payload에 전달하는 코드가 있다. 다만 README는 **LangExtract의 Ollama provider가 `output_schema`를 지원하지 않는다**고 명시한다. 이는 Ollama 자체에 JSON Schema 기능이 없다는 뜻이 아니다. 현재 프로젝트의 schema 호출을 대체하면 오히려 기능 차이가 생길 수 있다. [Ollama provider](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/providers/ollama.py#L280), [공식 Ollama 사용 설명](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/README.md#using-local-models-with-ollama)

**제안:** 먼저 `Evidence`에 원문 버전·block/표 셀 ID·문자 offset·발췌를 보존한다. 파싱 후 텍스트의 offset과 PDF 물리 페이지·HWPX 표 셀의 대응은 우리 파서가 담당한다. 이후 기존 추출+원문 일치 확인으로 해결되지 않는 위치 복원 문제가 측정됐을 때만 LangExtract를 별도 환경에서 같은 원문·모델·정답 span으로 비교한다. 이 라이브러리를 쓰는 것만으로 온톨로지 초기 설계나 사람 검수 시간이 개선됐다고 주장하지 않는다.

## 5. Instructor: 출력 구조 검증은 유용하나 현재 중복이 크다

공식 Ollama 연동은 Pydantic `response_model`과 명시적 mode, 제한된 재시도를 지원한다. 반환 자료형을 강제하고 파싱 오류를 다루는 기능이며 원문 의미·공식 ID 동일성·적용일의 사실성을 확인하는 기능은 아니다. 현재 Pydantic/Ollama 호출을 유지한다. 도입 시 모델 자동 선택이나 별도 수정 루프까지 가져오지 않는다. [공식 연동 문서](https://python.useinstructor.com/integrations/ollama/), [저장소](https://github.com/567-labs/instructor)

## 6. Python·라이선스·의존성·로컬 조건

아래는 **조사 시점 main의 선언**이다. 최신 배포판의 설치 결과가 아니고 과거 모든 버전이 충돌한다는 뜻도 아니다. 라이선스는 프로젝트 자체의 표기이며 전이 의존성 전체의 이용 조건을 대표하지 않는다.

| 후보·확인 SHA | Python 선언 / 라이선스 | 기존 환경에 대한 확인 사항 |
|---|---|---|
| OntoGPT `9224d33f` | `>=3.10,<3.15` / BSD-3-Clause | `numpy>=2.0.0`이 현재 `numpy==1.26.4`와 직접 충돌. LinkML·OAK·LiteLLM·PyMuPDF·SciPy 등도 기본 의존성. [pyproject](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/pyproject.toml) |
| LinkML `5ef7622e` | `>=3.10` / Apache-2.0 | 현재 main의 LinkML과 runtime은 `pydantic>=2.13.5`로 기존 `2.11.7`과 충돌. LinkML은 `pydantic-settings>=2.15.0`으로 기존 `2.10.1`과도 충돌. [LinkML 의존성](https://github.com/linkml/linkml/blob/5ef7622e727470cfad637e7519240d275df836c3/packages/linkml/pyproject.toml), [runtime](https://github.com/linkml/linkml/blob/5ef7622e727470cfad637e7519240d275df836c3/packages/linkml_runtime/pyproject.toml) |
| OAK `5f88047e` | `>=3.10,<4,<3.15` / Apache-2.0 | semsql·LinkML runtime·여러 ontology client 등 의존 범위가 넓다. 전체 해석·설치 충돌은 미확인. optional gilda의 제약을 core 제약으로 오인하지 않는다. [pyproject](https://github.com/INCATools/ontology-access-kit/blob/5f88047efa9f699d7d023e33086df6ff5a1c3820/pyproject.toml) |
| LangExtract `62b933a2` | `>=3.10` / Apache-2.0 | numpy·Pydantic 직접 하한은 기존 pin과 양립하지만 전체 resolver 결과는 미확인. 로컬 실행에도 기본 의존성에 google-genai·google-cloud-storage가 포함된다. 설치 의존성과 원격 전송은 별개다. [pyproject](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/pyproject.toml) |
| Instructor `e12f8b49` | `>=3.9,<4` / MIT | Python3.11에서 requests>=2.33.0, urllib3>=2.7.0, idna>=3.15, click>=8.3.3 요구가 기존 2.32.3/2.6.3/3.11/8.3.1과 각각 충돌. [pyproject](https://github.com/567-labs/instructor/blob/e12f8b49203b0c1f253d27c1e709d0a09b9fc5a8/pyproject.toml) |

기존 pin은 [requirements.txt](../../../requirements.txt)에서 확인했다. 모든 후보의 Python 선언에 3.11이 들어가지만 **Python3.11.9 Mac/Windows 실제 실행 호환성이 입증된 것은 아니다.** 이번 조사에는 추가 설치·다운로드 모델·환경 변경이 없다. 기존 의존성을 지키는 P0 권고에서는 플랫폼 전용 코드나 별도 패키지 관리 계층이 필요하지 않다.

## 7. 구현할 때의 최소 적용 순서

1. **기존 기능 직접 재사용:** Ollama 구조화 호출, Pydantic, SQLite, 현재 로컬 모델 설정. 실행마다 원문·모델·prompt/schema 버전을 기록한다.
2. **자료에서 초기 개념 후보 작성:** OntoGPT author-template의 필드 정의·유형·예시 지침을 참고한다. 업무 정의·근거·반례·검토 상태는 PRD 요구대로 데이터로 작성한다. OntoGPT 설치를 선행 조건으로 만들지 않는다.
3. **추출과 확인을 분리:** 후보 추출→공식 ID 조회→원문 위치/발췌 일치→조건·관계 검토. 앞 단계 통과로 뒤 단계 정확성을 대신하지 않는다.
4. **유용성이 확인된 기능만 확장:** 원문 위치 오류가 남을 때 LangExtract 비교, 외부 ontology 교환이 필요할 때 LinkML/OAK 검토. 새 비교 때문에 PRD의 B1 기준선을 약화하지 않는다.

이 경로는 라이브러리를 설치했다는 사실이 아니라 **동일 필수 산출물의 사람 수정·검토·유지 시간을 줄이는지**로 채택을 판단한다. 한국어 추출, 개체 오병합, 적용 범위·시점, 변경 영향의 정확도 개선은 현재 미확인이다.
