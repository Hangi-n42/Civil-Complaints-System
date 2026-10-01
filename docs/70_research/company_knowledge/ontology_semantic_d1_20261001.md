# 의미구축 D1 — 원문 지지와 연결 상태 분리

- 대상: [#535](https://github.com/Hangi-n42/Civil-Complaints-System/issues/535), 선행 동결만 [#539](https://github.com/Hangi-n42/Civil-Complaints-System/issues/539)에 해당한다. #536~#539의 구현/모델 비교는 수행하지 않았다.
- 기준: `feature/ontology-semantic-improvements`의 `e19bd8fac617ed7945acfb327355643481820cbd`. 기존 A1~A6 완료 기록, 원문, 원장, 승인 버전은 변경하지 않았다.
- 이유: 끝점 미연결이나 기존 개념 대응 미확정 때문에 원문의 근거 성격까지 `unresolved`로 덮어쓰면, 근거 수정과 유형 연결 수정을 구분할 수 없다. 기존 `support_type`, `origin`, `validation`, 결정 이력을 재사용했다.

## 구현 전 C2 동결

- 설정: `configs/knowledge/quality_20261001/semantic_construction_c2_v1.json`, SHA-256 `248b2475d03473f36e4f92030e2402a7a72f26e71c77a6856dc5e130f7533bd3`.
- 추적 파일 변경이 없는 e19bd8f에서, 제품 코드 수정 전에 작성했다. 기존 실행기 입력 형식을 유지하고 비교 메타데이터만 추가했다. 새 평가 프레임워크는 없다.
- 규칙 제15조/C2, 실제 분석 3블록과 동결 전체 입력 6블록의 ID/해시, current_discovery/step 0, manifest/입력 원장 해시, 기준 온톨로지 없음, 모델 tag/digest/options, 예산을 고정했다.
- 모델 호출 5회/1,800초, 검색 4회, 추가 라운드 0, revision 0, 호출 timeout 300초, 입력 12,000자, context 32,768, output 4,096, temperature 0, think false다. 모델 메타데이터만 조회했으며 생성 호출은 0회다.
- 필수/금지/허용 의미는 기존 `assessor.json`의 `current.C2`와 파일 해시로 고정하고 생성 프롬프트에 제공하지 않는다. 이후 전달된 [전문가의 의미 구체화](https://github.com/Hangi-n42/Civil-Complaints-System/issues/539#issuecomment-5931351038)는 이 기준의 해설이며 정답 후보 수나 새 그래프를 추가하지 않았다.
- v15에 기록된 `code_sha=bce08c3`는 그대로 보존했다. 기록된 런타임 파일 해시는 e19bd8f와 모두 일치하고, 두 커밋 사이 변경된 런타임 파일 중 해시 기록 밖 파일은 없었다. 입력·recipe·현재 설치 모델 digest도 일치했다. 이 사실은 동결 파일에 기록했으며 v15를 e19 실행으로 재표기하지 않았다. 기준선 최종 재사용 판단과 실제 비교는 D5에서 수행한다.

## 변경한 경계

- A3 변환은 끝점 미연결/개념 대응 미확정을 이유로 원래 `support_type`을 덮어쓰지 않는다. 미확정 자체는 기존 `origin.unresolved_endpoints`, `origin.change_intent=alignment_pending`, 보류 상태와 검증 오류로 표시한다.
- 미제공 ID가 우연히 기존 class ID와 같더라도 연결 미해결 오류를 유지해 직접 수락을 막는다. 관계의 명시적 `after.domain_id/range` 수정은 해당 끝점의 미해결 표시만 해소하고, 수정 전 상태는 원제안/결정 이력에 보존한다. 유효한 class ID·원문 근거·지원 성격·방향/부정·의존성 검사는 계속 수행한다. 판단 사유만 수정해서 끝점 오류를 우회할 수 없다.
- 기존 개념 대응이 미확정인 새 제안은 별도 오류로 직접 수락을 차단한다. 기존의 명시적 편집 경로와 새 target ID는 유지한다. 이름이 다른 기존 target을 바꾸는 잘못된 update의 방어는 그대로다.
- UI는 이미 제안 성격·구조/근거 오류·미해결 쟁점·결정 이력을 표시한다. 이번에는 새 UI나 상태 필드를 추가하지 않았다.

| A2 산출/근거 성격 | A3 보존 계약 |
|---|---|
| 원문 정의 type/vocabulary + explicit | class/vocabulary_concept + explicit |
| 사례에서 유도한 instance_proposal | 근거를 유지한 design_proposal; 원문 직접 정의로 승격하지 않음 |
| 규칙/정의 관계 | 기존 statement_type/조건과 explicit 매핑 유지; 타입 미연결은 별도 오류 |
| design_proposal 관계 | 설계 제안 성격 유지; 유효한 유형 연결/근거 필요 |
| 원래 unresolved/자료 미제공 | unresolved 유지; endpoint만 수정해도 수락 불가 |
| 개별 entity/값 또는 instance 관계 | 기존 참고 관측/K4 경계 유지 |

규범에서 역할 타입을 설계하는 Builder 출력 확장은 D3(#537) 범위다. D1에서 없는 타입을 만들거나 legacy unresolved를 explicit으로 추정하지 않았다.

## 실제 확인 결과

- Python 3.11.9, `test_knowledge_ontology_changes.py`와 `test_knowledge_discovery_analysis.py`: **124 passed, 11.70초**. A3 검수/결정·v1 호환·ID/이력, A2 normalize/재개 경계를 함께 확인했다.
- 새 집중 회귀: explicit/설계/원래 미해결의 구분, endpoint 명시 수정 후 남는 인용 오류·근거 부재·부정 관계 오류, 실제 존재하지만 미제공인 ID의 직접 수락 거절, 과거 저장 payload 읽기 불변. 유효한 경우 수정→수락→정본 재조회에서 조건·인용·ID 보존을 확인했다.
- 최초 A3 파일 실행은 55 passed/1 failed였다. 실패는 테스트가 publish의 정상 `changeset_id` 추가 이전 run과 조회 이후 run을 비교한 문제다. 게시 후 저장값을 기준으로 고쳤으며 제품 동작을 바꾸지 않았다. 최종 124개 결과와 중복 합산하지 않는다.
- 저장 v15 SQLite를 `mode=ro`로 열어 `_convert`/`_validate`만 메모리에서 재현했다. 관계 4개의 근거 성격은 rule에서 explicit으로 유지되고, 유형 4개는 unresolved 그대로다. 후보 **총 8개/수락 가능 0개** 유지, 끝점 미해결이 별도 오류로 남는다. 원문 인용·조건 동일, 원래 A2 result/저장 changeset/DB SHA 불변을 확인했다. 생성·결정·DB 쓰기 0회이며 새 실제 모델 실험이 아니다.
- 로컬 재현 기록: `data/knowledge/quality_20261001/d1_support_separation/result.json`. DB와 원출력은 커밋하지 않는다.
- 과거 저장 v15 후보를 조회하면 기존 unresolved 기록이 그대로 보인다. 변경 코드는 새 변환부터 적용되며 저장 payload를 자동 마이그레이션하지 않는다.

## 남은 문제와 #536 연결

- D1은 원인 표시와 수정 책임을 분리한 기능 보완이다. 원문 인용 오류, 역할/대상 타입 설계, 실제 끝점 연결, 모델 의미 정확성이 해결됐다는 결과가 아니다.
- #536은 실제 제공 packet의 ref 선택으로 quote/span을 복원하고 Critic의 개별 오류를 격리해야 한다. finish/revise/A3의 유효 검수 범위도 함께 반영하되 기존 exact quote와 과거 결과 읽기 호환을 유지한다.
- D2 이후에도 `support_type`을 연결 상태로 덮지 말고 원 관측·조건·근거를 보존한다. 저장 결과의 재처리나 새 모델 실행은 별도 기록으로 구분한다.
- 사람 참가자 0명/사람 시간 null, 실제 모델 비교·전체 자료·Windows 실기 미수행. 운영 활성화·PR 병합 없음. 현재 사용자 결정이 필요한 사항 없음.
