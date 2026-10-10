# 동일 문서 단위의 Trankit Korean-KAIST 비교 (#648)

2026-10-10, 기준 commit `a5fd5c9b931c70a7207a12334d3b3afc8497451f`. 단일 사전학습 파서 비교를 종료했다. 일부 명사와 정상 후보의 조건–행위 단서는 개선됐으나 c47 핵심 오류 판단에 필요한 원문의 지역 조건 귀속은 확보되지 않았다. Qwen 추가 0회, 후속 의미 판단 효과 미측정, 제품 미채택이다.

## 기존 비교와 고정 구성

[#646](business_document_boundary_20261010.md)에서 고정한 동일한 24개 단위·원형·주소를 사용하고 Stanza 대신 Trankit 한 구성을 분석한다. 문서 경계를 동시에 바꾸지 않는다. [Trankit 논문](https://aclanthology.org/2021.eacl-demos.10/)과 [공식 모델 목록](https://trankit.readthedocs.io/en/latest/pkgnames.html)의 한국어 KAIST 구성을 결과 전에 선택했다. 과거 XLM-R NLI 분류기 반복이 아니라 XLM-R 기반 구문 분석이다. GSD/large/다른 파서 순회와 새 학습은 없다.

| 항목 | 고정값 |
|---|---|
| 공식 코드 | [nlp-uoregon/trankit](https://github.com/nlp-uoregon/trankit/tree/54e863327391262cf72f6adc1b0ff104e972a1dc), commit `54e863327391262cf72f6adc1b0ff104e972a1dc`, version 1.1.2 |
| task weights | HF uonlp/trankit revision `1add34e3909949dbb98523ed6cfcb4e9393e2c8e`, `models/v1.0.0/xlm-roberta-base/korean-kaist.zip` |
| task ZIP | 35,339,423 bytes, SHA256 `61ad040e3ed0ff8caf858a66bd5b2aa76aabf42f94258c8a3435a79d22a78a7d`, 공식 LFS 값과 일치 |
| encoder | FacebookAI/xlm-roberta-base revision `e73636d4f797dec63c3081bb6ed5c7b0bb3f2089` |
| encoder weights | model.safetensors 1,115,567,652 bytes, SHA256 `6fd4797bc397c3b8b55d6bb5740366b57e6a3ce91c04c77f22aafc0c128e6feb`, 공식 LFS 값과 일치 |
| 환경 | 별도 venv, Python 3.11.9, torch 2.0.1, adapters 0.1.1, transformers 4.35.2, numpy 1.26.4 |
| 호출 | `Pipeline('korean-kaist', gpu=False, embedding='xlm-roberta-base')`, 각 원형에 `is_sent=True`, CPU 4 threads, seed 42 |

공식 코드가 요구하는 torch 상한 및 adapters/transformers 호환 범위를 별도 환경에 고정했다. 제품 또는 Stanza 환경을 변경하지 않았다. 설치된 runtime Python 파일 34개가 공식 source와 byte 단위 동일하며 `pip check`를 통과했다. 최초 설치 코드 감사가 배포되지 않는 source tests까지 찾던 오류는 감사 대상만 설치 파일로 한정해 해결했다. 모델/라이브러리를 패치하거나 다른 모델로 교체하지 않았다. 전체 의존성 lock과 설치 영수증을 남겼다.

고정 encoder 5파일 합계는 1,120,642,581 bytes다. 상대 모델 이름이 이 고정 로컬 디렉터리를 가리키도록 작업 디렉터리를 지정했고 HF/Transformers offline 환경으로 실행했다. task ZIP의 공식 downloaded marker와 tokenizer/tagger/lemmatizer/vocab 파일을 그대로 사용했다. 원래 코드의 자동 다운로드로 다른 revision을 섞지 않았다.

## 이용 조건과 학습 식별 한계

[코드 LICENSE](https://github.com/nlp-uoregon/trankit/blob/54e863327391262cf72f6adc1b0ff104e972a1dc/LICENSE)는 Apache 2.0, [encoder 모델 카드](https://huggingface.co/FacebookAI/xlm-roberta-base/tree/e73636d4f797dec63c3081bb6ed5c7b0bb3f2089)는 MIT, [KAIST treebank](https://github.com/UniversalDependencies/UD_Korean-Kaist)는 CC BY-SA 4.0으로 각각 구분한다. task-weight HF metadata에는 별도 카드 라이선스가 없고 ZIP 5개 member에도 LICENSE/NOTICE/README가 없다. 이 확인만으로 모든 가중치의 재배포·상업 이용 허용이나 금지를 단정하지 않는다. 이번에는 로컬 연구 실행과 식별 영수증만 보존하며 가중치를 재배포하지 않는다.

공식 mapping은 `korean-kaist → UD_Korean-Kaist`, training_id 2이며 이 구성은 MWT expansion을 하지 않는다. lemma checkpoint의 `ko_kaist`와 학습 경로는 확인했으나 정확한 UD 학습 릴리스는 확인 불가다. Stanza와 treebank 이름이 같다고 학습 자료/릴리스 동일성을 주장하지 않는다. 공식 README에 따르면 lemma 구현은 Stanza에서 유래했다. 따라서 모든 단계의 학습 계보가 독립인 비교라고 부르지 않는다. 모델 구성 전체의 차이를 비교한다.

## 실제 원형과 구문 정보

입력 SHA256 `6291df9299be771f71cb9d47ef6874279e24eae571af9c0c3609f0c598746d2c`, 24개 `(address, unit)`가 #646과 동일하다. 원문 11단위, 후보 13필드이며 출력의 text도 원형과 같다. 토큰의 보고 span만 검증하고 원래 block/field 시작 위치를 더했다. 주소를 다시 검색해 보충하거나 lemma를 인용문으로 쓰지 않았다. 155개 토큰 모두 정확한 원형 구간에 대응하고 비공백 누락은 0이다.

| 대상 | Trankit 실제 출력 | #646 대비 정보 가치와 한계 |
|---|---|---|
| b31/c13 Tail | `도장날인`과 `특약사항란` NOUN | Stanza의 도장날인 VERB·특약사항란 ADV 분석 일부 개선. 다만 `특약사항란 → 여는 괄호 (conj)` 등 목록 연결 오류는 남음 |
| b29 부모 | `양수인` VERB/`양수+이+ㄴ` → `미방문시` (acl), 후자는 NOUN/root | 원문 주체·미방문 조건의 정확한 분석은 미확보 |
| b32 지역 | 표면 `지역 번호는` → 바깥 `봉인` (dislocated) | 지역 조건을 안쪽 반납·변경 의무에 귀속하지 못함 |
| b32 의무·순서 | `반드시 → 안쪽 2매 (advmod)`, `후 → 변경하여야 (advmod)`, `함 → 변경하여야 (aux)` | 순서 일부 단서는 있지만 필수성의 연결은 부정확 |
| b32 두 단위 | root `변경하여야` / `사용할` 각각 유지 | #646과 같은 경계 효과이며 Trankit만의 신규 성과가 아님 |
| c46 Event | `양수인이 → 미방문 (nsubj)`, `미방문 → 시 (compound)`, `시 → 구비한다 (advmod)` | Stanza의 `시 → 위임장 (compound)`보다 조건–행위에 유용한 단서 |
| c46 나머지 | `양수인 신분증`의 양수인 VERB 및 일부 목록 연결 오류 | 정상 후보 전체 의미 보존이 검증된 것은 아님 |
| c47 Event | `시 → 변경한다 (advmod)`, `반납하여 → 변경한다 (ccomp)` | 후보 일반 조건의 단서는 있으나 원문의 지역 한정과 올바른 대응을 확보하지 못함 |

b32 token의 **표면**은 `지역 번호는`이며 lemma는 `지역+참번호+는`이다. 후자는 모델 출력 오류를 포함한 분석값으로 원문 인용이 아니다. 모든 raw 값을 그대로 보존했다. 관계 이름 변화나 token 수 증가 자체를 정확도 향상으로 계산하지 않는다.

## 비용과 종료 기준

pipeline load 1.983671초, 24단위 parse 합계 4.897783초다. 같은 단위를 처리한 Stanza의 1.297701초/0.430643초와 각각 구분한다. 단일 CPU 실행이며 설치·다운로드·Python 시작·검토 시간은 제외했다. 성능 분포나 일반 benchmark 우열을 입증하지 않는다. 생성 호출·입출력 생성 토큰은 0이다.

평가 담당과 독립 전문가가 원시 출력과 동일 단위 대조를 검토했다. c46 부분 개선은 인정하지만 원문 b29와 c47의 핵심 지역 조건 대응이 미확보이므로 후속 Qwen 관문을 충족하지 않았다. **Trankit 의미 판단 실패를 실행으로 확인한 것이 아니라, 필요한 원문 구문 정보 미확보로 후속 효과를 측정하지 않은 것이다.** 추가 Qwen·새 검수 모델·다른 parser·학습은 실행하지 않는다.

입력/주소 동등성, 고정 코드/설정, token span과 원형 slice, 누락 구간, head 범위 및 반복 표면/불일치 selfcheck를 확인했다. 이미 확인한 설치 코드·가중치 영수증을 재사용하며 venv/source 전체를 반복 해싱하지 않았다. 원문·DB·제품 경로를 수정하지 않았으며 전체 제품 테스트는 하지 않았다.

입력은 모두 개발 노출 자료이고 새 확인 자료는 0건이다. 자동 검출→수정·저장→정상 보존→같은 요구→그래프→검색→답변은 미실행, #616/#617/#620은 미완료다. 연구 종료가 제품 병목 해결은 아니다. 로컬 `data/knowledge/evaluations/business_trankit_20261010/`에 raw parse/설정/동결/환경/모델 식별/실패를 포함한 설치 기록을 보존하고 공개 [manifest](business_trankit_20261010.json)에 필요한 작은 증거와 해시를 기록한다. 현재 사용자 결정이 필요한 사항 없음.
