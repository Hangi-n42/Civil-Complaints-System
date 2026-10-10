# 과거 원문 재판정의 실제 제공 범위 복원

2026-10-11. 기존 #616 후속이며 시작 commit은 `b97d214631ceb29962c966e3daa31f9eb968799b`다. 조사 범위를 현재 종합입력에 전달하는 코드 변경은 채택한다. 같은 입력의 실제 join 1회에서는 핵심 의미 개선이 0이므로 전체 R05 완료나 자동 오류 발견 성과로 집계하지 않는다. A 연구 누적 4를 유지하며 A05를 추가하지 않는다.

## 진행 이유와 변경

과거 source unit `1f3345c4ec084e2184da588d95b6e97f`의 실제 messages/reference_map/evidence_reference_map은 현재 실행의 reusable_units에 보존돼 있다. 그러나 `inspection_summaries`는 source.reassessment_history의 previous/output/unit_id만 읽어, 실제 제공 범위를 종합입력으로 전달하지 않았다. 기록이 실제로 없는 경우와 unit에 보존된 경우를 구분하는 것이 이번 변경의 목적이다. 정상 의미를 다시 생성하거나 기존 finding을 수동 정정하지 않는다.

기존 조사 요약과 호출만 수정했다. source.reassessment_history에 제공·대상·선택 의미·버전 범위가 이미 있으면 그대로 재사용한다. 없으면 현재 run.units/reusable_units의 정확한 unit ID만 조회한다. 메시지의 원문 패킷과 참조 맵·근거 맵, 실제 원문 ID·버전·parse·구간·문자열·위치, 선택 previous 의미를 대조한다. 기록이 없거나 불일치하면 unavailable로 남기며 examined나 성공 상태에서 제공 범위를 추정하지 않는다. 부모 DB 탐색, 새 원문 조사, 모델 스키마·프롬프트 변경은 없다.

1f3345의 실제 범위는 제공 5개, 대상 b32 1개, context_only 부모 문맥 4개, 선택 의미 plate_change_documents 1개, 버전 1개·parse 1개다. 이는 과거 요청 범위다. 원기록에 inspection_status가 없어 null을 유지하며 examined_block_ids는 model_report로 표시한다. 원문 해석의 정확성, 실제 읽기 완료, 전체 요구 완료로 승격하지 않는다. 원래 unit·source 의미·finding ID/본문/kind·재판정 이력은 수정하지 않는다.

## 작은 검사와 실제 입력 대조

신규 경계 검사 13개가 2.97초에 통과했다. 정확 범위 복원, 메시지/맵/문자열/버전/parse/구간/위치/선택 의미/ID 불일치, 기록 없는 legacy, 기존 완전 receipt 보존, 기존 join 전달과 비승격을 확인했다. 실제 1f3345는 아래 제품 preflight 및 실제 join에서 별도로 확인했다. 이전 통과 19개와 전수 검사를 반복하지 않았다.

preflight run `fd185c99888c4a59944e66b8d7012763`은 모델 호출 0회다. 기존 lifecycle actual_join_v4와 동일한 저장 source, 활성 후보 119개, 원문 171개, 원문 의미 17개, 개념, 질문·공개 항목·설정 및 국소 응답 12개를 사용했다. 국소 messages/schema/reference/configuration/요청·실행 한도가 정확히 일치했다. 종합입력에서 바뀐 필드는 source_inspections 하나다. system 문구·schema·reference_map·설정·한도는 같다. b97의 새 “제출해야” 재작성 결과는 사용하지 않았다.

입력과 출력 한도 합계의 기존 추정식 결과는 49,071이며 컨텍스트 한도 49,152 안이다. 이는 utf8_bytes/2+output+1000 추정으로 실제 provider 토큰이 아니다. 동일 preflight 요청과 정확히 일치하는 제품 start→assess의 새 join 1회만 조율 승인에 따라 실행했다. 기대 정답·라벨·수동 정정·새 평가 기준을 모델 입력에 추가하지 않았다.

## 실제 결과와 실패 경계

실제 run은 `9da0802dc5794b4b9fd6edb196920dd3`, join unit은 `62a98e50fa394797b7dae3325f2d69e1`다. 전송·파싱은 완료됐지만 원래 지적 대상과 해소 근거의 의미 대조에서 실패했다.

- finding 0의 원래 지적은 “번호판 변경을 수반하지 않는 이전등록의 구비서류 요건이 제공된 원문에 없다”다. 새 응답도 plate_change_documents/c47/b32의 번호판 변경 구비서류와 지역 번호 조건만 근거로 resolved 처리했다. 이유 역시 “번호판 변경 시 구비서류…c47이 이를 정확히 표현함”이다. 공통·비번호변경 서류를 번호변경 서류로 바꿔 해소한 동일 오판이다. 기존 입력에는 공통서류 b27도 있지만 이 해소 근거에서 사용하지 않았다.
- finding 1은 실제 5개 기관 표의 기관명·자가용 범위·업무 및 제외 15개 구간으로 해소했다. 이전 실행과 같은 방향이며 신규 개선으로 세지 않는다.
- 정상 직접 제외 결합 3개는 동일 문장·근거와 supported/located 상태를 보존했다. 두 복합 처리 결합도 supported로 유지했다. k1은 b139/b146의 번호판 교부 기간을 번호판 변경 수반 이전등록 처리의 직접 지지로 채택했다. 이번 인용은 교부·변경·재발급·재봉인 사이의 용어 연결이나 복합 처리 전제를 별도로 확인하지 않는다. 이 supported 라벨만으로 해당 연결 또는 전체 R05를 확정할 수 없다.
- 기존 표현 판정 12개와 원문 필드 판정 12개의 값, dependencies와 eligible 21개가 이전 actual_join_v4와 같다. c47의 구비항목 및 지역 번호 한정 반납 후 변경 두 의미, 다른 정상 source와 후보를 보존했다. 원문 의미 17개·후보 119개·원문 171개·개념·과거 finding 본문/kind와 재판정 이력은 그대로다. preservation_checks의 이유는 새 응답이므로 이전과 문자 그대로 같다는 주장은 하지 않는다.

응답은 satisfied=true, conjunctions_satisfied=true, source_completeness=complete를 반환했다. 위 finding 0 실패 때문에 이를 의미 성공으로 인정하지 않는다. 실제 기록의 전달 누락과 이번 코드의 전달 회복은 확인했다. 그 누락만 복원하면 오판이 해소된다는 가설은 이번 고정 비교에서 성립하지 않았다. 이전 오판의 유일 원인이 누락이었다는 인과는 확인 불가다.

## 비용·보존·후속

| 구분 | 신규 생성 | 정확 재사용 | 실제 입력/출력 토큰 | 모델 응답 시간 | 실행 driver 시간 |
|---|---:|---:|---:|---:|---:|
| preflight | 0 | 국소 12 | 신규 0 | 신규 0 | 20.616612초 |
| 실제 join | 1 | 국소 12 | 17,353 / 3,012 | 272.712481초 | 297.087996초 |

모델은 기존 qwen3.8:27b-q4_K_M, temperature 0, think=false, timeout 1,800초, 출력 한도 8,192와 컨텍스트 49,152를 유지했다. 재사용 응답의 과거 비용은 신규 비용에 더하지 않는다. driver 시간은 해당 실행 구간이며 코드 작성·전체 준비·검토 시간을 포함하지 않는다. 실행 후 소유 Qwen을 내렸고 Ollama /api/ps 모델 0을 확인했다.

같은 오판이 반복돼 QA, source 재판정, 편집, 개념, 추출, 추가 join/judge, 프롬프트 변형·재시도는 모두 0회로 종료했다. raw 응답과 서버 최종 판정, 입력 대조·기준·DB·동결 코드·재현 harness·파일별 해시를 별도 archive에 보존한다. 원본 actual_join_v4 DB/source/result 해시는 유지됐다. 기존 b97과 모든 이전 실행 자료를 덮어쓰지 않는다.

보존 위치는 `/Users/hyeongi/.codex/artifacts/business-historical-inspection-scope-20261011/v1`이며 구조화 보고는 동명 JSON이다. #616을 갱신하고 #616/#617/#620은 미완료 결과 때문에 열린 상태로 유지한다. 이번 전달 계약만 기존 제품 branch에 반영하며 다른 연구 branch의 채택·push와 분리한다. 다음 작업은 새 실행 없이 대기다. 현재 사용자 결정이 필요한 사항 없음.
