# 의미구축 D2 — 제공 구간 참조와 후보별 검수 오류 격리

- 대상: #536, 상위 #534. D1 `e5991b46b86e7071bd7cc4fe818c55179e785c7a` 이후 변경.
- 브랜치: `feature/ontology-semantic-improvements`.
- 목적: 모델의 원문 복사 오류를 줄일 입력 계약을 제공하고, Critic 개별 오류가 독립적인 정상 판단을 버리거나 검수 완료로 잘못 집계되지 않도록 한다.

## 구현과 선택 이유

- 기존 packet의 focus/shared view에 호출별 `source_ref`를 붙인다. 원문을 중복 직렬화하는 별도 참조 표, 토크나이저, DB는 추가하지 않는다.
- 모델은 복수 `source_refs`/`counter_source_refs`를 선택한다. 서버는 실제 제공된 view에서 부모 block/evidence/version/parse/span/locator/quote를 복원한다. 미제공 구간이나 다른 실행·호출의 참조는 거절한다.
- 동일 문자열이 여러 위치에 있어도 선택한 view의 부모 offset을 보존한다. legacy exact quote 경로를 유지하며 ref와 함께 제출한 quote/ID가 서로 다르면 거절한다. fuzzy 보정은 하지 않는다.
- Critic 응답의 전체 구조는 기존 Pydantic으로 검사하고, 개별 쟁점·관계·계층·누락 복구는 record별 검증한다. 오류 원문과 사유·대상, expected/valid/pending 후보 ID, 검토 시점 후보 해시를 기존 unit 출력에 저장한다.
- 관계 누락·중복·잘못된 인용/판정, 계층 양방향 누락·중복을 미검수로 남긴다. 전역 쟁점 참조 중복, JSON 전체 오류, 공통 근거 범위 위반은 호출 전체 실패를 유지한다.
- `finish`, `revise`, A3 변환에서 동일한 유효 후보 검토 정보를 사용한다. 호출 저장 성공과 후보별 검수 완료를 구분하고, 오류 대상은 run partial 및 A3 deferred/수락 불가로 남긴다. 전체 Critic 실패도 새 결과의 pending 목록으로 A3까지 전달한다.
- 오류 판정·쟁점에서 수정/근거 요청을 파생하지 않으며 잘못된 누락 제안은 복구 큐에 넣지 않는다. 수정 후 후보에는 이전 내용에 대한 판정을 붙이지 않는다. A3의 기존 명시적 사람 수정 경로와 별도 근거·구조 검사는 유지한다.
- 선택한 정·반례 구간을 A3 계층·쟁점에도 보존한다. 전체 부모 블록으로 넓혀 저장하지 않는다.
- 같은 기존 대상의 추가 근거로 합쳐진 관측들도 각 record의 후보 ID별로 검수 유효성을 확인한다. 다른 Critic이 각각 검수한 정상 판단과 해당 묶음의 전역 쟁점은 보존하고, 관련 없는 묶음의 전역 쟁점은 붙이지 않는다.
- recipe는 `discovery-a2-v16`. 재개 시 성공 unit의 원래 참조 범위를 유지해 입력 해시·결과·오류를 재사용한다. 기존 저장 결과/원장은 변경하지 않는다.

## 실제 확인

```text
Python 3.11.9
python -m pytest app/tests/unit/test_knowledge_discovery_segments.py app/tests/unit/test_knowledge_discovery_analysis.py app/tests/unit/test_knowledge_ontology_changes.py app/tests/unit/test_knowledge_ontology_consumer_impact.py -q --tb=short
161 passed in 17.13s
git diff --check: 통과
```

- 위 161개 확인 후 실행 전문가가 지적한 병합 관측의 정상 판단 소실 경계를 수정했다. 최종 변경에서 해당 회귀와 혼합/수정/전체 실패 경로만 다시 확인했다.

```text
python -m pytest app/tests/unit/test_knowledge_ontology_changes.py app/tests/unit/test_knowledge_discovery_analysis.py -k 'merged_evidence_only or mixed_critic or revision_corrects or common_envelope' -q --tb=short
13 passed, 123 deselected in 3.16s
```

- 합성 혼합 응답 7가지: 잘못된 quote, 관계 누락/중복, 잘못된 judgment, 미제공 후보 ID, 계층 방향 누락/중복.
- 정상 관계 판단 보존과 의존 유형을 포함한 수락 가능성 유지, 오류 대상 pending, run partial, 오류발 수정/근거 요청 없음, 재개 시 추가 모델 호출 없음, A3 오류 표시·수락 거절까지 확인했다.
- 여러 focus/shared 구간과 중복 문자열의 정확한 부모 위치, 다른 실행/호출 참조 거절, ref/legacy quote 충돌, 계층·쟁점 반례 span 보존을 확인했다.
- 수정 이력의 전후 ID는 유지하되 수정 전 Critic 판정은 재사용하지 않으며 수정 후보를 A3에서 미검수로 유지하는 경계를 확인했다.
- 기존 입력 고정/재개·API 응답·legacy quote 및 A3 소비자 영향 테스트를 함께 통과했다.
- C2 고정 설정 SHA256: `248b2475d03473f36e4f92030e2402a7a72f26e71c77a6856dc5e130f7533bd3` (D1과 동일).

## 한계와 다음 작업

- 결정적 모델 대역을 사용한 기능 회귀 결과다. 새 실제 LLM 호출, 원래 C2 결과 재평가, 정확도 상승·수락 후보 증가·사람 작업시간 개선은 측정하지 않았다. 기존 8개 후보의 품질 판정을 변경하는 결과가 아니다.
- 구간 선택의 위치 정확성과 해당 구간이 주장/조건을 의미상 지지하는지는 별개다. 실제 의미 품질 비교는 #539에서 고정 기준으로 확인한다.
- Windows 실기·전체 민원 평가·새 검수 UI는 이번 확인 범위가 아니다.
- 다음 #537은 원문 근거 성격과 유형 연결 상태를 유지하면서 역할/대상 타입 설계를 보완한다. #538 이후 #539 비교를 수행한다.
- 현재 사용자 결정이 필요한 사항 없음.
