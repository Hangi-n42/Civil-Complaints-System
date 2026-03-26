# Week2 ADMIN_UNIT 오탐 감소 Diff 리포트

- 생성시각: 2026-03-27T02:02:28.519989
- 비교건수: 50
- Before pred: docs/40_delivery/week2/artifacts/baseline_before_admin_unit_fix/be1_structured_pred_50.json
- After pred: docs/40_delivery/week2/artifacts/be1_structured_pred_50.json

## 핵심 지표

- ADMIN_UNIT 총 개수: 1023 -> 12
- implausible ADMIN_UNIT(오탐 추정): 1020 -> 0
- 오탐 감소량: 1020 (100.0%)
- 오탐 케이스 수: 50 -> 0

## 상위 제거 오탐 토큰

- 국립아시: 49
- 혹시: 42
- 그러면: 35
- 주시: 31
- 되십시: 26
- 잠시: 26
- 다시: 20
- 하시: 18
- 하면: 18
- 말씀하시: 17
- 혹시라도: 14
- 정도: 13
- 맞으시: 13
- 되시: 12
- 성함과: 12
- 말씀이시: 12
- 되면: 11
- 하시면: 11
- 아니면: 11
- 별도: 10

## 샘플 케이스 변화 (최대 10건)

- case_id=000012 | before=18 | after=0 | removed=18
  - removed: 정도, 안타깝게도, 단체이셔도, 고객님들과, 예매도, 단체이면, 주시더라도, 하시, 되면, 전화하시
- case_id=000021 | before=24 | after=1 | removed=23
  - removed: 하면, 전시, 모시, 혹시라도, 원하시, 수도, 참고하시면, 방문하시, 정도, 별도
- case_id=001555 | before=33 | after=1 | removed=33
  - removed: 국립아시, 아니면, 혹시, 성인이시군, 그러시면, 전시, 관람하시면, 그러면, 관람과, 소요시
- case_id=002465 | before=24 | after=0 | removed=24
  - removed: 국립아시, 얼굴과, 그러면, 보이면, 누군, 하면, 있으면, 혹시, 말씀하시, 친구
- case_id=002466 | before=17 | after=0 | removed=17
  - removed: 국립아시, 다시, 그러면, 혹시, 통화로도, 잠시, 주시, 원하시, 하시, 취소하시
- case_id=002467 | before=20 | after=0 | removed=20
  - removed: 국립아시, 혹시, 신청하시, 잠시, 일도, 그러면, 예매해주시면, 하면, 화면, 주시
- case_id=002468 | before=25 | after=0 | removed=25
  - removed: 국립아시, 혹시, 해봐드려도, 그러시면, 성함과, 말씀해주시, 고객님이시, 잠시, 주시, 하시면
- case_id=002469 | before=21 | after=2 | removed=21
  - removed: 국립아시, 사슴과, 상영하시, 말씀이시, 어르신들도, 혹시, 별도, 참여하시면, 하면, 모시
- case_id=002470 | before=16 | after=0 | removed=16
  - removed: 국립아시, 말씀하시, 그러시면, 잠시, 주시, 취소해드리면, 취소하시, 되면, 하도, 여쭤봐도
- case_id=002471 | before=23 | after=0 | removed=23
  - removed: 국립아시, 전시, 혹시, 말씀하시, 방문하시, 해주시면, 가시면, 해도, 아무래도, 그러면
