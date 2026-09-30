# K3 오픈소스 재사용 기록

기준: 2026-09-27. 전체 엔진의 도입·논문 재현·동일 성능을 의미하지 않는다.

| 자산 | 고정 버전/커밋 | 실제 사용 | 제외 |
|---|---|---|---|
| LinkML / linkml-runtime | 1.11.1 / 1.11.1 | SchemaView, JsonSchemaGenerator 공개 API 직접 호출 | 패키지 내부 수정, 자체 스키마 컴파일러 |
| OntoGPT | 9224d33f84cce7097c3519e1d9f0e2be46cec056 | template_skeleton의 root·class·slot·prefix 구성과 validate_template의 root/range/prefix 검사 방법을 `ontology_schema.py`에 맞게 이식 | core·생의학 클래스·annotator·OAK·코드 생성/import·세미콜론 목록 |
| AutoSchemaKG | d0a1666ae6621806faf814504c73678de4e809f2 | 개체/관계 표현에서 추상 유형을 찾는 conceptualization 지침을 한국어 CQ·근거 기반 프롬프트로 재작성 | 무작위 이웃 표본·개념명 해시 ID·별도 그래프/모델 실행기 |

원본 자산:

- [OntoGPT template_skeleton](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/skills/ontogpt-author-template/assets/template_skeleton.yaml)
- [OntoGPT validate_template](https://github.com/monarch-initiative/ontogpt/blob/9224d33f84cce7097c3519e1d9f0e2be46cec056/skills/ontogpt-author-template/scripts/validate_template.py)
- [AutoSchemaKG conceptualization 지침](https://github.com/HKUST-KnowComp/AutoSchemaKG/blob/d0a1666ae6621806faf814504c73678de4e809f2/atlas_rag/llm_generator/prompt/triple_extraction_prompt.py)
- [LinkML JSON Schema](https://linkml.io/linkml/generators/json-schema.html)

OntoGPT의 구조·검사 방법을 회사 지식용으로 적응했으며 원본 validator 그대로가 아니다. AutoSchemaKG는 방법을 재구현한 것으로 프롬프트 전문이나 엔진 코드를 복사하지 않았다. 원본 저장소 라이선스는 [OntoGPT](ontogpt_LICENSE.txt), [AutoSchemaKG](autoschemakg_LICENSE.txt)에 보존했다. OntoGPT skeleton 자체에는 CC0 선언이 있다.

LinkML 정본의 candidate annotation에 정의·포함/제외·CQ·근거를 보존한다. Pydantic은 고정 메타모델만 검증하고, 회사 도메인 클래스·슬롯은 LinkML에서 파생한다. 허용하지 않은 후보 필드는 명시적으로 거절한다. 복잡한 법률 조건은 자연어 정의/범위로 남기며 실행 가능한 법률 규칙으로 변환하지 않는다.


## K4 적용 (2026-09-28)

- `langextract==1.7.0`의 `Extraction`·`Resolver.align` 공개 API만 호출한다. `fuzzy=False`, `accept_match_lesser=False`에 원문 substring 일치 확인을 더했다. 한국어 부분 어절·반복 발췌는 미해결로 남긴다.
- 원본 [Resolver](https://github.com/google/langextract/blob/62b933a2c757fd2bbb100498571b8d1692db4344/langextract/resolver.py), [Apache-2.0 라이선스](langextract_LICENSE.txt). 패키지 내부 수정·코드 복사는 없다. 배포 패키지에 포함된 라이선스를 보존했다.
- `lx.extract`·provider·원격 API를 사용하지 않는다. 패키지의 Google SDK 전이 의존성은 설치되지만 실행에는 사용하지 않는다.
- 기존 Pydantic·protobuf·OpenTelemetry 제약을 유지하도록 google-genai 2.8.0, google-api-core 2.33.0, proto-plus 1.28.2를 함께 고정했다. 현재 Mac Python 3.11.9에서 pip check 통과. Windows 전체 설치는 미확인이다.
- LinkML JSON Schema를 그대로 바탕으로 추출 슬롯 타입을 구성한다. 단지 현황 PDF 표의 명시 헤더 3개가 확인될 때는 단지명·수량·최초입주월 슬롯만 허용한다. OntoGPT의 표기/ID 연결 분리, SKOS식 별칭, PROV식 출처는 로컬 원장 필드로 반영하며 엔진·외부 온톨로지를 추가하지 않는다.

## A3 적용 (2026-09-30)

- 기존 LinkML/runtime 1.11.1의 `SchemaView`·`JsonSchemaGenerator`를 저장된 v2 YAML에 직접 호출한다. `class_slots`로 상속 슬롯을 조회하며 v1 후보 재구성으로 정본을 다시 만들지 않는다. 공개 API 호출이며 외부 코드 추가 이식·패키지 내부 변경은 없다.
- `uuid`, `hashlib`, `sqlite3`, 기존 Pydantic을 사용한다. YAML은 클래스/슬롯/클래스 별칭·구조 링크, 같은 버전의 registry는 어휘/어휘 링크·별칭/대체 ID를 소유한다. diff는 ID별 필드 비교로 충분하여 별도 diff 패키지를 추가하지 않았다.
- 선택형 `vocabulary-broader-v1`은 [SKOS 2009-08-18](https://www.w3.org/TR/2009/REC-skos-reference-20090818/)의 의미 참고를 로컬 메타데이터로 기록한다. W3C document license, 코드·정의 전문 복사 없음. 회사 정의를 공통 메타모델에 추가하거나 RDF 적합성을 주장하지 않는다.
