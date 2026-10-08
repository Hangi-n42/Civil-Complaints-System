# ClearCheck 공개 모델의 한국어 조건·범위 진단 — 2026-10-09

연구 #628은 공개 사실검증 모델 ClearCheck가 기존 한국어 조건 확대 오류를 구분하는지 확인한다. 기존 모델/프롬프트 변형의 실패를 반복하지 않고 공개 체크포인트 하나와 공식 CoT 템플릿 하나를 고정했다. 기준 HEAD는 `57b23f1724f0a5e4353f6a6efd89d76ebc06138c`다. 원문·후보·부모·제품 DB·기존 동결 결과는 보존한다.

## 공식 방법과 로컬 적용

[논문](https://arxiv.org/html/2506.13342v2)은 Llama 3.1 8B Instruct에 ANLI와 합성 multi-hop 자료를 사용한 학습을 설명한다. 이는 공개 모델의 학습 이력이며 우리 자체 학습이 아니다. 논문은 CoT를 direct보다 우월하다고 보고하지 않는다. 이번 CoT 선택은 실제 이유를 원문과 대조하기 위한 것이다. 한국어 행정 조건에서의 효과는 별도 검증 대상이다.

[공식 코드](https://github.com/just1nseo/verifying-the-verifiers/tree/a2b9d5f5afa23c09bed142e4cd120b510d581d1c) revision은 `a2b9d5f5afa23c09bed142e4cd120b510d581d1c`다. `ClearCheckCoT`는 원문들을 줄바꿈으로 연결해 공식 템플릿에 넣고 user 메시지 하나를 tokenizer chat template으로 변환한다. 출력의 마지막 대괄호에서 세 범주를 추출한다. 공식 평가의 Not Attributable/Contradictory 이진 합산은 이번 코드에서 사용하지 않는다.

[공개 체크포인트](https://huggingface.co/just1nseo/ClearCheck-8B/tree/89255c69f65d49e574092772963afc3e5ba6a30b)는 revision `89255c69f65d49e574092772963afc3e5ba6a30b`, BF16 8,030,326,784개 parameter, 4개 safetensors shard다. 모델 카드의 Apache-2.0 선언과 코드 저장소 루트의 명시 LICENSE 부재를 구별한다. 일부 공통 utils 파일의 Apache header를 전체 저장소 라이선스로 확대하지 않는다. 기반 모델은 [Llama 3.1 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE) 조건을 별도로 확인했다. 공개 가중치의 로컬 연구 사용이 기업 배포·재배포 조건 전체의 승인을 뜻하지 않는다. 가중치와 공식 구현 전체를 제품에 복사·배포하지 않는다.

## 동결 계약

- 기존 `business_nli_20261009/inputs.json`과 `source_packet.json`의 한국어 원문 10블록 및 c13/c46/c47/c11을 사용한다. 부모 제목과 블록 순서를 유지한 본문 전체이며 번역·정답·오류 이유·정정문을 추가하지 않는다.
- 공식 `CLEARCHECK_COT`를 참조 파일의 상수 AST에서 읽는다. 참조 패키지는 실행하지 않는다. 공식 tokenizer의 user 1개 + generation prompt 형식을 그대로 적용한다. 기본 시스템 머리말의 `26 Jul 2024` 및 `December 2023`도 실제 template 내용으로 보존하며 현재 날짜로 바꾸지 않는다.
- 로컬 Transformers/MPS BF16, safetensors, trust_remote_code=false, local_files_only=true, SDPA를 사용한다. 공식 vLLM 엔진과 다르므로 모델·템플릿·엔진의 결합 변경이며 수치 동일 재현을 주장하지 않는다.
- temperature=0.1, top_p=1, top_k=0(제한 없음), max_new_tokens=1024, sampling=true, seed=42, 후보당 1회·총 4회다. 체크포인트의 기본 generation 설정 0.6/0.9를 그대로 쓰지 않고 공식 CoT 설정으로 덮어쓴다. stop IDs는 모델 config의 128001/128008/128009로 고정한다.
- 공식 실행의 context 상한 32,768을 적용하고 truncation=false다. 실제 입력 길이는 c13=465, c46=479, c47=454, c11=466이다. 추가 BOS를 중복 삽입하지 않는 tokenizer 동치 검사를 통과했다.
- native pre-sampling logits에서 top-3 및 실제 선택 token의 log probability를 저장한다. vLLM 값과 동일하다고 가정하지 않으며 이를 보정된 정답 확률이나 채택 기준으로 쓰지 않는다.
- 기준은 Attributable/Attributable/Not Attributable/Attributable이다. c47의 원문 미지지와 명시 반증을 구별한다. 정상 보존과 원문에 충실한 이유까지 모두 요구한다. 잘림·라벨 없음·실패는 미확정으로 분모 4에 남긴다. 모두 개발 노출 사례이며 단일 sampling 결과로 안정성이나 일반 성능을 입증하지 않는다.

현재 장비는 M4 Max 36GiB이며 설치된 torch 2.5.1/transformers 4.46.3을 유지했다. peak 로딩 메모리를 줄이기 위해 로컬 환경에 accelerate 1.10.1만 추가했으며 제품 의존성 파일은 변경하지 않았다. 작은 BF16 MPS 연산 확인은 전체 모델 실행 성공과 별개다. 세 라벨 분리/최종 라벨 누락과 안전한 template 읽기의 일반 검사 2개가 0.01초에 통과했다.

## 실제 결과

**이번 고정 구성은 기각한다.** 전체 모델은 MPS BF16/SDPA로 실행됐지만 c47 범위 확대를 놓쳤고 실제 이유도 원문과 맞지 않았다. 정상 3건은 최종 지지 라벨을 유지했다. 개발 라벨 일치는 3/4이며 일반 성능 정확도가 아니다.

| 후보 | 기준 | 실제 | 출력 token | 생성 시간(초) | 종료 |
|---|---|---|---:|---:|---|
| c13 | Attributable | Attributable | 121 | 18.272787 | EOS |
| c46 | Attributable | Attributable | 151 | 15.161227 | EOS |
| c47 | Not Attributable | Attributable | 98 | 10.155351 | EOS |
| c11 | Attributable | Attributable | 77 | 7.845281 | EOS |

c47의 Extraction은 지역 번호 조건이 있는 원문을 그대로 인용했다. 그러나 Inference는 번호판 변경 일반에 반납 의무를 부여했고, `must be returned after changing the number`라고 써 원문의 ‘반납 후 번호 변경’ 순서까지 뒤집었다. 마지막 Attributable 판단은 원문과 추론의 범위 차이를 검출하지 못했다. 이 오류를 입력 문맥 누락이나 출력 잘림 때문이라고 설명할 근거는 없다. 반증과 미지지를 합치지 않아도 이번 출력은 지지 오판이다.

c13은 미방문 조건 아래 양도증명서의 포함을 설명했고, c46은 해당 구비 목록을 대조했다. c11은 신분증 사본의 부분 포함을 지지했다. c46의 이유에 ‘동일하다’는 표현이 있으나 최종 기준은 양방향 세부사항 등가가 아닌 후보의 단방향 지지다. 이러한 정상 3건의 유지가 핵심 c47 실패를 상쇄하지 않는다.

실제 parameter 장치/형식은 `mps:0`/`torch.bfloat16`, attention은 `sdpa`다. 모델 로딩 3.124799초, 4회 생성 합계 51.434647초, 입력 1,864/출력 447 token이다. 각 생성 종료 직후 측정한 MPS driver 메모리 중 최대는 21,284,782,080 bytes다. 이는 전체 실행의 계측된 peak가 아니라 종료 직후 표본의 최대다. 다운로드·해시·검토시간을 생성 시간에 합치지 않았다. 전체 실행을 마친 프로세스는 종료돼 다음 Qwen 비교와 모델을 동시에 상주시켜 실행하지 않았다.

## 증거와 후속 경계

원본 `data/knowledge/evaluations/business_clearcheck_20261009/`에 공식 참조·메타데이터·다운로드 기록, inputs/criteria/freeze/started/result, 검사 및 실행 로그를 보존했다. 실제 formatted chat, input/output token IDs, token별 native top-3/선택 log probability, stop 이유, 버전과 모든 checkpoint 파일 해시를 기록했다. 커밋한 JSON에는 동결 계약·입력·raw 답변·생성 token·비용·의미 검토를 포함하고, 상세 token log probabilities는 로컬 원본 경로/해시로 연결한다. 응답이나 이전 동결 결과를 덮어쓰지 않았다.

공식 CoT 한 구성의 단일 sampling 결과다. Direct 변형·다른 seed·프롬프트·임계값 탐색·양자화·번역·자체 학습은 실행하지 않았다. ClearCheck 전체 또는 모든 전용 verifier가 불가능하다는 결론은 아니다. 이번 게이트 실패로 미사용 확인셋과 자동 교정·저장·R05·그래프/검색 기반 동일 질문 QA에 연결하지 않는다. 연구 #628의 비교 기각과 제품 #616/#617/#620의 미완료를 구별하고, 다음 독립 비교 #629를 실행한다.
