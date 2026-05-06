# Task 05 - 검색 평가셋(v1) 사람 검토 체크리스트

## 목적

`data/eval/retrieval/v1` 평가셋이 자동 변환만으로 생길 수 있는 편향을 줄이고, 실제 검색 품질 비교에 쓸 수 있도록 최소 인력 검토 기준을 정한다.

## 검토 대상 파일

- `data/eval/retrieval/v1/queries.jsonl`
- `data/eval/retrieval/v1/qrels.tsv`
- `data/eval/retrieval/v1/smoke/queries.jsonl`
- `data/eval/retrieval/v1/smoke/qrels.tsv`
- `data/eval/retrieval/v1/manifest.json`

## 1차 샘플 검토 (필수)

- 전체 query 중 최소 50건을 랜덤으로 추출해 검토한다.
- 각 query마다 qrels 상위 문서 3개를 사람이 확인한다.
- relevance 기준은 아래를 고정 사용한다.
  - 3: 질문에 직접 답할 수 있는 핵심 근거
  - 2: 답변에 중요하지만 단독으로는 부족한 근거
  - 1: 주제/절차상 약하게 관련
  - 0: 무관 또는 오답 유도 가능

## 2차 편향 점검 (필수)

- lexical overlap이 과도한 query 비중이 높은지 확인한다.
- 동일/유사 문서만 정답으로 반복 지정되는지 확인한다.
- dense 검색기가 의미적으로 적합한 문서를 찾았는데 qrels에 없는 false negative 사례를 기록한다.

## 3차 slice 균형 점검 (권장)

- `topic_type`, `complexity_level`, `risk_level`별 query 분포를 확인한다.
- 특정 slice가 과소대표되면 후보를 추가 라벨링한다.
- high-risk 또는 complexity high slice는 최소 표본 수를 별도 확보한다.

## 승인 기준

- 검토 로그에서 치명 라벨 오류(명백한 relevance 오기입) 비율이 5% 미만
- false negative 후보가 확인되면 qrels 보강 계획을 이슈로 분리
- smoke set(50건) 기준 평가 스크립트 실행 성공

## 후속 이슈 권장

- BM25 + dense + hybrid 결과를 풀링한 qrels 보강
- 사람 검토 로그를 표준 JSONL 포맷으로 저장
- 라벨 불일치 케이스에 대한 adjudication 규칙 문서화