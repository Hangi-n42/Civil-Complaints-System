# G1 원문 관계 진단 — 2026-10-02

**C 채택.** 후보 정보를 제거한 B만으로는 목적어 오류가 해결되지 않았다. B의 원문 입력에 사전 고정한 행위 분해·방향 문단을 적용한 C는 독립 AI 의미 검수에서 current.C2 필수 의미를 충족했다. 이 결과는 고정 원문·상류 결과를 사용한 Relation 단독 각1회 진단이며 전체 C2 실행, 일반 성능 향상 또는 특정 문장의 인과 증명이 아니다.

## 선택 이유와 고정 범위

- #553. 제품 기준 `fdf01ca5436baed7e2cd6f3d8bce129f75256948`/v31, 실행 HEAD `17a62cb`. 제품 코드를 바꾸기 전에 `semantic_relation_g1_v1.json`을 커밋·푸시했다.
- 동결 SHA256 `80efb6718864eafd6022a95247f38e28f68ed1ea2d979c8e1068d5ffd04241c5`. 기존 F5 원문과 Concept 상류 결과를 고정하고 현행 Relation 스키마를 사용했다. A prompt는 저장 F5와 정확히 같다.
- B는 reviewed_base/unapproved_observations/comparison_terms/previous_observations 후보 정보만 제외했다. 원문·도구 원문·항 범위·CQ·source_ref는 유지했다. C는 B payload에서 사전 고정 문단 하나만 교체했다. 정답 예시·assessor는 생성 입력에 넣지 않았다.
- 세 안의 schema SHA256 `369ae8c496d4c7134e87e15a5f45fbebc55baafed28ca90825cfc07f9bf783c4` 동일. Gemma/Qwen 설치 digest, temperature0/think=false/ctx32768/output4096/input12000/실제timeout300초 유지. 새 조건·문구 반복 탐색과 A/B 재호출 없음.

| 진단 | 입력자 | 실제 HTTP | 모델초 | 경과초 | 저장 관계 | 의미 결과 |
|---|---:|---:|---:|---:|---:|---|
| A 현행 | 5,704 | 1 | 69.066 | 69.124 | 4 | ①② 목적어가 국민임대주택, 방향4개 unresolved |
| B 후보 정보 제외 | 5,248 | 1 | 52.916 | 52.986 | 4 | 동일 목적어 오류·방향 미해결로 탈락 |
| C 사전 문단 교체 | 5,349 | 1 | 67.814 | 67.883 | 4 | 독립 의미 검수 통과, 채택 |

- 총3HTTP, 모델189.796초/경과189.993초. 시간 차이를 동등 품질의 효율 개선으로 환산하지 않는다.
- C는 ①② 행위 대상인 입주자, 선정 의무/허용, 잔여주택 전제·일부 완화 OR 선착순·예외 우선성을 보존했다. ③ 장관/시도지사 권한과 LH/지자체·지방공사 공급 분기, 지역 실정, 제1·2항에도 불구 조건, 지방공사 정의를 보존했다. 방향4개 subject_to_object와 모든 원문 인용이 확인됐다.
- 유형 연결 전의 unresolved_endpoints나 미제공 외부 별표·정의·시점 자체는 raw 의미 탈락 사유로 사용하지 않았다. 원문 후보의 의미 통과와 Builder의 실제 설계·연결 성공은 별개다.
- 세 출력 모두 source/version/parse/block/span/quote/locator 검사 오류0. 원 F5 실행·DB·결과·호출 기록·동결 및 실행 중 제품 코드 해시를 보존했다. D5/E6/F5를 재실행하거나 실패를 새 코드 성공으로 바꾸지 않았다.

## 증거와 다음 작업

- `data/knowledge/semantic_g1_20261002/{A,B,C}_input.json`: 사전 입력·schema·서버 문맥.
- `{A,B,C}/result.json`: raw_output·정규화 결과·호출 기록, 각 폴더의 knowledge.db: 별도 저장 사본. `abc_checks.json`: 근거 검사·비용·출력/DB 해시. 원본·DB·전체 모델 출력은 커밋하지 않는다.
- 조율 세션의 독립 의미 전문가는 C 필수 의미 통과를 확인했고 평가 전문가는 B의 사전 기준 미달을 확인했다. C를 G2에 반영하고 G3 역할별 복구 입력을 정리한 뒤, 새 동결의 전체 C2에서 Builder·Critic·생성 후보만의 preview까지 확인한다.
- 이번 시점 G2/G3 제품 변경0, 전체 C2/current 실행0, 실제 사람0명/시간null/효용미측정. 현재 사용자 결정이 필요한 사항 없음.
