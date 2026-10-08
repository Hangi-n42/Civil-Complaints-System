# 검토 영어 번역 + VitaminC 공개 모델 진단 — 2026-10-09

연구 #626은 원문의 작은 변화에 민감하도록 대조 학습한 공개 verifier가 기존 한국어 개발 사례를 구분하는지 제한 확인한다. 기준 입력은 `645dfc004abcd58d5144fbf01dbe92e4dd16f9eb`의 기존 원문/후보이며, 직전 자연논리 연구 커밋 `fed8a8945c8f6f9b7a862be7aeabeb4a2b98d0e1` 이후 별도로 실행한다. 제품 코드·DB·평가 기준은 변경하지 않는다.

## 근거와 재현 범위

[VitaminC 논문](https://aclanthology.org/2021.naacl-main.52/)은 거의 같은 근거가 서로 다른 지지 여부를 만드는 대조 자료를 사용한다. 이번 **한국어→검토 영어 번역→공개 모델** 결합은 우리의 변형이다. 논문의 벤치마크 성과를 한국어 행정 조건의 성공으로 전제하지 않는다. 이전 한국어 NLI와 언어·모델·학습 과제가 함께 달라지므로 한 변수의 효과로 해석하지 않는다.

사용 체크포인트는 [tals/albert-xlarge-vitaminc-mnli](https://huggingface.co/tals/albert-xlarge-vitaminc-mnli/tree/3082ba54344bd9ddada2be1c5e9b4131721d2a5d), revision `3082ba54344bd9ddada2be1c5e9b4131721d2a5d` 하나다. [공식 processor](https://github.com/TalSchuster/VitaminC/blob/eb532922b88b199df68ed26afeb58dca5501b52f/vitaminc/processing/multitask_sent_pair_cls.py)는 evidence를 첫 문장, claim을 두 번째 문장으로 받는다. 라벨은 0=SUPPORTS, 1=REFUTES, 2=NOT ENOUGH INFO이며 실제 config와 대조했다.

[공식 저장소 LICENSE](https://github.com/TalSchuster/VitaminC/blob/eb532922b88b199df68ed26afeb58dca5501b52f/LICENSE)는 MIT이고, [자료 조건](https://github.com/TalSchuster/VitaminC/blob/eb532922b88b199df68ed26afeb58dca5501b52f/DATA_LICENSE)은 Wikipedia 해당 조건 및 CC BY-SA 3.0을 별도로 설명한다. 다운로드한 모델 카드에는 가중치에 대한 명시적인 license 선언이 없다. 저장소 MIT가 가중치 재배포 권한까지 자동으로 확인해 주지는 않는다. 이번에는 공개 파일의 로컬 연구 추론만 수행하며 가중치를 커밋·배포하지 않는다.

## 번역·실행 계약

기존 승인된 GPT-6 Astra 작성 에이전트가 원문 블록 10개와 후보 4개를 각각 번역하고, 다른 기존 에이전트가 원문 대조 검토했다. 검토자는 verifier 결과·판정 기준·구현을 보지 않고 번역 의미만 확인했다. 원문과 후보의 한국어 문자열 및 부모 관계 일치를 계산으로도 검사했다. 인간 전문 번역 검수가 아니며 두 에이전트의 검토가 번역의 무오류를 보증하지 않는다.

b32의 괄호 밖은 번호판 변경 조건의 구비품목 목록이고, 괄호 안에만 지역 번호의 반납 후 변경 의무를 유지했다. c47에는 없는 지역 조건을 번역 중 추가하지 않았다. c13/c11의 ‘포함한다’는 일부 포함 관계로 두었고 전체 충분성으로 바꾸지 않았다. 수행 주체가 생략된 후보는 수동형으로 옮겨 주체를 보충하지 않았다. 숫자·괄호·날인·법인인감증명서를 유지했으며 번역자 notes는 모델 입력에서 제외했다.

영문 premise는 원래 블록 순서대로 본문 전체를 줄바꿈으로 연결한다. b29 조건 제목 뒤에 b30/b31이 이어지는 순서를 보존하고 부모 metadata도 별도 보존한다. 이전 NLI와 같이 ID/메타데이터를 문장쌍 모델에 별도로 주입하지 않는다. hypothesis는 해당 후보의 영어 번역 전체다. 정답/정정문/오류 설명은 모델 입력에 없다.

CPU FP32, eval/inference_mode, safetensors, local_files_only=true, trust_remote_code=false, truncation=false로 고정한다. 공식 SentencePiece 토크나이저를 위해 로컬 환경에 `sentencepiece==0.2.1`을 설치했으며 제품 의존성에는 추가하지 않는다. 최대 길이는 모델/tokenizer의 512이며 초과 시 자르지 않고 실패 분모에 남긴다. 후보당 한 번, 총 최대 4회 argmax 비교이며 임계값 조정·재시도·다른 체크포인트 순회는 없다.

사전 기준은 c13/c46/c11=SUPPORTS, c47=NOT ENOUGH INFO다. c47의 미지지는 명시적인 반증이나 조건 밖 면제를 뜻하지 않는다. 네 건은 모두 개발 노출 자료다. 네 라벨을 모두 맞춰야 후속 비교를 진행하며, 검토 번역의 라벨 성공만으로 자동 번역·오류 위치·정정·저장·제품 QA 성공을 주장하지 않는다.

## 실제 결과

**이번 검토 번역 + 단일 체크포인트 조합은 채택 실패다.** 정상 3건은 유지했지만 c47의 일반화도 SUPPORTS로 판정했다. 개발 라벨 일치는 3/4이며 일반 정확도 추정이 아니다. 기준 게이트는 false다.

| 후보 | pair token 수 | SUPPORTS softmax | REFUTES softmax | NEI softmax | argmax | 기준 일치 |
|---|---:|---:|---:|---:|---|---|
| c13 | 251 | 0.975406 | 0.004963 | 0.019631 | SUPPORTS | 예 |
| c46 | 268 | 0.990573 | 0.002356 | 0.007071 | SUPPORTS | 예 |
| c47 | 236 | 0.951626 | 0.014339 | 0.034035 | SUPPORTS | 아니오 |
| c11 | 254 | 0.986425 | 0.002233 | 0.011342 | SUPPORTS | 예 |

이 softmax는 보정된 정답 확률이 아니다. c47의 원본 logits는 `[2.4494731426239014, -1.745686650276184, -0.8813148736953735]`다. 모델이 설명을 생성하지 않으므로 내부 오판의 구체적 원인을 이 출력만으로 확정할 수 없다. 실제 입력에는 지역 한정 원문과 이를 일반화한 후보가 모두 있었고, 길이 초과·잘림·전송 실패·빈 응답은 없었다. 따라서 해당 문제로 이번 실패를 설명할 근거는 없다.

원문-번역의 보존은 별도로 검토했지만 그 사실이 영어 verifier의 의미 이해를 보장하지 않는다. 이번 결과는 영어로 바꾸면 이 단일 모델이 핵심 오류를 구분한다는 가설을 통과하지 못했다. 모든 영어 모델·모든 NLI·VitaminC 학습법 전체의 불가능을 주장하지 않는다. 오류 위치 특정/자동 정정/한국어 자동 번역 통합은 수행하지 않았다.

## 실행·검토 비용과 증거

실제 분류기 forward는 4회, 총 1.521151초, 모델 로딩은 0.503070초다. CPU FP32 로컬 실행의 측정값이며 다운로드·번역·검토·전체 준비시간은 포함하지 않는다. 분류기는 생성 token이 없으며 pair input 길이 합은 1,009 token이다. 다운받은 가중치와 tokenizer/config 파일은 freeze에서 각각 SHA256을 고정했다.

평가자료 작성과 검토는 기존 승인된 GPT-6 Astra 경로의 `/root/contrast_author`, `/root/contrast_reviewer`가 수행했다. 도구가 노출한 식별자는 이 canonical agent 이름이다. 별도 내부 session UUID, 실제 과금, token 사용량, 각 작업의 총 실행시간은 **확인 불가**다. 검토 파일의 기록시각은 `2026-10-08T17:50:28.060727Z`이며 총 소요시간으로 환산하지 않았다. 인간 검토로 기재하지 않는다. 조정 채팅에서도 동결한 번역의 원문 보존을 별도로 대조했다.

실행 전 원문/후보 일치, 순서 보존, notes 배제의 작은 serialization 검사를 통과했다. 순서를 뒤집은 입력은 거부했다. 컴파일 검사도 통과했다. 이는 입력 계약 확인이며 분류 품질 검사가 아니다.

로컬 근거는 `data/knowledge/evaluations/business_vitaminc_20261009/`의 `translation_draft.json`, `translation_review.json`, `inputs.json`, `criteria.json`, `freeze.json`, `started.json`, `length_preflight.json`, `result.json`, `download.json`, `dependency_install.log`, `self_check.log`, `run.log`다. 함께 커밋한 JSON에 번역/검토/동결/결과와 증거 해시를 담았다. 기존 한국어 raw 원문은 수정하지 않았다.

핵심 게이트 실패에 따라 자동 번역 통합과 같은 모델의 반복은 중단한다. 연구 #626은 제한 비교 완료/후보 기각으로 닫으며, 독립 후보 #627의 자동 조건·효과·양태 구조 비교로 이어간다. 제품 자동 교정 및 종단 요건 #616/#617/#620는 이 결과로 완료되지 않는다.
