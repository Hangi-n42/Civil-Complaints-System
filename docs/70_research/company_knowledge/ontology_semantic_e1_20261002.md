# E1 원관측 보존과 정확 일치 대표 후보 — 2026-10-02

## 목적과 구현 경계

- [#540](https://github.com/Hangi-n42/Civil-Complaints-System/issues/540): 매 관측의 새 UUID 때문에 정확히 같은 제안도 후속 분석·검수에서 반복되는 경계를 보완한다. 의미 중복 전체를 자동 동치 처리하는 작업은 아니다.
- 기준 `54dcb5b15c68b76f6e8087040862ca2c5c1bef7a`, 브랜치 `feature/ontology-semantic-improvements`. Ponytail에 따라 기존 run JSON·SQLite·직렬 실행기와 `deepcopy`·기존 digest를 사용했다. 새 저장소·모델 역할·의존성은 없다.
- 새 레시피 `candidate_version=a2-candidates-v1`, 프롬프트 버전 `discovery-a2-v20`에서만 적용한다. 기존 저장 실행은 재작성하지 않으며 레시피가 다른 실행의 재개도 허용하지 않는다.
- `discovery_candidates.py`가 원관측 ID→대표 후보 ID와 발견 unit/group을 별도 등록한다. 성공 원관측·원관계·unit의 ID/output/input_hash를 유지하고 처음 등록된 대표 ID를 재개에서도 유지한다.
- 정확 일치 키는 유효한 source version/parse/block/span/quote, 이름·종류·정의·조건·예외·시점·CQ/범위·근거 성격·설계 출처를 포함한다. 분류 이유·추상화 수준·검토 신호·설계 이유도 같아야 한다. 근거 오류·범위 밖·근거 없는 후보는 재사용하지 않는다. 기존 복구용 meaning_signature는 이 키로 사용하지 않는다.
- Relation 입력→lookup/복구 입력→assemble→Builder/Critic→finish→A3에 대표 뷰를 연결한다. 관계 양 끝점·계층·alignment·설계 연결의 계약상 ID 필드만 해석한다. 문자열 전체나 원관계 사본을 치환하지 않는다. 대표 연결 후 자기 계층은 검증 오류로 남긴다.
- A3는 원관측별 id_mapping과 발견 이력을 보존한다. 승인 기준의 alignment와 사람 검수 경계는 유지하며 정본을 자동 병합하지 않는다. 서로 다른 대응 판단도 자동 단일화하지 않는다.
- 대표 후보의 주 생성 근거가 사용 중단되면 다른 발견으로 조용히 대체하지 않는다. 수정된 대표 후보에는 수정 전 정의의 새 발견을 추가 연결하지 않는다.
- Critic fingerprint는 대표 뷰를 대상으로 하며 원관측 대상의 과거 판정은 재사용하지 않는다. 발견 이력은 뷰와 분리하여 같은 관측의 추가 발견이 의미 fingerprint를 바꾸지 않게 했다.

## E6 사전 고정

- 제품 코드 변경 전 `configs/knowledge/quality_20261001/semantic_completion_e6_v1.json`에 기존 D5 C2/current 기준선·입력 원장·모델 digest·의미 판정 기준·예산·비교 절차를 고정했다.
- 설정 SHA-256: `0c1cccdedb2cb7a2b3ce905c08c85529f5bb1ff1a403d070ae6380cd6379faa3`. 구현 후에도 동일함을 확인했다.
- 실제 D5 기준 실행 코드는 `dc4ad67147a6f9dbf464e54ad61c802a8e656b71`이며 문서 커밋 54dcb5b와 구분한다. 기준 runtime 27파일 해시, 원장·출력 해시를 보존했다.
- C2 5호출/1,800초, current 24호출/1,800초와 기존 검색·라운드·수정 상한을 유지한다. E6에서 C2 1회 후 사전 조건을 충족하는 경우만 current 1회를 수행한다. 기준선 재생성이나 성공할 때까지 반복하지 않는다.
- E1의 실제 모델 생성 호출은 **0회**다. 모델 설치 digest 확인용 `/api/tags` 조회는 추론 호출이 아니다. 실제 참가자 0명, 사람 총 시간 null을 유지한다.

## 확인 결과

- Python 3.11.9, 후보 동일성·A2 분석/복구·A3 변경 모델 관련 **179 passed (16.89초)**. 실행 명령:

```sh
python -m pytest app/tests/unit/test_knowledge_discovery_candidates.py app/tests/unit/test_knowledge_discovery_analysis.py app/tests/unit/test_knowledge_discovery_recovery.py app/tests/unit/test_knowledge_ontology_changes.py -q --disable-warnings --maxfail=3
```

- 합성 원관측 3개→대표 2개, 반복 묶음의 원관측 6개→대표 2개를 확인했다. Relation/Builder/Critic 입력과 A3 유형 2개·관계 끝점이 대표 ID로 연결된다. 원관측·unit은 보존되고 재개 시 모델 대역 추가 호출 0회다. 이는 실제 모델 생성 품질 측정이 아니다.
- 다른 근거 버전/parse/block/span/quote, 종류·정의·조건·예외·시점·범위·근거 성격은 합치지 않는다. 과거 fingerprint 재사용 차단, 발견 추가 시 fingerprint 유지, 대표 근거 중단, 수정 후 이전 정의의 재연결 차단도 확인했다.
- 회귀 중 수정 후보의 근거 오류가 검수 대기 집계에서 빠지는 경계를 수정했다. 대표 뷰를 상속한 설계 관계의 새 끝점도 다시 해석하며, fingerprint가 없는 과거 판정은 새 뷰의 완료로 계산하지 않는다. 기존 비교 후보 수정 금지 테스트는 유효한 새 fingerprint를 제공하도록 맞췄다.

## 저장 D5 출력 재조립

- 원본 result.json을 깊은 복사하고 DB는 SQLite 읽기 전용으로 열었다. 새 추론·게시·승인·DB 쓰기 없이 register/assemble/finish/A3 변환을 검사했다. 기존 출력의 새 코드 재조립이며 새 모델 평가나 기존 실행 마이그레이션이 아니다.

| 저장 사례 | 원관측 | 대표 관측 | 정확 일치로 접힌 수 | 최초 종합 주후보/묶음 | A3 구성 |
|---|---:|---:|---:|---|---|
| D5 C2 current_fixed | 6 | 6 | **0** | 9/1 → 9/1 | 유형 4·관계 4 |
| D5 current_changed | 31 | 31 | **0** | 45/14 → 45/14 | 유형 27·관계 19·계층 3 |

- current의 범위 밖 관측을 제외한 최종 관측은 27개다. 기존 의미 검토의 동일 다섯 유형 add 22개, 중복 추가분 **17개가 그대로 남는다**. 정확 동일성 경로의 코드 완료와 이 17개의 의미 중복 해결을 구분한다.
- 저장값의 주요 차이: 공공주택 5개·공공분양 5개는 정의/조건/근거 성격과 span/quote 2종, 공공임대 7개는 이에 설계 출처·이유와 span/quote 3종, 건설임대 3개는 정의/근거 성격·설계 출처와 span/quote 2종, 매입임대 2개는 정의/조건과 span/quote 2종이 다르다. 각 유형 안의 source version/parse/block은 같아도 정확 일치 키 전체는 다르다. 분류 이유·추상화 수준 차이도 보존했다. 수치를 줄이려고 일치 기준을 완화하지 않았다.
- 새 뷰에는 기존 Critic fingerprint가 유효하지 않으므로 재조립 A3 후보 C2 8개/current 49개를 모두 보류했다. 이 보류는 새 검수가 필요하다는 계약 결과이며 새 모델 품질 하락/상승 수치가 아니다. 원본의 기존 판정은 변경하지 않았다.
- 두 사례의 원관측/원관계·분석 unit 전체 해시·원본 result/DB 해시가 유지됐다. 같은 복사본을 다시 finish해도 대표 대응과 최종 후보가 동일했다. 실제 재개에서 성공 호출을 재사용하는 경로는 위 합성 통합 테스트에서 별도로 확인했다.
- 로컬 진단: `data/knowledge/semantic_e1_20261002/reconstruct.py`, `reconstruction.json`. 원문·DB·전체 출력과 함께 Git 커밋에서 제외한다.

## 다음 작업과 남은 범위

- E1은 정확 일치 관측 재사용과 원장/검수 경계 구현까지다. 의미 중복 17개, 실제 목적어·조건/예외 완결, Builder의 기존 유형 재사용/연결, Critic의 지역 공백 오판, 예산 예약 개선은 미완료다. 전체 온톨로지·지식 그래프 품질이 승인 수준이라는 결론을 내리지 않는다.
- E2/E3는 기존 유형에 근거를 갖춘 재사용/신규/보류와 관계 연결을 보완하고, 실제 효과는 사전 고정한 E6에서 확인한다. 다음 단계는 계획 세션의 지시 후 진행한다.
- 전체 민원·다중 모델·Windows 실기·실제 사람 효용 시험은 수행하지 않았다. 새 UI 시험·정본 활성화·PR 병합·배포도 하지 않았다. 상위 #534/#539의 전체 품질 문제는 미완료로 유지한다.
- 현재 사용자 결정이 필요한 사항 없음.
