# 실제 공개 민원 조사 자료

- 상세 보고서: [실제 민원 확보와 영향 검토](../../../docs/70_research/company_knowledge/real_complaints_and_impact_demo_2026-09-29.md)
- 명세: [sources.json](sources.json)
- 상태: 조사 자료 확보. 지식 계층에 반입·활성화하지 않음.

## 사례 구분

| 사례 ID | 자료 유형 | 입력·비교 자료 |
|---|---|---|
| `jeju_lh_deposit_question` | LH 관련 시민 문의, 제주 주거복지센터 접수 | 원문 본문·기관 답변 분리 |
| `hanam_lh_single_household` | LH 관련 시민 민원, 하남시 접수 | 원문 본문·기관 답변 분리 |
| `acrc_lh_unit_change` | LH가 피신청인인 권익위 결정문 | 신청서 원문이 아닌 기관 작성 사건 기록 |
| `dobong_1127_complaint` | 도봉구 실제 노선 개편 민원 | 시민 원문·기관 답변·시민 제안 지도 4장 |

- LH 자체 민원 조회는 본인인증으로 연결. 직접 접수 신청서 원문 미확보.
- 원본과 추출 텍스트: `data/knowledge/raw/demo_complaints_20260929/`.
- `*_input.txt`: 공개 본문의 표시 텍스트. 문장 재작성 없이 공백·줄바꿈 정규화, 작성자 메타데이터 제외.
- `*_reference_answer.txt`: 기관의 실제 답변. 생성 입력과 분리하며 현재 규정이나 절대 정답으로 간주하지 않음.
- `acrc_lh_unit_change.pdf`: 결정문 8쪽. 신청 내용 1~2쪽, 사실 2~3쪽, 판단 4쪽, 당시 규정 5~7쪽.
- `IMG_0258.jpeg`, `IMG_0259.jpeg`, `IMG_0262.jpeg`, `IMG_0261.jpeg`: 시민이 첨부한 개략 노선 변경 지도. 정확한 정차 목록·운행 가능성이 확정된 자료 아님.
- `seoul_route_order_20260902.xlsx`, `seoul_stops_20260902.xlsx`: 민원 접수 직전 기준의 공식 자료.
- `1127_baseline_20260902.json`: 노선 XLSX에서 추출한 1127번 60행. 제안 변경안이 아님.
- 2025년 도봉 정류장 변경과 2026년 노선 개편 민원은 별도 사건. 이전 자료는 `configs/knowledge/demo_selection_20260929/sources.json` 참조.

원문은 기존 Git 제외 경로에 보관. 시연 시 실제 접수기관·작성 시점·자료 유형을 표시하고 개인정보 메타데이터는 노출하지 않음. 코드·PRD·고정 평가 과제는 변경하지 않음.
