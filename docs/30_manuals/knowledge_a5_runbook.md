# A5 검토된 온톨로지의 LH 추출·활성화 연결

- 대상: [#524](https://github.com/Hangi-n42/Civil-Complaints-System/issues/524), 마일스톤 14. 기준 main `5f66466ed107ac234669dfb1e5d35b8ec0896121`에서 `feature/a5-ontology-consumer-integration` 분기.
- 기존 SQLite·직렬 실행기·LH 전용 매핑·LinkML SchemaView·K4 검수·K5 스냅샷을 연결한다. 새 DB/큐/프레임워크/의존성 없음. A3의 원자적 revision/head 승인 트랜잭션을 재사용한다.
- 온톨로지 수락, 필드 의미 대응, 개별 사실 수락, 지식 버전 활성화는 서로 다른 결정이다. 과거 사실·개체 유형·스냅샷을 새 정의로 덮어쓰지 않는다.

## 구현과 소비 계약

- `ontology_consumer.py`: v1 조회 유지, v2 저장 YAML의 `class_slots`/`induced_slot`/`class_ancestors`로 현재 유효 정의 해석. 상속 주체·관계 대상, 필수값, enum, 폐기 제외를 추출·사실 검수·스냅샷·기존 검색에 공통 적용한다. 클래스별 서로 다른 값 제약·복합 제약·다중값 속성은 미지원 표시한다.
- `ontology_canonical.py`: A2 파생 입력 의존 블록을 불변 정본 메타데이터에 보존한다. 원문·반례·파생 근거는 입력·사실 수락·스냅샷 생성과 조회/활성화에서 현재 K5 사용 상태를 적용한다. 전체 유효 온톨로지의 근거를 보수적으로 검사하므로 사용하지 않은 정의의 근거 제한도 새 소비를 막을 수 있다.
- LH 공식 개체는 기존 `namespace + official_id`와 서버 ID를 유지한다. 실행의 `consumer_contract.role_targets`가 선택 온톨로지의 유형을 해석하며 전역 `entities.concept_id`를 변경하지 않는다.
- 기존 ID와 의미 정의가 같은 LH 역할은 기존 `k4_lh_mapping.json`을 재사용한다. 새 ID·바뀐 의미는 검토자가 명시한 역할→유효 target ID 대응만 사용한다. 구조/자료형 검사는 의미 정확성의 승인자가 아니다. 이름 유사도 자동 대응은 없다.
- 대응 결정은 기존 decisions 원장에 버전별로 추가 저장한다. ontology hash, mapping review ID, LH profile 버전과 대응을 실행에 고정한다. 후속 대응 수정은 기존 실행을 바꾸지 않는다. v1은 기존 전용 매핑을 유지하고 새 대응 검토는 v2에서 수행한다.
- 실행은 `block_ids`와 `predicate_ids`를 함께 고정해 필요한 자료/필드만 추출한다. 미선택·미대응 필드는 coverage에 남긴다. 재시도는 고정 계약과 성공 단위를 재사용하며 사용 중단 상태를 다시 확인한다.
- 사용한 기존 별칭의 근거 의존을 새 연결·스냅샷에도 보존한다. v2 별칭 재사용은 동일 온톨로지와 현재 사용 가능한 검토 연결로 제한한다.
- 미연결 참고는 기존 별칭/모호함/새 하위 유형/새 개념/파싱 오류/근거 부족으로 검토·기록한다. UNKNOWN이나 미연결만으로 새 개념을 생성하지 않는다.
- v2 K5는 동일 온톨로지·동일 고정 대응의 수락 사실만 받는다. 선택 개체의 필수 유효 슬롯을 검사하며 다른 버전의 과거 사실을 자동 혼합하지 않는다. `run_scopes`, `consumer_contract`, `vocabulary_registry`를 조회할 수 있다.
- 기존 Local 검색의 사실 표시와 모델 입력도 같은 버전의 정의를 읽는다. 표시명·별칭은 새 버전에서 갱신되며 과거 스냅샷의 표현은 보존한다. 검색 알고리즘·LLM 답변 정책 변경은 없다.

## 변경 유형과 직접 의존 처리

| `consumer_impact.action` | 처리 |
|---|---|
| `display_refresh` | 같은 의미의 이름 변경·조건 없는 별칭. ID 유지, 새 정본의 표시·검색 참조 적용 |
| `partial_extract` | 속성/관계 추가. 새 필수값 호환성 표시, 기존 사실 보존, 선택 범위 새 추출 |
| `semantic_review` | 정의·조건·범위·필수 제약 변경. 직접 영향 사실/대응 재검토 |
| `review_dependencies` | 병합/폐기. 최종 정본 ID 대응과 직접 참조 검토 또는 보류 |

- 의미/병합/폐기 변경에 직접 소비자가 있으면 수락 결정에 `consumer_action: "review_required"`를 명시한다. 서버가 계산한 직접 영향 사실만 기존 availability 원장의 `needs_review`로 바꾸고 blocked는 유지한다. actor/reason·변경 fingerprint·처리한 참조 ID·보존한 과거 실행/스냅샷을 결정에 저장한다.
- 현재 정의 내부의 미해결 참조는 이 옵션으로 해제되지 않는다. 관련 정의를 함께 수정/폐기하거나 해당 변경을 보류해야 한다. 사유 없는 일괄 우회·과거 사실의 새 버전 자동 수락은 없다.
- 조건·시점·부정이 붙은 별칭은 조건 없는 LinkML 동의어로 투영할 수 없어 명시적으로 수락을 차단한다. 의미 범위를 무시한 표기 갱신은 지원하지 않는다.
- K8 간접 영향 탐색이나 전체 재추출은 포함하지 않는다.

## API와 화면

기존 `/api/v1/knowledge`와 성공/오류 봉투를 유지한다.

1. 온톨로지 초안에서 A3 수락. revision/head가 오래되면 `409`. 의미 변경의 직접 영향은 화면의 재검토 처리 선택과 사유로 기록한다.
2. 개체·사실에서 reviewed 온톨로지 선택. `GET /ontologies/{id}/consumer`가 유효 정의·미지원·LH 대응·현재 검토 ID/head·어휘 registry를 반환한다.
3. 새 대응이 필요하면 정의·포함/제외를 대조하고 `POST /ontologies/{id}/consumer`에 `actor`, `reason`, `expected_review_id`, `expected_ontology_head_id`, `target_ids`를 전달한다. 오래된 대응/head는 `409`, 미지원 대응은 `422`다. 빈 대응은 보류다.
4. 기존 `POST /runs`의 `kind=extract`에 자료/등록부/온톨로지를 지정한다. 선택적인 `predicate_ids`는 적어도 한 개의 유효 지원 슬롯이어야 한다. `block_ids`는 기존 자료 부분 선택이다. 화면은 자료·표 선택과 속성/관계 부분 선택을 제공한다.
5. 개체·사실 화면에서 연결/사실을 원문과 대조해 수락한다. 근거 중단은 수락을 막고 수정 시에도 미수락 상태를 유지한다. 사실 재수락만으로 기존 `needs_review`를 자동 해제하지 않는다.
6. 지식 버전에서 같은 온톨로지의 수락 항목과 필요한 연결을 선택해 스냅샷 생성 후 별도로 활성화한다. 과거 스냅샷 롤백은 기존처럼 가능하며 현재 사용 제한 항목은 제외한다.

## 확인 결과 — 2026-10-01

- Python 3.11.9/macOS, 변경 경계·기존 K4/K5/Local 검색/API **123 passed**. 새 A5 매핑/저장/영향 테스트와 기존 v1·A3 회귀 포함. 이후 v1 대응 저장 제한 회귀를 추가한 소비 테스트 **9 passed**로 해당 변경을 재확인했다.
- 프런트 관련 **13 passed**, TypeScript·변경 파일 ESLint 통과. 화면 확인은 실제 컴포넌트 정적 출력·요청 계약 검사이며 이번 작업에서 브라우저 상호작용 전체를 재수행하지 않았다.
- 독립 AI 검수: 구현자 두 명의 상대 코드 검수와 작성에 참여하지 않은 세 번째 에이전트의 별도 검수. 반례 의존 누락, 공고 식별자 단독 부분 추출 누락, induced-slot 타입/enum 불일치, 조건부 별칭의 무조건 동의어 투영을 재현하여 수정했다. 수정 경계 재검수에서 추가 중요 결함은 확인되지 않았다. decimal 정규화와 저장 자료형의 불일치도 수정했다.

### PR #532 등록 후 경계 보완

- 조율 세션의 추가 검수에서 두 결함을 임시 DB로 재현했다. 단지 세대수만 선택해도 `panId` 때문에 미대응 공고 역할을 요구했고, 전역 공식 개체 유형의 변경이 다른 유형으로 검토된 사실까지 재검토 상태로 바꿨다.
- 공고 개체 생성은 선택된 유효 지원 슬롯의 주체·관계 대상에 검토된 `LH:notice` 역할이 필요한 경우로 제한한다. 기존 `permits`의 상속 허용 타입을 사용하며 기본 공고 슬롯뿐 아니라 신규 공고 속성·관계도 처리한다. 공고 역할이 보류돼도 단지 속성 부분 추출이 완료되며 미대응 공고를 자동 연결·수락하지 않는다.
- 직접 영향은 연결에 저장된 유형을 우선한다. 연결 정보가 없을 때는 실행에 고정된 의미 대응을 사용하며, v2 미대응 역할을 전역 개체 유형으로 대체하지 않는다. 기존 무계약 원장의 직접 참조는 유지한다.
- 관련 소비·영향·추출 실행 테스트 36건 확인: 첫 실행 35건 통과, 신규 테스트 fixture의 실행 상태 누락을 보정한 뒤 해당 1건 재통과. 새 회귀는 미선택 공고, 공고 슬롯별 추출, 주체/대상 연결, 고정 대응·미대응·레거시 fallback과 과거 스냅샷/블록 불변을 확인한다.
- 두 외부 재현에서도 시작 거절 해소와 별도 유형 사실의 `allowed` 유지 확인. 이 보완의 추가 모델 호출은 0회이며 전체 평가·프런트 재검증·A6는 수행하지 않았다.
- 구현에 참여하지 않은 에이전트가 변경 부분과 외부 재현 두 건을 독립 재검수하고 소비·영향 테스트 29건을 재확인했다. 이 범위에서 추가 중요 결함은 발견되지 않았다.
- 후속 검수에서 두 기본 공고 슬롯만 검사하던 guard가 신규 공고 슬롯의 공식 개체 연결을 누락하는 회귀를 재현했다. 유효 주체/대상 타입 판정으로 보완한 뒤 관련 10건 통과: 신규 속성·관계의 직접/상속 타입, 미대응 공고의 수락 차단, 기존 단지 부분 추출·공고 식별자. 고정 응답 재현에서도 공고 개체 1개·공식 ID 연결·연결/사실 검증 오류 없음 확인. 독립 검수자도 해당 10건과 외부 재현을 확인했으며 추가 중요 결함은 발견하지 못했다. 실제 모델 호출 0회.

```sh
python -m pytest app/tests/unit/test_knowledge_consumer.py app/tests/unit/test_knowledge_a5_store.py app/tests/unit/test_knowledge_ontology_consumer_impact.py app/tests/unit/test_knowledge_ontology_changes.py app/tests/unit/test_knowledge_ontology_schema.py app/tests/unit/test_knowledge_extraction_run.py app/tests/unit/test_knowledge_extraction_quality.py app/tests/unit/test_knowledge_extraction_store.py app/tests/unit/test_knowledge_snapshots.py app/tests/unit/test_knowledge_api.py app/tests/unit/test_knowledge_search.py -q
cd frontend
npx vitest run __tests__/knowledgeReview.test.ts __tests__/knowledgeReviewRender.test.ts __tests__/knowledgeConsumer.test.ts
npx tsc --noEmit --incremental false
npx eslint components/KnowledgeConsumer.tsx components/KnowledgeExtraction.tsx components/KnowledgeDiscoveryReview.tsx lib/knowledgeReview.ts __tests__/knowledgeConsumer.test.ts __tests__/knowledgeReview.test.ts
```

### 저장된 LH 자료의 격리 확인

- 운영 원장을 읽기 전용으로 복사한 사본에서 기존 reviewed LH 정의 `30728ffc…`의 동일 의미 표시명만 `LH 주택단지`로 변경 수락했다. 입력 분석 run은 **수동 통합 fixture**라고 기록했다. A2가 새 의미를 발견하거나 실제 사람이 이를 승인한 결과가 아니다.
- 저장 CSV 버전 `c4df4204…`, C00446의 한 행에서 코드·명칭·세대수만 추출하여 **개체 1·연결 1·사실 3**을 검수·활성화했다. 온톨로지 수락과 스냅샷 생성 직후에는 기존 활성 ID가 유지됐다.
- API 수락→추출→사실 검수→생성→활성화→근거/JSON 재조회 통과. v2 검색 입력 준비·사실 표시·답변 입력 구성도 같은 3개 사실로 확인했다. 모델 답변 생성은 실행하지 않았다.
- 실행 `0f6aa20b3c9642bc9e022e1f097c7464`, 온톨로지 `ab55cf6ac22f4036aa6c96c8c0ca1a11`, 스냅샷 `29311406dade40608512d25b1bd0a4d9`.
- 추가 LLM **0회/0초**, 추출 **0.281초**, 수락부터 활성화·재조회까지 기록한 경로 **1.512초**. 추가 검색 입력 준비 시간은 이 수치에 포함하지 않는다.
- 기존 스냅샷 **5개**와 source version/parse 포인터 불변. 원본 DB의 전후 SHA-256 동일: `31a997cf114bade59e59998f0edf326f1bfcfded8556e74dec09bddbe320d84f`.
- 첫 시도는 예전 K2 전체 블록 근거가 별도 evidence 행 없이 저장된 경계에서 실패했다. 기존 원문 조회의 `_optional` 호환 경로를 A3 검사에도 적용하고 새 사본에서 위 경로를 재확인했다. 실패 사본·성공 사본을 모두 보존했으며 호출을 성공으로 집계하지 않았다.
- 로컬 증적: `data/knowledge/a5_smoke_20261001_retry/{knowledge.db,verification.json,run.json}`. 재현 절차 `/tmp/a5_smoke_retry.py`. 이 경로와 ID는 해당 저장 자료가 있는 로컬 원장에 종속된다. DB·원문·실행 증적은 커밋하지 않는다.

## 남은 범위와 다음 작업

- 실제 신규 개념의 의미 정확성, 현업 사람 검수·효용, LLM 추출 품질, 전체 19파일·12과제·모델 비교·Windows 실기는 확인하지 않았다. 상속·병합·필수값·사용 중단·새 ID 대응은 명시한 합성 fixture로 확인했다.
- A6는 검토 버전/대응 ID, `predicate_ids`/`block_ids`, `consumer_impact`와 decision 이력, snapshot의 `run_scopes`/현재 사용 상태를 고정하여 제한된 비교와 검수 확인에 사용할 수 있다. A6는 별도 지시 후 착수한다.
- 현재 사용자 결정이 필요한 사항 없음.
