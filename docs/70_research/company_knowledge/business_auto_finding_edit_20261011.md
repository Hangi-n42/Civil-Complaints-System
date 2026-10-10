# 실제 자동 c47 연결과 자유 공백 소유 수정 진단

2026-10-11. 제품 branch `feature/business-requirement-answer-flow`, 시작 commit `9abff745d9fbf8d6baa4d7ff04651dd849461c3b`, 기록 계약 수정 commit `890529b890ce307bd5592ef09b84ff030871aadf`. 기존 #616/#617/#620의 제한 후속이며 이슈 완료·merge·배포를 뜻하지 않는다.

## 확인된 결과와 남은 경계

실제 연구 자동 finding 한 건을 기존 native 편집에 연결하여 c47을 저장했고, 자동 원문 재판정·보존 검수·승인 가능한 스냅샷·실제 전체 그래프 검색·같은 질문의 QA에서 수정 지식을 사용했다. c47의 일반 구비항목과 지역 번호에 한정한 반납 후 변경 조건이 유지됐다. 이 한 건의 연결은 부분 성공이다. 전체 R05 의미 완료, 제품 완료, 연구 검수기의 기본 채택이나 일반 품질 향상은 입증하지 않았다.

별도로 자유 `gaps`를 선택 의미 소유로 강제한 코드 한 줄을 수정했다. 미귀속 `meaning_keys=[]`와 조사 당시 `scope_meaning_keys`를 분리하고, 명시 `meaning_gaps`의 소유는 그대로 보존한다. 이 기록 계약 수정은 채택했다. 수정 후 join은 여전히 공백 0의 대상을 바꿔 해소했다고 하므로 종합 의미 효과는 확인되지 않았다.

기존 cb9의 제한 안내 성공에 대한 2026-10-09 평가 정정은 유지했다. 그때의 정확 과제 지시·추가 입력만 이번 지식에 다시 연결한 새 QA는 구체 미확인을 생성했으나 내부 모순과 불필요한 공백이 남아 **미채택**이다. 과거 cb9 성공을 새 실행의 성공으로 전용하지 않았다. 해당 patch는 별도 사본에만 있으며 기본 `reviewed_items` 지시는 변경하지 않았다.

## 자동 finding에서 같은 QA까지

원 후보는 `번호판 변경 시 기존번호판 2매 및 봉인을 반납하여 번호를 변경한다.`였다. 연구 `c47_single`의 실제 자동 finding은 일반 구비항목과 지역 번호 한정 반납 의무를 구분하지 않은 확대를 지적했다. 원 응답 해시는 `af5993ac2421dbd644b508f860ee377fb4b30dfbf85f81a341f9fca8bd4cae60`이다. X 단일 입력을 사용했고 원하는 교정문·gold·Y 후보를 편집 입력에 넣지 않았다.

native 모델이 생성하고 저장한 Event는 다음 두 줄이다.

```text
번호판변경시 기존번호판 2매 및 봉인
지역 번호는 반드시 기존번호판 2매 및 봉인 반납 후 번호 변경하여야 함
```

`기존번호판`·`봉인`과 원문 정확 주소가 보존됐다. 저장 receipt는 `2b6f5e4c2b2442439afa5f0d76668d2f`, origin은 `model_event_edit`다. 실제 사람 검토나 승인 결과로 표기하지 않았다. 원문은 version `7b42ae519cbd4184b4de800623559005`, parse `c07b68e5135e49118fbae958f46125bf`, block `a55dc972ad5c4f5d8e8c3c22c80c6735`, span `[0:116]`이다. 지역 번호 밖의 면제·금지·추가 기간을 만들지 않았다. `번호 변경 시`는 업무 시점 문맥이다.

자동 원문 재판정은 이 의미 한 개만 대상으로 했고, c47/119개 후보·171개 원문 블록은 바꾸지 않았다. 나머지 **운영 의미 16개 중 8개는 과거 조율 AI 명시 정정**, 8개는 과거 모델/검토 기록이다. 재사용 donor는 `fd10ffa6e523437eb2ab1b31411dba8b`이며 이 16개를 새 자동 성과 분모에 넣지 않는다. 저장된 origin=`user`는 당시 API 기록값으로 실제 사람이 수행한 시험을 뜻하지 않는다. donor의 c47 의미·판정·교정·보존 이력은 복사하지 않았다.

기존 `r05_reuse_audit.json`의 `donor_c47_or_manual_source_meanings_copied=false`는 비-c47의 과거 AI 정정까지 없었다는 뜻으로 읽힐 수 있다. 원 감사 파일을 덮어쓰지 않고 `reuse_provenance_clarification.json`에 donor c47=0, 운영 의미=16, 그중 조율 AI 정정=8을 구분해 정정 설명을 붙였다.

c116/c117은 이미 완료된 수정·정상 의미 보존 영수증을 버전 대조 후 재사용했다. 새 c116/c117 교정·전체 추출·전체 282개 개념 재생성은 하지 않았다. c47 연결 대상인 이벤트·개체 2개·관계의 **4개 개념만** 갱신했다. 승인 후보는 21개, 스냅샷은 `259ea7cd945c4c10a9f2129469078451`이다. 현재 전체 검색 그래프는 364 nodes/5061 edges/171 passages/134 concept nodes다. 일반화된 옛 c47 Event는 활성 그래프·검색 입력에서 제외됐다. 21개 필수 검토 후보의 정책 포함을 자연 검색 품질로 세지 않았다.

공개 질문은 `번호판 변경을 수반하거나 수반하지 않는 이전등록을 어느 기관에서 처리할 수 있는가?`이며 revision 1과 criterion을 고정했다. `source_run_id=null`, `hipporag2`, `full`, limit 50, `reviewed_items` 및 공개 네 항목을 그대로 사용했다. 원문 QA 우회는 없었다.

## 판정·QA·기록 수정의 효과 분리

- 기본 C run `954a0173c52b41ec997bca47af3a6e86`: 모델은 `satisfied`, source completeness=`complete`, errors=[], preservation_complete=true로 저장했다. 그러나 공백 0은 번호판 변경 **없는** 경우의 서류를 지적하는데 해소 근거는 변경 **시** b32/c47만 가리켰다. `common_documents`의 별도 공통사항 근거는 존재하지만 모델의 해소 설명이 그 근거를 직접 사용하지 않았다. 과거 source.conjunctions의 복합 처리 단정도 유지돼 모델 상태를 최종 의미 완료로 확정하지 않았다.
- 기본 D QA `0416918d5c604dc5b91c9ceab24d3003`: `answered`, c47·기관 담당·정확한 제외·서류 조건·실제 인용을 보존했다. 네 `unconfirmed`는 모두 빈 배열이며 일반 전제 경고만 있어 `r05-guidance-scope-v1`의 구체 미확인 표시는 달성하지 못했다. 옛 conjunction 문장은 실제 QA 입력에 직접 포함되지 않았지만 C의 satisfied 때문에 assessment_limitations도 전달되지 않았다.
- cb9 재사용 QA `761fad0ac9934e8cb484c37eae9592aa`: 같은 현재 스냅샷·공개 질문·모델·schema·설정에서 보존된 과제 지시와 동적 `required_preserved_meaning_refs`만 사용했다. D의 필터 요청 메시지/schema/ref/설정/실행 한도가 정확히 일치하여 응답을 재사용하고, D의 동결 순위·검색 입력을 재생했다. 새 검색·embedding은 0, 새 QA는 1이다. 네 항목에 구체 미확인이 생겼지만 첫 항목은 연결이 ‘확인됨’ 후 같은 연결 부족을 쓰고, 제외 항목은 금련산 제외 미제시 후 명시 제외를 스스로 인정했다. 번호판 변경 없는 경우·서류에도 불필요한 추가 공백이 생겨 채택하지 않았다. 새 지시 변형·정상 대조 모델·QA 재시도는 0이다.
- owner 수정 run `29d2b55edd704c65a9d3e4be024ddf19`: 실제 source 응답 `1f3345c4ec084e2184da588d95b6e97f`를 수정 코드로 재생했다. 전체 객체 대조에서 자유 finding 두 개의 `meaning_keys`만 바뀌었다. 원래 text/scope/provided blocks/실행 ID, 명시 gap 소유, 자동 c47 의미, 운영 의미 16개, 후보·원문·구 conjunction·질문·모델·설정은 고정했다. 응답 재생은 새 자동 판단 성과가 아니다.
- owner 이후 새 join 한 번: source 응답 1개와 국소 12개를 정확 재사용했다. 모델은 다시 satisfied/complete, c47와 기존 정상 의미 보존, eligible21/blocked0이다. 공백 1은 기관 header·업무 본문으로 해소했으나 공백 0은 다시 b32/c47로 해소하고 원 지적을 ‘번호판 변경 관련 서류 존재’로 바꿔 해석했다. 추가 서류가 없음을 뜻할 수 있다는 추정도 남았다. **기록 수정은 성립하지만 의미 해소 개선은 미확인**이다. 동일 변형을 재시도하지 않았다.

합의 기준은 `r05-guidance-scope-v1`: 문서의 담당·제외·서류를 종합 안내하고 복합 처리·용어 대응의 미확인을 구분한다. 모든 기관의 완전한 권한 증명이나 새 정답 기준을 추가하지 않았다. 독립 평가는 노출된 저장 자료에 대한 비맹검 AI 대조이며 실제 사람 시험·공식 점수·새 judge가 아니다.

owner 이후 QA 내용도 추가 호출 없이 대조했다. 기존 기본 QA payload와 **assessment_id를 제외한 의미 내용이 동일**했다. 새 승인 스냅샷·QA·검색·개념·교정을 실행할 실질 입력 변화가 없어 추가 실행하지 않았다. 전체 R05/제품과 기존 #616/#617/#620은 미완료로 남긴다.

## 호출·토큰·시간

review는 `qwen3.8:27b-q4_K_M` (digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`), 개념 생성은 `gemma4:31b-it-q4_K_M` (digest `6316f0629137b426c9d9b853ffc4c8209589f30ee39aebede6285096c0ff47e7`)이다. 실행 context 49,152, review 출력 한도 8,192, 개념 출력 한도 512, temperature 0, think=false, timeout 1,800초를 유지했다. 응답 `elapsed_s`는 순수 GPU 추론 벤치마크가 아니다.

제품 로컬 runtime은 `ollama`, endpoint `http://localhost:11434`이며 실제 requested/executed limits를 대조했다. 임베딩은 `BAAI/bge-m3`, device=`cpu`, 기존 로컬 파일만 로드했다. 상위 연구는 보존된 `/Applications/Ollama.app/Contents/Resources/llama-server` native 엔진의 별도 port 11435 실행 산출물이고, 이번 제품은 Ollama API를 통한 기존 제품함수 연결 진단이다. 두 실행 엔진의 품질·속도 우월성을 비교하지 않았다. 근거는 `runtime_evidence.json`의 제품 `/generation`, `/request_configuration`, `/requested_limits`, `/executed_limits`, `/embedding` 및 연구 handoff `/runtime`, `/settings`이고, 원 기록은 `qa_run.json`과 `handoff.json`이다.

아래 토큰은 provider의 실제 응답 metadata이며 입력 예산 추정치가 아니다. 새 모델 시간과 재사용에 붙은 원 응답 시간을 구분한다. 단계 driver 합계는 실행 구간 합계로 준비·AI 검토·대기 등 작업 전체 경과 시간이 아니다. 상위 연구 finding과 과거 추출/AI 정정은 새 제품 호출 합계에서 제외한다.

| 단계 | 새 호출 | 응답 재사용 | 새 입력 토큰 | 새 출력 토큰 | 새 모델 시간(초) | 단계 driver 시간(초) |
|---|---:|---:|---:|---:|---:|---:|
| A 실제 c47 편집 | 1 | 0 | 1,922 | 94 | 21.176 | 21.892 |
| B 자동 원문 재판정 | 1 | 0 | 2,393 | 662 | 53.063 | 55.253 |
| C R05 표현·결합·보존 | 11 | 2 | 86,157 | 3,968 | 709.329 | 737.638 |
| D 변경 개념·전체 그래프·기본 QA | 6 | 0 | 35,632 | 753 | 254.605 | 278.137 |
| E 기존 cb9 구성 QA 연결 | 1 | 1 | 14,136 | 1,048 | 142.004 | 143.695 |
| F owner 수정 후 응답 재생·join | 1 | 13 | 14,823 | 1,581 | 180.938 | 205.510 |
| 합계 | 21 | 16 | 155,063 | 8,106 | 1361.114 | 1442.125 |

D 6회는 변경 개념 4회(입력 18,354/출력 77/모델 107.272초)와 그래프 필터·기본 QA 2회(입력 17,278/출력 676/모델 147.333초)다. E의 필터 재사용은 기존 순위 재생과 함께 기록했다. F 재사용 13건은 실제 source 응답 1개와 국소 표현 응답 12개다.

재사용 metadata의 아래 값은 원 생성 시의 토큰·시간이며 이번 새 생성 비용으로 더하지 않는다. 새로 실행한 검수·교정으로도 세지 않는다.

| 재사용 단계 | 건수 | 원 응답 입력/출력 토큰 | 원 응답 모델 시간(초) |
|---|---:|---:|---:|
| R05_assess | 2 | 8,318 / 475 | 74.297 |
| cb9_QA_connection | 1 | 3,346 / 51 | 32.009 |
| owner_connector_replay_join | 13 | 82,039 / 3,858 | 679.155 |

## 검증·재현·보존

수정 전 관련 기존 검사 10개는 18.61초에 통과했다. 수정 후 좁은 회귀검사 12개는 21.77초에 통과했다. 신규 두 param은 v4/v8에서 자유 gap 미귀속, 명시 gap 소유, scope/provided/text/실행 ID 보존을 확인한다. 실제 source 응답 재생은 과거 v6 기록의 연결도 대조했다. 테스트 통과를 의미 품질 성공으로 세지 않았다. `git diff --check`를 통과하고 보고 JSON을 파싱해 해석된 문자열의 의도하지 않은 리터럴 `\n` 잔여가 없음을 확인했다.

실제 driver 원본 위치: `/Users/hyeongi/.codex/worktrees/business-requirement-answer-flow/Civil-Complaints-System/data/knowledge/evaluations/business_auto_finding_edit_20261011`.

영구 보존 위치: `/Users/hyeongi/.codex/artifacts/business-auto-finding-edit-20261011/before_owner_fix`와 `/Users/hyeongi/.codex/artifacts/business-auto-finding-edit-20261011/final`. before_owner_fix에는 기존 D·cb9 사본·동결·수정 전 app Python 360개를 보존했고, final에는 각 단계 DB 사본·원 요청/응답/단위·계보·감사·driver·해시·수정 후 코드 사본을 보존한다. 원본/연구 checkout은 읽기 전용으로 사용했고 기존 DB SHA를 재확인했다. 제품이 적재한 Qwen/Gemma는 내렸고 Ollama ps는 비었다.

| 실제 실행·대조 driver | SHA-256 |
|---|---|
| diagnose.py | `64ec6d6c2ebe0282c13c4f5f7eceaf7294f4d88b2ea679ed0d23ef9fea52b8a3` |
| source_reassess.py | `acdb261b576b2eecb08a00bfba42dab5f234261392e705ef2e8342d28b26a6e1` |
| assess_r05.py | `0d89e12d3ff88156467a9a1c1233732cc5bf4f79fde7815c05b2224ef77b8101` |
| snapshot_qa.py | `c46fe16f60f2da93ca56d05b247b97373896a49587ff2c127bdfde07026923e1` |
| connect_cb9.py | `73e8ec6323cbad7e46eb35bfd73b7d94094d2f683cd65f7fb6b02e01583656a4` |
| join_reuse_preflight.py | `fc9525895492631bff6cb7cc21d7bfff513e6d7e4529406d2f50256dc96ee6c6` |
| owner_replay_join.py | `9533e785256c1eb0640a9d6c054a6a5c3d69d9adf243c5539050b17e53a7ec65` |

초기 no-model join 사전 대조는 None service의 저장 경계에서 한 번 실패했다. 실제 모델·DB 변경 없이 저장을 no-op으로 고친 local harness가 국소 12개/새 join 1개 요청 대조를 완료했다. 실제 owner join과 사전 대조는 system·schema·참조맵·JSON 객체가 같지만 사용자 메시지 직렬화 순서가 달랐다. exact cache 조건을 느슨하게 하지 않았고 엄격한 문자열 단독 A/B 우월성을 주장하지 않는다.

`executed_driver_manifest.json`, `execution_metrics.json`, `reuse_provenance_clarification.json`, `owner_replay_join/source_replay_audit.json`과 `owner_replay_join/qa_payload_comparison.json`이 상세 근거다. 실행 원본은 당시 checkout/resource 경로를 전제로 하며 중복 실행 방지 assert를 포함한다. 완료 기록을 덮어쓰지 않고 새 재현 사본에서 사용해야 한다. driver 파일 보존은 신규 실행이나 반복 실험을 뜻하지 않는다.

[구조화 요약](business_auto_finding_edit_20261011.json). 현재 채택 범위는 한 줄 기록 계약 수정뿐이다. 남은 실패 경계는 공백 해소의 의미 일치와 QA의 구체적이고 모순 없는 미확인 설명이며, gold 덮어쓰기·새 검수층·추가 prompt 탐색으로 통과시키지 않았다.
