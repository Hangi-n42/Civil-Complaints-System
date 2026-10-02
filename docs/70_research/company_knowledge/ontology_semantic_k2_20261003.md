# K2: 명제와 유형 연결의 독립 판정

- 관련 이슈: #570, 상위 #534/#539
- 이유: J3는 정상 입주자 명제를 주택 유형에 연결했지만 놓쳤고, supported와 content_error를 중복 생성했다. 입력을 더 늘리는 대신 기존 Critic 계약을 명확히 분리한다.
- 변경: recipe v44/checks-v1에서 semantic_checks가 명제·정의 전체 판단의 단일 근거다. modeled 관계는 subject/object binding_checks가 필수이며 실제 제공된 타입 정의와 대조한다. 유효 refuted check에서만 content_error 또는 endpoint를 한 번 도출한다.
- 경계: 주후보의 별도 content_error/endpoint 출력은 생성 schema에서 제한하고 normalizer에서도 격리한다. 비교 후보·계층의 별도 쟁점과 evidence_error/alignment/source_absent 등은 유지한다. 누락/잘못된 연결 정의는 해당 후보만 pending. 새 연결은 기존 지문 판정을 재사용하지 못하며 A3의 기존 binding_validation/endpoint 차단을 사용한다.
- unknown: 내용 오류로 확정하지 않으며 새 계약에서는 자동 Revision 대상도 아니다. primary 전체를 수정하던 빈 대상 fallback도 제외했다. 실제 evidence_error가 별도로 있으면 그 원인으로 수정할 수 있다. unknown의 근거 없는 명시 보류는 허용하되 supported/refuted는 원문 근거가 필요하다.
- 프롬프트: 누적된 중복 지시를 한 공통 검수 계약과 짧은 역할별 지시로 정리. 동등 조건 표현과 역할 추상화를 허용하며 정의 자체가 주장한 조건 누락·원문 밖 사실 추가는 오류로 구분한다.
- 확인: 관련 4개 파일 170 통과, 기존 serializer 경고 13개. 정상 명제/오류 연결과 오류 명제/정상 연결 분리, unknown 오류 미생성·Revision 0/A3 보류, missing binding 격리, 과거 모순 응답 실패 보존, 생성 schema와 후보별 지문 검증 확인. 실제 모델 호출 0.
- 테스트 변경: 별도 전체 judgment 대신 세부 판정으로 mock 오류를 지정. 주후보 중복 issue 주입 검사는 pending 격리 그대로 확인. 타입→어휘 수정 후 관계는 정확한 '연결 유형 정의가 이번 검수에 제공되지 않음' 오류와 판정 제거를 검증하고 정상 관측의 유효 판정 경계를 유지한다.
- 한계/다음: 서버 계약 통과는 모델의 의미 판정 성공이 아니다. K3에서 후보별 수정과 원명제를 유지하는 한정 Builder 교정을 연결하고 K4에서 실제 효과를 확인한다. 현재 사용자 결정이 필요한 사항 없음.
