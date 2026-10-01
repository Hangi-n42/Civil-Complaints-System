# A6 제한 개발 평가와 검수자 시험 준비

- 대상: #525, `자율 탐색 기반 온톨로지 초안 구축 (A1~A6)` 마일스톤 14.
- 분기: A5 검수 커밋 `0124110`을 포함한 원격 main `4979f5b91663cd20f9d7496fddc6fa2bdd538cb7`에서 `feature/a6-ontology-evaluation` 생성.
- 기존 A1 고정 입력·직렬 실행기·K3/A2 모델 호출·A3 결정·원문 API를 사용한다. 별도 평가 플랫폼·모델·의존성을 추가하지 않는다.
- 원본 작업트리·기존 DB·원문은 보존하고 새 평가 디렉터리에만 원장을 만든다. DB·원문·전체 모델 출력은 커밋하지 않는다.

## 동결 범위와 해석

최초 동결은 **2026-10-01 03:05:04 UTC**, 최초 모델 호출은 03:05:05 UTC 이후다. `freeze.initial.json`과 커밋 `7ea0715`에 그 조건을 보존했다. 실제로 발견한 빈 enum HTTP 400을 `bb31c55`에서 수정한 뒤 03:19:04 UTC에 `freeze.json`으로 다시 고정했다. 두 동결에서 바뀐 실행 파일은 `app/knowledge/discovery_analysis.py` 하나다. 입력·판정 기준·모델·예산은 동일하며 첫 실패를 별도 보존한다.

코드·manifest·생성 조건·판정표·검수 카드는 SHA-256으로 묶었다. 생성 실행기는 `generation.json`만 모델 입력으로 사용한다. `assessor.json`과 `reviewer_cards.json`은 바이트 해시 확인 외에는 생성기가 해석하지 않는다.

| 사례 | 입력 전체 | 기준 |
|---|---|---|
| manual_current | 법 제2조·시행규칙 제15조, 6블록 | 기존 수동 자료 선택 K3 |
| auto_current | 같은 6블록·C1/C2 | A2, 법→규칙 순서 |
| auto_reverse | 같은 6블록·C1/C2 | A2, 규칙→법 순서 |
| contrast | 위 원문 + LH 5년임대 공식설명, 19블록 | current의 검수한 최소 기준 + X1 |
| history0 | 2020-08-05 시행령 제2조, 3블록 | 빈 별도 역사 계보 |
| history1 | 2020-09-08 제2조 추가, 누적 6블록 | 직전 단계의 검수한 최소 기준 |
| history2 | 2020-10-19 제2조·제37조 추가, 누적 12블록 | 직전 단계의 검수한 최소 기준 |

- 기존 K9 12과제와 K6 출력은 자료·질문·설정이 다르고 사전 노출되었으므로 비교 수치로 재사용하지 않는다. 기존 원문·원장·실행 지표·원문 검수 원칙과 덮어쓰기 방지 방식을 재사용했다. 계획에만 있던 4/4/2 카드는 이번에 고정했다.
- 이 자료와 질문은 개발자/AI에 사전 노출된 **개발 평가**다. 독립 비노출 검증이나 현업 효용 입증이 아니다.
- 동일 Gemma/Qwen 태그와 digest, `temperature=0`, `think=false`, context 32,768/output 4,096을 적용한다. 수동 단계 토큰 한도는 평가 프로세스에서만 맞춘다. 기존 경로의 역할·후보 계약·문맥 조립 차이는 남으므로 자율성만의 인과 효과로 해석하지 않는다.
- 자율 정순/역순 모두 `profile.survey`의 frontier 우선순위를 지정 순서로 고정하는 평가용 개입이다. Scout 자체 선택 순서 비교가 아니다. 실제 시도 단위의 `primary_order`와 원문·도구 문맥 `provided_set`을 구분한다. UUID 정렬을 처리 순서로 세지 않는다. 반복 1회씩이므로 확률적 변동과 순서 효과를 분리할 수 없다.
- 실행별 최대 20호출·모델 대기 1,800초·호출당 300초, 검색 2회·추가 회차 0·수정 1회. 소진·실패 결과를 남기며 자동 재시도/확대하지 않는다. 상위 호출 시도와 실제 HTTP 생성 시도를 별도로 기록한다.
- CSV 실개체·별표4·건축법 별표는 이번 작은 묶음에 없다. 구조 표현, 실제 자료 존재, 조회 결과의 조건·예외·근거 일치를 각각 판정한다. 조회 가능한 코드와 인용 존재를 답변 정확도로 환산하지 않는다.
- 현재/대비와 역사 계보를 분리한다. 역사 0/1도 제2조에서 확인되는 기존주택 매입·지원·공급 조건은 평가하되, 아직 없는 제37조 세부를 정답으로 요구하지 않는다.

## 재현

Python 3.11.9와 기존 설치 의존성, 동결된 두 로컬 모델, manifest 해시와 일치하는 허용 원문이 필요하다. `--input-root`는 원문을 읽기만 한다. 아래 `<study>`는 새 출력 경로, `<source-root>`는 허용 파일이 있는 저장소 루트다. Mac 전용 경로를 코드에 넣지 않았다.

```sh
python scripts/run_knowledge_a6.py init --output <study>
python scripts/run_knowledge_a6.py run --case manual_current --output <study> --input-root <source-root>
python scripts/run_knowledge_a6.py run --case auto_current --output <study> --input-root <source-root>
python scripts/inspect_knowledge_a6.py --study <study> --case auto_current --output <study>/current-inspect.json
```

생성 실패도 해당 `<case>.json`과 `.calls.jsonl`에 보존한다. `.started.json`이 있으면 같은 사례를 덮어쓰지 않는다. 모델 출력은 재현 시 달라질 수 있다. 출력 파일만으로 참가자·효용 결과를 만들지 않는다.

`inspect_knowledge_a6.py`는 기존 API를 FastAPI TestClient로 호출하여 변경안·preview·고정 read/search·근거 위치를 저장한다. 원문 상태/포인터가 변하지 않았는지도 확인한다. 실행 중인 원장이면 거절한다. 결정 적용 전에 출력 파일을 배타적으로 예약하고 시작 기록을 남기므로, 쓰기 불가능한 경로는 원장을 바꾸기 전에 실패한다. 브라우저 상호작용 시험을 대신했다는 뜻은 아니다.

원문 대조 후 명시적인 A3 `DecisionRequest` JSON을 작성한다. `actor=a6-ai-operator`, 실제 `expected_changeset_revision`/`expected_ontology_head_id`, 후보별 결정·이유를 기재한다. 다음 명령은 그 요청을 저장된 API 경로로 적용하고 다시 조회한다. 자동 수락/의미 채점은 하지 않는다.

자동 변경 후보가 없고 증분 연결에 최소 기준이 필요하면 A3 `AddOntologyChanges` 요청을 별도 작성하여 `--additions <request.json>`으로 보완한다. `evidence_refs`의 전체 ID·버전·parse·locator·인용·문자 span을 보존한다. 추가·편집·보류·수락 요청은 각각 현재 revision으로 분리하고 최초 생성 결과를 덮지 않는다.

```sh
python scripts/inspect_knowledge_a6.py --study <study> --case auto_current --decisions <decisions.json> --output <study>/current-decided.json
python scripts/run_knowledge_a6.py run --case auto_reverse --output <study> --input-root <source-root>
python scripts/run_knowledge_a6.py run --case contrast --base <current-reviewed-version> --output <study> --input-root <source-root>
python scripts/run_knowledge_a6.py run --case history0 --output <study> --input-root <source-root>
# history0 원문 검수·API 결정 후 다음 단계로 진행
python scripts/run_knowledge_a6.py run --case history1 --base <history0-reviewed-version> --output <study> --input-root <source-root>
# history1 원문 검수·API 결정 후 다음 단계로 진행
python scripts/run_knowledge_a6.py run --case history2 --base <history1-reviewed-version> --output <study> --input-root <source-root>
```

사람 대신 AI가 검수한 최소 기준은 증분 연결 확인용이며 사람 승인/현업 승인으로 표시하지 않는다. 생성 실패를 보완한 경우 최초 생성 성과와 보완량을 분리한다. 단계별 이전 실행과 base version의 출처를 검사한다.

## 실제 사람 시험 준비 — 미수행

```sh
python scripts/prepare_knowledge_a6_review.py prepare --study <study> --output <new-review-directory>
python scripts/prepare_knowledge_a6_review.py score --record <record.json> --adjudication <independent-adjudication.json> --output <new-score.json>
```

- 완료된 격리 원장의 고정 블록·근거 ID·위치로 카드 원문을 묶는다. 준비 도구는 원장을 읽기 전용으로 열고, 정답/판정 이유를 참가자 파일에서 제외한다. 오류 카드를 운영 원장에 삽입하지 않는다.
- A묶음은 정상 2·오류 2·미연결 요구 1, B묶음은 정상 2·오류 2·잘못 충족 표시한 요구 1. 난이도 동등성은 미검증이다.
- P1: baseline A→assisted B, P2: assisted A→baseline B. 같은 카드를 같은 사람이 재학습하지 않도록 교차 배치한다. 준비 설명 뒤 실제 시각·조건·도구·결정/사유·수정문·열람/탐색 횟수를 기록한다. 실제 1명이면 사용성 확인으로만 보고한다.
- 비교군도 원문·검색·diff·메타데이터·요약·수동 관계표를 사용할 수 있다. K9의 강한 B1 원칙을 유지하되 K9 전체 평가를 실행하지 않는다.
- 제공 HTML은 동일 카드/원문의 **오프라인 모의 도구**다. assisted의 근거 위치와 요구 연결 강조는 실제 A4 화면 시험과 다르다. 실제 A4 UI 효과를 주장하려면 같은 카드를 격리 UI에 배치하고 별도로 사람 시험해야 한다.
- 참가자 기록과 독립 의미 판정을 분리한다. 오류 발견은 판정자의 `discovery_correct`까지 있어야 집계한다. 올바른 수정·오류 기각·오류 보류, 잘못 수정 후 승인, 최종 핵심 오류, 미연결 누락과 잘못된 충족 주장을 별도 집계한다. 정상 후보의 수정/거절 건수와 실제 훼손도 분리한다. 의미를 유지한 정상 수정은 훼손으로 세지 않는다.
- 실제 사람 준비·CQ·검수·수정 시간은 측정 전 `null`. AI/도구 시간·모델 대기·총 경과와 합쳐 사람 비용이나 절감률을 만들지 않는다. AI 기록은 사람 시간 필드로 집계하지 않는다.

## 확인 결과

실제 실행·의미 판정·실패·검수 보완·남은 범위는 [A6 결과 보고](../70_research/company_knowledge/a6_evaluation_20261001.md)에 기록한다. 자동 확인은 A6 도구와 기존 원장 연결 경계에 한정한다. 전체 민원 테스트, K9 12과제, 다중 모델 비교, Windows 실기는 완료 조건에 추가하지 않는다.
