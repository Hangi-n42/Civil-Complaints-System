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
