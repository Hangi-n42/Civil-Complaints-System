# 자연논리 기반 2-template hard-label·전체 문맥 변형 진단 — 2026-10-09

기준은 `645dfc004abcd58d5144fbf01dbe92e4dd16f9eb`, 연구 이슈는 #625다. 기존 직접 검수·span binding·CAD·NLI 비교는 반복하지 않는다. 후보의 자기 출처 지지 판단을 대체할 수 있는 기전인지 개발 c13/c46/c47/c11로 제한 비교한다. 제품 기본 경로·DB·후보·평가를 변경하지 않는다.

## 원형과 실제 공개 구현

[Zero-NatVer 논문](https://aclanthology.org/2024.findings-emnlp.991/)은 후보를 나누고 원문과 정렬한 뒤, 국소 자연논리 관계의 복수 Yes/No 판단을 집계하고 DFA로 최종 판정을 계산한다. 논문은 관계당 10개 질문과 우도 기반 가중 집계를 사용한다. 정렬 설명의 signal은 가능한 연산을 제한한다. 이 논문의 다국어 평가에는 한국어가 포함되지 않는다.

[공식 코드](https://github.com/marekstrong/Zero-NatVer/tree/e97735004c1568b827a497fac7f4fab03daac883)는 revision `e97735004c1568b827a497fac7f4fab03daac883`을 확인했다. 공개 실행은 Llama3-8B, Hugging Face FP16/CUDA와 직접 logits 접근을 사용한다. chunking은 다음 원문 token과 개행을 비교하여 원문 token을 따르는 제약 생성을 한다. 반면 main의 alignment는 일반 text-generation 후 원문 정리를 사용한다. `natops.py`는 5연산×10질문의 점수를 반환하지만 공개 tree에는 최종 가중집계·DFA 판정 구현이 없다. 따라서 README 실행을 그대로 하는 것만으로 논문의 전체 비교를 재현했다고 할 수 없다.

`llm/generate.py`는 Yes/No 후보의 log total을 비교하고 반환 확률에는 두 첫 token의 정규화 확률을 사용한다. 현재 제품 `ModelClient`는 JSON schema generation과 호출 기록을 제공하며 이 likelihood API나 token-follow logits 제약을 노출하지 않는다. 과거 native 엔진의 전체 분포 기능 확인을 이번 원형 실행 성공으로 재사용하지 않았다.

공식 후처리 `utils.get_alnum_string`은 영문·숫자만 남기는 정규식을 사용하여 한글 정렬 검증에 그대로 적합하지 않다. 저장소의 [LICENSE](https://github.com/marekstrong/Zero-NatVer/blob/e97735004c1568b827a497fac7f4fab03daac883/LICENSE)는 AGPL-3.0이다. 원 코드를 제품에 복사하거나 패키지로 설치하지 않았고, 논문의 연산 원리를 작은 독립 진단 코드로 구현했다. 코드·모델·데이터의 배포 조건은 서로 같다고 가정하지 않는다.

## 이번 변형과 입력 경계

- 자동 분할은 원래 후보 문자열을 공백 포함 token 주소로 제시하고 모델이 연속 구간의 끝을 정한다. 전체 coverage·원래 순서·정확한 한글 인용의 유일성을 사후 검증한다. 원형의 constrained decoding 재현은 아니다.
- 모델이 원문과 후보를 자동 정렬한다. 모든 원문 10개 블록과 기존 부모 관계를 유지한다. 정답에 맞춰 후보를 나누거나 올바른 지역 조건을 대신 선택하지 않는다.
- 각 연산에 신규 한국어 질문 두 개를 고정했다. 연산/질문별 별도 요청에서 유효 pair들을 묶으므로 pair별 독립 표본 실험은 아니다. raw yes/no/unknown과 이유를 모두 저장한다.
- 동일 가중 hard-label 평균이 0.5를 초과할 때, 즉 두 yes일 때 후보 연산으로 사용한다. likelihood·보정 확률·원형의 10-template 가중 집계와 다르다. unknown과 동률은 미확정으로 남기고 문서 미지지 성공으로 전환하지 않는다.
- 원형의 정렬 signal에 따른 후보군과 equivalent→negation→forward→reverse→alternation 우선순위를 사용한다. 신호가 support면 equivalent/forward, refute면 negation/reverse/alternation, unclear면 전체다. 어떤 연산도 성립하지 않으면 independent다. 정렬 signal 자체도 모델 판단이므로 오류가 뒤로 전달될 수 있다.
- micro 질문에도 전체 원문·부모·후보를 유지한다. 국소 문구만 쓰는 원형과 다른 전체 문맥 변형이다. 조건·부정·양태의 단어 겹침을 함의로 계산하지 않는다. 모델이 적용 범위 비교 불가라고 한 구간은 미지원으로 남기며 새 양태·극성 논리를 발명하지 않는다.

방향은 **원문 의미 E → 후보 의미 C**다. forward는 E가 C를 함의하는 방향, reverse는 반대 방향이다. 후보 전체의 최종 S/R/N은 모델이 출력하지 않고 아래 고정 전이로 계산한다. 이 연산표를 구현하는 코드의 정확성이 모델의 의미 관계 정확성이나 복잡한 한국어 조건의 형식적 증명을 보장하지 않는다.

| 현재 상태 | equivalent | forward | reverse | negation | alternation | independent |
|---|---|---|---|---|---|---|
| S | S | S | N | R | R | N |
| R | R | N | R | S | N | N |
| N | N | N | N | N | N | N |

논문 Figure 1의 도표를 직접 확인했다. 시작 상태는 S이며 N은 흡수 상태다. 원형에서 사용하지 않는 cover 연산과 별도의 양태/극성 투영은 추가하지 않았다. 상태·연산 trace를 저장한다. 같은 문자들의 포함관계로 이 표의 입력 연산을 정하지 않는다.

## 동결·코드 검사

입력은 직전 NLI 진단에 보존한 `inputs.json`과 `source_packet.json`을 그대로 재사용한다. 원문·후보·raw·부모는 동일하며 해시를 대조한다. c13/c46/c11의 사전 라벨은 S, c47은 N이다. c47은 지역 한정 행위를 일반화하여 원문으로 뒷받침되지 않으며 조건 밖의 명시적 반증을 주장하지 않는다. c11은 포함 관계의 부분 사실이며 전체 서류를 나열하지 않았다는 이유로 오류가 되지 않는다. 정답·오류 이유·완성 정정문은 모델 입력에 넣지 않는다.

`data/knowledge/evaluations/business_natlogic_20261009/freeze.json`에 입력·기준·질문·전이·코드·모델을 동결했다. 로컬 Qwen `qwen3.8:27b-q4_K_M`, digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`, context 49,152, max output 8,192, think=false, temperature=0, timeout=1,800초다. 최대 호출은 자동 분할/정렬 1회와 5연산×2질문 총 11회다. 모델 재시도는 없다.

실행 전 세 가지 검사가 통과했다(0.02초). 3원소 유한 집합의 모든 비공집합 조합에서 DFA가 거짓 S/R을 단정하지 않는지 확인했고, 이중 부정·흡수 상태, unknown/동률의 미확정 분리, 한글 문자열 전체 coverage와 중복/없는 인용 거부를 검사했다. 이는 일반 계산·주소 계약 검사이며 개발 사례의 의미 정답을 대신하지 않는다. 네 개발 사례는 모두 노출 자료다. 라벨 일치만으로 통과하지 않으며 실제 자동 정렬·연산·이유가 원문과 맞아야 한다.

## 실제 결과와 실패 경로

**이번 변형은 채택 실패다.** 11회 모두 응답을 받아 계산했으나 c47의 범위 확대를 최종 판정에서 검출하지 못했다. 개발 라벨 일치는 3/4이고, 정상 3건 보존과 오류 1건 검출을 모두 요구한 gate는 false다. 이 네 건은 독립 성능 추정용 표본이 아니다.

| 후보 | 사전 기준 | 실제 | 자동 pair 수 | 소비한 연산 | 결과 |
|---|---|---|---:|---|---|
| c13 | S | S | 2 | equivalent × 2 | 최종 라벨 일치 |
| c46 | S | S | 2 | equivalent × 2 | 최종 라벨 일치 |
| c47 | N | S | 1 | equivalent | 범위 확대 검출 실패 |
| c11 | S | S | 2 | equivalent × 2 | 최종 라벨 일치, 국소 동등성 오류 별도 |

7개 pair 모두 전체 후보 coverage와 정확한 인용 주소 검사를 통과했다. 자동 정렬은 모두 support/scope_supported=true였다. 이것은 모델의 자기 판단이며 실제 의미 범위 검증 통과가 아니다. c47은 후보 전체를 한 구간으로 유지했고 b32의 지역 한정이 있는 전체 문장을 정확히 인용했다. 따라서 해당 한정 문맥이 입력에 없어서 생긴 실패는 아니다.

c47의 equivalent 두 응답과 forward 두 응답은 모두 yes였다. 첫 equivalent 이유는 ‘특히 지역 번호’를 언급하면서도 후보의 일반적인 반납 절차와 의미가 같다고 판단했다. 반면 reverse 첫 응답은 지역 번호 한정으로 일반적인 번호판 변경 주장을 보장할 수 없다고 정확히 설명했고, 두 번째 응답은 no였다. **연산별 판단이 상충했다.** 정확한 국소 설명이 전혀 나오지 않았다고 서술할 수 없다.

고정된 실제 경로는 `support alignment → {equivalent, forward} → equivalent(2/2 yes) → S`다. reverse는 support 후보군 밖이고 자체 두 응답도 일치하지 않았다. 정답을 본 뒤 reverse를 우선시키거나 상충을 unknown으로 바꾸지 않았다. 모든 pair에서 negation의 두 번째 응답과 alternation의 두 응답은 unknown, reverse는 yes/no였지만, 해당 연산들은 고정 support 후보군 밖이므로 최종 unresolved에 반영되지 않았다. 최종 미완료/미확정 0건은 모든 국소 관계가 명확했다는 뜻이 아니다.

정상 후보의 최종 라벨도 중간 연산의 정확성을 증명하지 않는다. c11의 두 번째 정렬 E는 다른 구비 항목도 포함하는 b30 전체인 반면 C는 신분증 사본 한 항목의 포함을 말한다. E→C는 성립하지만 C가 나머지 E까지 함의하지 않으므로 양방향 equivalent 판단은 부정확하다. c46도 원문에 있는 날인 세부사항을 모두 되돌려 함의하는 후보가 아니어서 동등성보다 단방향 지지와 구별해야 한다. 자동 구조와 국소 의미를 별도로 요구한 semantic gate 역시 통과하지 않았다.

## 비용·증거와 종료 범위

실제 호출 11회, 입력 21,071 token, 출력 7,425 token, 응답별 elapsed 합계 511.502775초다. 이는 해당 로컬 실행의 응답 시간 합계이며 전체 준비·검토시간이나 배포 환경 시간은 아니다. 분할/정렬 1회와 5연산×2질문 외 모델 재호출은 없다. 입력 잘림이나 전송 실패는 기록되지 않았다.

로컬 원본은 `data/knowledge/evaluations/business_natlogic_20261009/`의 `freeze.json`, `started.json`, `inputs.json`, `source_packet.json`, `criteria.json`, `calls.json`, `alignment.json`, `microjudgments.json`, `result.json`, `tests.log`에 보존했다. 함께 커밋한 JSON 보고서에는 입력/코드/실행 증거 해시, 고정 설정, 결과, 전체 국소 판단과 이유 및 원본 경로를 담았다. 실행 당시 스크립트 SHA256은 `da84a71103c7fd87842e9ea8be73df0be0ceb6cc55966ef24399906916523a9c`다.

같은 질문·모델의 튜닝 반복과 후속 제품 통합은 진행하지 않는다. 이 결과는 **로컬 Qwen, 2-template hard-label·전체 문맥 변형**의 실패이며 원 논문의 likelihood 10-template 방식이나 자연논리 전체가 불가능하다는 근거가 아니다. 독립 후보 #626의 검토 영어 번역 + 공개 pretrained verifier 비교를 다음 순서로 진행한다. #616/#617/#620의 실제 자동 수정·저장·정상 보존·R05·그래프 검색 기반 QA 완료는 이 진단으로 충족되지 않았다.
