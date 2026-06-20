# request_segments ?? B Shadow 100? ?? ??? ??
JSONL ?? ??: `reports/request_segment_llm_condition_b_shadow_100_review.jsonl`
?? ?: `human_judgment`? `pass / partial / fail / unsure` ? ??? ?????.
## 1. assist_limited_safe_candidate / 501472
- ??: 4대보험 신고 관련 및 근로계약서 작성 관련
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 26.28?
- ?? ???: 4대보험 신고 관련 및 근로계약서 작성 관련 1. 한 달 총 근로시간이 64시간(8일*8시간)으로 4대보험 신고 여부 2. 근로계약서상으로 근무일을 2019.02.18.~2019.02.27.으로 작성하는 것과 2019.02.18.~2019.02.22./2019.02.25.~2019.02.27.로 작성 시 차이가 있는지요?
- rule_segments:
  - 근로계약서상으로 근무일을 2019.02.18.~2019.02.27.으로 작성하는 것과 2019.02.18.~2019.02.22./2019.02.25.~2019.02.27.로 작성 시 차이가 있는지요?
- llm_segments:
  - 4대보험 신고 여부 확인 (한 달 총 근로시간 64시간 기준)
  - 근로계약서 작성 시 근무일 범위 차이 확인
- restored_evidence_texts:
  - 1. 한 달 총 근로시간이 64시간(8일*8시간)으로 4대보험 신고 여부
  - 2. 근로계약서상으로 근무일을 2019.02.18.~2019.02.27.으로 작성하는 것과 2019.02.18.~2019.02.22./2019.02.25.~2019.02.27.로 작성 시 차이가 있는지요?
- human_judgment: 
- human_note: 

## 2. assist_limited_safe_candidate / 300927
- ??: 발코니 바닥 해체허가(신고) 관련 문의
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 13.15?
- ?? ???: 발코니 바닥 해체허가(신고) 관련 문의 1. 건축법 제2조제1항제7호에 따른 주요구조부란 "내력벽, 기둥, 바닥, 보, 지붕틀 및 주계단을 말한다. 다만, 사이 기둥, 최하층 바닥, 작은 보, 차양, 옥외 계단, 그밖에 이와 유사한 것으로 건축물의 구조상 중요하지 아니한 부분은 제외한다"라고 명시되어 있습니다. 이에 따라 10.4m x 1.4m 크기의 발코니 바닥은 건축물의 구조상 중요하지 아니한 부분으로 판단할 수 있는지  2. 발코니 바닥을 주요구조부로 볼 수 있는지와 음식물 이동용 덤웨이터 설치를 위하여 2층부터 6층의 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지  3. 발코니 바닥은 건축물의 구조상 중요하지 아니한 부분으로 판단될 시 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지
- rule_segments:
  - 음식물 이동용 덤웨이터 설치를 위하여 2층부터 6층의 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지
  - 발코니 바닥은 건축물의 구조상 중요하지 아니한 부분으로 판단될 시 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지
- llm_segments:
  - 발코니 바닥 해체 허가(신고) 대상 여부 문의
- restored_evidence_texts:
  - 발코니 바닥 해체허가(신고) 관련 문의
  - 음식물 이동용 덤웨이터 설치를 위하여 2층부터 6층의 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지
  - 3. 발코니 바닥은 건축물의 구조상 중요하지 아니한 부분으로 판단될 시 발코니 바닥에 1.1m x 0.9m 크기의 절단이 발생할 경우 해체 허가(신고) 대상인지
- human_judgment: 
- human_note: 

## 3. assist_limited_safe_candidate / 001585
- ??: 4월 21일에 소풍을 가려하는데요.
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 10.53?
- ?? ???: 4월 21일에 소풍을 가려하는데요. 4월 21일에 소풍을 가려하는데요. 네, 여보세요. 네, 저희 4월 21일에요. 유치원에서 소풍을 가려고 하는데요. 한 200명 정도가 돼요. 근데 혹시 어떻게 예약을 하고 연락을 드려야 할까요? 아 홈페이지 통해서요? 아 네, 네. 아 정원이 180명. 아 네, 네, 네. 아, 단체가 아니고. 연령대가 음 3살부터 7살이요. 아 그럼 거기서 이제 2명이 나오는 거죠? 아 네,네, 알겠습니다. 네, 알겠습니다. 감사합니다.
- rule_segments:
  - 근데 혹시 어떻게 예약을 하고 연락을 드려야 할까요?
  - 아 홈페이지 통해서요?
  - 아 그럼 거기서 이제 2명이 나오는 거죠?
- llm_segments:
  - 4월 21일 소풍 예약 방법 문의
- restored_evidence_texts:
  - 네, 여보세요. 네, 저희 4월 21일에요. 유치원에서 소풍을 가려고 하는데요. 한 200명 정도가 돼요. 근데 혹시 어떻게 예약을 하고 연락을 드려야 할까요?
- human_judgment: 
- human_note: 

## 4. assist_limited_safe_candidate / 700210
- ??: 
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 15.95?
- ?? ???: (현황) OO 시설물의 건설은 ‘AOO 공단’이 시공하고, 시설물 준공 후에는 ‘BOO 공사’가 인수하여 유지 보수 업무를 수행 (문제점) BOO 공사가 시설물을 인수하여 업무를 수행하던 중 수감 기관으로부터 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반 사항이 발생함 1. BOO 공사가 법 위반 사항을 인지하지 못하고, 시설물을 인수한 후에 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반이 발생하였을 경우 법 위반 책임은 누구에게 있는지? 2. BOO 공사가 법 위반 사항을 인지하고 개선 요구를 하였음에도 개선이 되지 않은 채로 인수한 후에 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반이 발생하였을 경우 법 위반 책임은 누구에게 있는지? 3. 설계 시점과 시공 시점의 법 기준이 상이한 경우, 시설물 인수 당시의 법 기준에 맞게 시설물을 설치하여야 할 의무가 있는지?
- rule_segments:
  - BOO 공사가 법 위반 사항을 인지하고 개선 요구를 하였음에도 개선이 되지 않은 채로 인수한 후에 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반이 발생하였을 경우 법 위반 책임은 누구에게 있는지?
  - 설계 시점과 시공 시점의 법 기준이 상이한 경우, 시설물 인수 당시의 법 기준에 맞게 시설물을 설치하여야 할 의무가 있는지?
- llm_segments:
  - 법 위반 책임이 누구에게 있는지 확인해 주세요.
  - 시설물 인수 시 법 기준 준수 의무 확인 필요성.
- restored_evidence_texts:
  - 1. BOO 공사가 법 위반 사항을 인지하지 못하고, 시설물을 인수한 후에 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반이 발생하였을 경우 법 위반 책임은 누구에게 있는지?
  - 2. BOO 공사가 법 위반 사항을 인지하고 개선 요구를 하였음에도 개선이 되지 않은 채로 인수한 후에 점검을 받아 철도 시설물에 대한 ｢산업안전보건법｣ 위반이 발생하였을 경우 법 위반 책임은 누구에게 있는지?
  - 3. 설계 시점과 시공 시점의 법 기준이 상이한 경우, 시설물 인수 당시의 법 기준에 맞게 시설물을 설치하여야 할 의무가 있는지?
- human_judgment: 
- human_note: 

## 5. assist_limited_safe_candidate / 800815
- ??: 성남시내 주요 공원의 ▲▲▲ 조성관련 질의 및 건의 사항
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 16.96?
- ?? ???: 성남시내 주요 공원의 ▲▲▲ 조성관련 질의 및 건의 사항 먼저 국민 건강을 위해 주요 공원에 황톳길을 조성해 주셔서 대단히 감사드립니다. 이와 관련 몇 가지 문의 사항과 건의 사항이 있어 이 서류를 작성합니다. 1. 질의 사항 - 인터넷 블로그에 "▲▲공원 맨발 걷기 황톳길을 파보니 황토 밑에 콘크리트 타설과 부직포를 깐 후에 황토를 깔았다"며 사진까지 올린 기사를 보았습니다. 이 내용이 사실인지요 ? *** 맨발로 황토나 흙. 모랫길을 걷는 가장 큰 이유는 맨발과 땅속에 있는 음이온과의 접촉을 통해서 발생하는 접지 효과 때문이며, 그다음에 지압 효과나 기타 운동 효과 등입니다. 그런데 황톳길 밑에 콘크리트·자갈. 부직포 등을 공사하면 전혀 접지 효과를 누릴 수 없습니다.  - 황톳길에 조성된 황토는 100퍼센트 황토인가요. 혹은 황토와 여러 가지 다른 성분을 추가해서 만든 황토인가요 ?  2.
- rule_segments:
  - 이와 관련 몇 가지 문의 사항과 건의 사항이 있어 이 서류를 작성합니다.
  - 혹은 황토와 여러 가지 다른 성분을 추가해서 만든 황토인가요 ?
  - 부직포 등을 사용하지 않고 친환경적인 공법을 개발하여 주실 것을 요청합니다.
- llm_segments:
  - 황톳길 조성 관련 사실 확인 요청
  - 황톳길 황토 구성 성분 확인 요청
  - 친환경 공법 개발 건의
- restored_evidence_texts:
  - - 인터넷 블로그에 "▲▲공원 맨발 걷기 황톳길을 파보니 황토 밑에 콘크리트 타설과 부직포를 깐 후에 황토를 깔았다"며 사진까지 올린 기사를 보았습니다.
  - - 황톳길에 조성된 황토는 100퍼센트 황토인가요. 혹은 황토와 여러 가지 다른 성분을 추가해서 만든 황토인가요 ?
  - 기왕에 많은 예산을 들여서 국민 건강을 위해 황톳길을 조성할 경우, 향후에는 접지 효과가 없어지지 않도록 황토 밑에 흙을 제외한 콘크리트·자갈. 부직포 등을 사용하지 않고 친환경적인 공법을 개발하여 주실 것을 요청합니다.
- human_judgment: 
- human_note: 

## 6. assist_limited_safe_candidate / 002158
- ??: 네. 여보세요? 그 빨래 뮤지컬 예매하려고 하는데요. 네, 이게 여기 어디서 예매를 해야 돼요?
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 17.25?
- ?? ???: 네. 여보세요? 그 빨래 뮤지컬 예매하려고 하는데요. 네, 이게 여기 어디서 예매를 해야 돼요? 네. 여보세요? 그 빨래 뮤지컬 예매하려고 하는데요. 네, 이게 여기 어디서 예매를 해야 돼요? 네. 토요일이요. 네. 아 그러면 토요일 2시 타임 그 2개가 붙어 있는 자리예요? 네. 1층 M열 8, 9요? 네. 그러면 예매할게요. 네. ▲▲▲이고요. 네. ▲▲▲이고요. 카드는 ▲▲카드고요. ▲▲▲▲ ▲▲▲▲ 없어요. 없습니다. 네. 네. 여보세요? 네. 했는데 그게 좀 놓쳤나 봐요, 타이밍을. 네. 네. 2개월로 해주세요. 네. 네. 이거 티켓은 어떻게 수령해요? 네, 알겠습니다. 네.
- rule_segments:
  - 이게 여기 어디서 예매를 해야 돼요?
  - 아 그러면 토요일 2시 타임 그 2개가 붙어 있는 자리예요?
  - 2개월로 해주세요.
  - 이거 티켓은 어떻게 수령해요?
- llm_segments:
  - 빨래 뮤지컬 예매 장소를 알려주세요.
  - 토요일 2시 타임의 붙어 있는 좌석 예매 확인
  - 티켓 수령 방법 문의
- restored_evidence_texts:
  - 네. 여보세요? 그 빨래 뮤지컬 예매하려고 하는데요. 네, 이게 여기 어디서 예매를 해야 돼요?
  - 아 그러면 토요일 2시 타임 그 2개가 붙어 있는 자리예요?
  - 이거 티켓은 어떻게 수령해요?
- human_judgment: 
- human_note: 

## 7. assist_limited_safe_candidate / 701068
- ??: 
- fallback_reasons: strong_candidate_single_segment, numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 8.7?
- ?? ???: 자발적 퇴사, 연장근로 초과로 인한 퇴사는 실업급여 대상자, 궁금한 점은 10월 둘째 주부터 12월 둘째 주까지 초과 근무하지만 10, 11월 11, 12월 평균적으로는 초과근무 아님. 실업급여 가능할까요?
- rule_segments:
  - 실업급여 가능할까요?
- llm_segments:
  - 실업급여 가능할까요?
- restored_evidence_texts:
  - 자발적 퇴사, 연장근로 초과로 인한 퇴사는 실업급여 대상자, 궁금한 점은 10월 둘째 주부터 12월 둘째 주까지 초과 근무하지만 10, 11월 11, 12월 평균적으로는 초과근무 아님. 실업급여 가능할까요?
- human_judgment: 
- human_note: 

## 8. assist_limited_safe_candidate / 301527
- ??: 방화구획 설치 시 법취지에 맞는 구체적인 시공 방법에 대한 문의
- fallback_reasons: strong_candidate_single_segment, numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 16.36?
- ?? ???: 방화구획 설치 시 법취지에 맞는 구체적인 시공 방법에 대한 문의 방화구획 설치 시 법 취지에 맞는 구체적인 시공 방법에 대해 문의드립니다.  방화구획 등의 설치 (건축법 시행령 제46조) ① 법 제49조제2항 본문에 따라 주요구조부가 내화구조 또는 불연재료로 된 건축물로서 연면적이 1천 제곱미터를 넘는 것은 국토교통부령으로 정하는 기준에 따라 다음 각호의 구조물로 구획(이하 “방화구획”이라 한다)을 해야 한다. 1. 내화구조로 된 바닥 및 벽 2. 제64조제1항제1호ㆍ제2호에 따른 방화문 또는 자동방화셔터(국토교통부령으로 정하는 기준에 적합한 것을 말한다. 이하 같다)  위 법에 따라 내화구조로 된 바닥 및 벽으로 방화구획을 계획함에 있어서 철골구조의 경우 시공 현장에서 구체적인 시공 방법에 대한 논란이 있어 문의드립니다. 철골구조 보 부재(내화 3시간)와 방화벽(비내력벽 내화 2시간)이 만나는
- rule_segments:
  - 철골구조 보 부재(내화 3시간)와 방화벽(비내력벽 내화 2시간)이 만나는 부분에 대해 세부적인 지침 확인이 필요합니다.
- llm_segments:
  - 철골구조 보 부재(내화 3시간)와 방화벽(비내력벽 내화 2시간)이 만나는 부분의 구체적인 시공 방법 지침 확인 필요
- restored_evidence_texts:
  - 철골구조 보 부재(내화 3시간)와 방화벽(비내력벽 내화 2시간)이 만나는 부분에 대해 세부적인 지침 확인이 필요합니다.
- human_judgment: 
- human_note: 

## 9. assist_limited_safe_candidate / 301301
- ??: 방화구획 및 외벽 마감재 해체 관련 문의
- fallback_reasons: strong_candidate_single_segment, numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 9.77?
- ?? ???: 방화구획 및 외벽 마감재 해체 관련 문의 1. 방화구획을 해체할 시에 대수선에 해당(대수선 정의 중 대통령령)하여 해체 허가(신고) 대상입니다. 그 방화구획이 비내력벽인 경우에도 대수선에 해당하는 것으로 알고 있는데, 그렇다면 이 경우가 해체 허가(신고) 대상에도 포함이 되는지 문의드립니다.  2. 외벽 마감재 해체는 해체 허가(신고) 대상입니다. 여기서 외벽 마감재가 나사를 푸는 방식으로 제거된다면, 해체 허가(신고) 대상인지 문의드립니다.
- rule_segments:
  - 그 방화구획이 비내력벽인 경우에도 대수선에 해당하는 것으로 알고 있는데, 그렇다면 이 경우가 해체 허가(신고) 대상에도 포함이 되는지 문의드립니다.
- llm_segments:
  - 방화구획 해체 허가 대상 여부 문의
- restored_evidence_texts:
  - 1. 방화구획을 해체할 시에 대수선에 해당(대수선 정의 중 대통령령)하여 해체 허가(신고) 대상입니다. 그 방화구획이 비내력벽인 경우에도 대수선에 해당하는 것으로 알고 있는데, 그렇다면 이 경우가 해체 허가(신고) 대상에도 포함이 되는지 문의드립니다.
- human_judgment: 
- human_note: 

## 10. assist_limited_safe_candidate / 20036
- ??: 화성시 ▲▲ ▲▲▲▲▲ 건출물분양에관한법률위반
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 29.29?
- ?? ???: 화성시 ▲▲ ▲▲▲▲▲ 건출물분양에관한법률위반 화성시 ▲▲ ▲▲▲▲ ▲▲▲▲▲ 상가 설계변경과 관련하여 건축허가과에 문의드립니다. 안녕하세요. 고생이 많으십니다. 본 민원인은 화성시 ▲▲ ▲▲▲▲ ▲▲▲▲▲▲ ▲▲▲▲▲ 복합상가 수분양자입니다. ▲▲▲▲▲는 2022.12.21 화성시로부터 사용승인을 허가 받은 것으로 건축물대장을 통해 확인하였습니다. 사용승인이 완료되었다는 것은 공사가 완공되었다는 것으로 알고 민원인이 분양받은 호실 내부를 확인한 결과 입점하여 영업할 수 있는 상태가 아닙니다. 앞면 벽은 완전히 뚫려있고 당연히 출입문도 없습니다. 복도에 옆으로 칸막이만 쳐놓고 완공되었다고 사용승인을 받았다는 것은 받아들이기 힘든 부분입니다. 분양 당시에 받았던 층별 도면에도 옆벽과 앞 벽은 그려져 있습니다. 이에 분양 허가 시 제출된 설계 도면과 사용승인 시 제출된 12블록 5층 5063의 단면
- rule_segments:
  - 분양 시 설계도는 벽으로 구분되어 있었지만, 공사를 진행하면서 설계변경을 하였다면 수분양자 전원에게 변경 사항을 10일 전에 내용증명 우편으로 알리고 동의를 받은 후에 설계변경 신청을 해야 하는 절차를 받아야 합니다.
  - 이는, "건축물분양에 관한 법률 시행규칙 제8조 설계의 변경 제2항 3호인 "공사감리자가 건축허가를 받을 당시의 재료와동등하거나 그 이상이라고 판단한 내장 재료 및 외장재료의 변경"에 해당하는 설계변경으로, "건축물 분양에 관한 법률 제7조 2항 및 제10조 2항 6호에 해당하므로, 행정처분을 내려주시기 강력히 요청합니다.
- llm_segments:
  - 상가 설계 변경 과정에서 수분양자 전원에게 변경 사항을 알리지 않은 것은 건축물 분양에 관한 법률 위반으로 판단됩니다. 행정처분을 요청합니다.
  - 설계 변경 시 수분양자 동의 절차 미준수에 대한 조사와 처분 요청
- restored_evidence_texts:
  - 2) 분양 시 설계도는 벽으로 구분되어 있었지만, 공사를 진행하면서 설계변경을 하였다면 수분양자 전원에게 변경 사항을 10일 전에 내용증명 우편으로 알리고 동의를 받은 후에 설계변경 신청을 해야 하는 절차를 받아야 합니다.
  - 이는 <건축물의 분양에 관한 법률 제10조(벌칙)> 2항 6호를 위반한 것입니다.
  - 이는, "건축물분양에 관한 법률 시행규칙 제8조 설계의 변경 제2항 3호인 "공사감리자가 건축허가를 받을 당시의 재료와동등하거나 그 이상이라고 판단한 내장 재료 및 외장재료의 변경"에 해당하는 설계변경으로, "건축물 분양에 관한 법률 제7조 2항 및 제10조 2항 6호에 해당하므로, 행정처분을 내려주시기 강력히 요청합니다.
  - 하지만 분양자는 이러한 우편물을 현재까지 받은 적이 없고 준공심사 이후에 알게 되었습니다.
  - 또한 세현제삼차에서 지난 12월 동탄 ▲▲▲▲▲ 상가 분양자에게 우편 통보한 디자인 변경에 따른 외부 마감재 변경은 지난 2020년 8월 13일 허가 변경(2차)에 변경되었으나, 변경된 사항에 대해 분양받은 자 전원에게 동의를 받거나 알린 사항이 없이 이미 시공됐습니다.
- human_judgment: 
- human_note: 

## 11. assist_limited_safe_candidate / 6899347
- ??: 채권양도 질의
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 10.2?
- ?? ???: 채권양도 질의 1. 사업형태 : 구매사업  2. 계약당사자와의 관계 : 협력업체  3. 질의 내용  당사는 방위사업청과 구매사업을 체결한 계약당사자의 협력업체로서 계약당사자의 발주를 받아 구매 및 납품을 하였습니다.  하지만 납품이후 납품대금을 수령하지 못하는 상황입니다.  이때 양사가 채권양도에 상호합의하면 방위사업청 납품대금에 대하여 채권양도를 받을 수 있는지 궁금합니다.
- rule_segments:
  - 이때 양사가 채권양도에 상호합의하면 방위사업청 납품대금에 대하여 채권양도를 받을 수 있는지 궁금합니다.
- llm_segments:
  - 계약당사자의 납품대금에 대한 채권양도 가능 여부 문의
- restored_evidence_texts:
  - 이때 양사가 채권양도에 상호합의하면 방위사업청 납품대금에 대하여 채권양도를 받을 수 있는지 궁금합니다.
- human_judgment: 
- human_note: 

## 12. assist_limited_safe_candidate / 6905873
- ??: 고등학교 타 시.도 추가 배정은 어떻게 이루어지나요?
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 8.52?
- ?? ???: 고등학교 타 시.도 추가 배정은 어떻게 이루어지나요? 고등학교 타 시.도 추가 배정은 어떻게 이루어지나요?
- rule_segments:
  - 고등학교 타 시.도 추가 배정은 어떻게 이루어지나요?
- llm_segments:
  - 고등학교 타 시.도 추가 배정 방법을 알려주세요.
- restored_evidence_texts:
  - 고등학교 타 시.도 추가 배정은 어떻게 이루어지나요?
- human_judgment: 
- human_note: 

## 13. assist_limited_safe_candidate / 301057
- ??: 토지거래허가구역 내 주택임대사업자의 소유권 변동
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 9.28?
- ?? ???: 토지거래허가구역 내 주택임대사업자의 소유권 변동 토지거래허가구역 내 빌라를 소유하고 있는 주택임대사업자의 매매 가능 여부 1) 주택임대사업자에게 매매 2) 개인에게 매매
- rule_segments:
  - 토지거래허가구역 내 빌라를 소유하고 있는 주택임대사업자의 매매 가능 여부
- llm_segments:
  - 토지거래허가구역 내 빌라 매매 가능 여부 확인
- restored_evidence_texts:
  - 토지거래허가구역 내 빌라를 소유하고 있는 주택임대사업자의 매매 가능 여부
- human_judgment: 
- human_note: 

## 14. assist_limited_safe_candidate / 300016
- ??: 기존주택 처분 관련 질의
- fallback_reasons: numbered_under_split, possible_over_split, weak_request_signal
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 24.5?
- ?? ???: 기존주택 처분 관련 질의 2018.12.11. 개정된 「주택공급에 관한 규칙」 제28조제8항을 적용받으면서 청약이 진행된 분양주택(민영)과 관련하여 "기존주택 처분 조건" 해당 여부 해석 문의드립니다.  (제28조8항과 11항) ⑧ 사업 주체는 투기과열지구, 청약과열지역, 수도권 및 광역시에서 제2항부터 제7항까지의 규정에 따라 추첨의 방법으로 입주자를 선정하는 주택 수보다 추첨 대상자가 많으면 다음 각호의 순서에 따라 입주자를 선정해야 한다. <신설 2018. 12. 11.> 1. 제2항 및 제4항 단서에 따라 추첨의 방법으로 공급되는 주택 수의 75퍼센트(소수점 이하는 올림 한다. )를 무주택세대구성원에게 공급한다. 2. 나머지 주택(제1호에 따라 무주택세대구성원에게 공급하고 남은 주택을 포함한다. )은 무주택세대구성원과 1주택을 소유한 세대에 속한 사람(기존 소유 주택 처분조건을 승낙한 사
- rule_segments:
  - 개정된 「주택공급에 관한 규칙」 제28조제8항을 적용받으면서 청약이 진행된 분양주택(민영)과 관련하여 "기존주택 처분 조건" 해당 여부 해석 문의드립니다.
  - 「부동산 거래 신고 등에 관한 법률」 제3조에 따른 신고
  - 기존 소유 주택 처분 서약의 내용이 "1주택 소유자로서 추첨의 방법으로 주택을 우선 공급 받는 경우"에 대해 입주가능일로부터 6개월 이내에 처분 완료하는 조건인데, 질문의 경우 1순위 청약 당시 추첨의 방법으로 우선 공급 당첨이 된 것이 아니고 해당 청약 순위 자체가 미달로 주택 처분 서약과 상관없이 청약자 전원이 경쟁 없이 공급을 받게 되는 경우라고 생각되어 문의드립니다.
  - 최근 부동산 시장이 매우 급변하여 거래가 거의 이루어지지 않아 기존주택 처분 조건 해당 여부 판단이 중요하여
  - 많은 업무로 바쁘시지만 답변을 부탁드립니다.
- llm_segments:
  - 기존주택 처분 조건 적용 여부 문의 (청약 미달 시)
  - 기존주택 처분 조건 의무 무효 여부 확인
- restored_evidence_texts:
  - 해당 청약에서 "1주택 소유(주택 처분 서약)" 체크하여 1순위 해당 지역 청약을 신청하였으나, 1순위 해당 지역 미달로 주택공급을 받게 되는 경우 6개월 이내 기존주택처분 조건 의무가 무효화되는 것이 맞는지요?
  - 기존 소유 주택 처분 서약의 내용이 "1주택 소유자로서 추첨의 방법으로 주택을 우선 공급 받는 경우"에 대해 입주가능일로부터 6개월 이내에 처분 완료하는 조건인데, 질문의 경우 1순위 청약 당시 추첨의 방법으로 우선 공급 당첨이 된 것이 아니고 해당 청약 순위 자체가 미달로 주택 처분 서약과 상관없이 청약자 전원이 경쟁 없이 공급을 받게 되는 경우라고 생각되어 문의드립니다.
  - 기존 소유 주택 처분 서약의 내용이 "1주택 소유자로서 추첨의 방법으로 주택을 우선 공급 받는 경우"에 대해 입주가능일로부터 6개월 이내에 처분 완료하는 조건인데, 질문의 경우 1순위 청약 당시 추첨의 방법으로 우선 공급 당첨이 된 것이 아니고 해당 청약 순위 자체가 미달로 주택 처분 서약과 상관없이 청약자 전원이 경쟁 없이 공급을 받게 되는 경우라고 생각되어 문의드립니다.
- human_judgment: 
- human_note: 

## 15. assist_limited_safe_candidate / 300912
- ??: 아파트 정화조 기계실의 통기관 및 환기(배기)덕트 설치 관련 문제
- fallback_reasons: strong_candidate_single_segment, numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 14.54?
- ?? ???: 아파트 정화조 기계실의 통기관 및 환기(배기)덕트 설치 관련 문제 아파트 정화조 통기 및 환기 관련하여 질의 올립니다. 당 공사 현장 시공사는 아파트 정화조 통기관(벤트)을 정화조 기계실 환기(배기)덕트에 연결하여 옥상으로 배기하고자 하오나 사업 승인 조건에는 통기관 및 환기 시설 설치 시 옥상 등으로 설치해야 한다고 나와 있지 통기관(벤트)과 환기 시설을 서로 연결하여 사용하라는 내용은 없습니다.  - 국토교통부 고시 제2021-851호 기계설비 기술기준 [별표3] 환기설비의 설계 및 시공 기준(제8조 제3호 관련) 2.환기설비 설계 2.1 설계 기준 2.1.2 용도별 환기 (8) 정화조. - 개인하수처리시설의 설치 기준(제24조제3항 관련). - 건축기계설비공사 표준시방서.  위 내용을 찾아보았지만 명확하게 답이 없으며 일반적으로 기계설비 교육 관련 서적에는 통기 배관 상의 주의 사항으로 오
- rule_segments:
  - 정화조 통기관(벤트)을 정화조 기계실 환기(배기)덕트에 연결하여 옥상으로 배기하여도 되는지 의견 부탁드립니다.
- llm_segments:
  - 정화조 통기관(벤트)을 정화조 기계실 환기(배기)덕트에 연결하여 옥상으로 배기해도 되는지 확인 부탁드립니다.
- restored_evidence_texts:
  - 정화조 통기관(벤트)을 정화조 기계실 환기(배기)덕트에 연결하여 옥상으로 배기하여도 되는지 의견 부탁드립니다.
- human_judgment: 
- human_note: 

## 16. assist_limited_safe_candidate / 300309
- ??: 지역주택조합 조합원 자격 유지 건
- fallback_reasons: strong_candidate_single_segment, numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 11.67?
- ?? ???: 지역주택조합 조합원 자격 유지 건 안녕하세요. 미세먼지와 추위로 고생이 많으십니다.  지역주택조합의 조합원 자격을 조합설립인가 신청일부터 해당 조합주택의 입주 가능일까지 세대주를 포함한 세대원(세대주와 동일한 세대별 주민등록표에 등재되어 있지 아니한 세대주의 배우자 및 그 배우자와 동일한 세대를 이루고 있는 사람을 포함) 전원이 주택을 소유(「주택공급에 관한 규칙」 제2조 제7호에 따른 당첨자(당첨자의 지위를 승계한 자를 포함)의 지위를 포함)하고 있지 아니한 세대의 세대주이거나, 세대주를 포함한 세대원 중 1명에 한정하여 주거전용면적 85㎡ 이하의 주택 1채를 소유한 세대의 세대주로서, 조합설립인가 신청일 현재 해당 지역에 6개월 이상 계속하여 거주하여 온 사람으로 한정한다고 알고 있습니다.  1. 조합 가입 후 결혼하였고(배우자는 지역이 다름) 조합설립 후 1년 10개월 뒤 배우자의 지역으로
- rule_segments:
  - 이 경우에 조합원 자격이 유지되는지 알고 싶습니다.
- llm_segments:
  - 조합원 자격 유지 여부 확인 요청
- restored_evidence_texts:
  - 2. 이 경우에 조합원 자격이 유지되는지 알고 싶습니다.
- human_judgment: 
- human_note: 

## 17. assist_limited_safe_candidate / 002047
- ??: 아 네, 안녕하세요. 내일 그 저 ▲▲▲의 편지 표를 어 1명 거를 구하고 싶은데 그 제가 보니까 남아있는 표가 없고 휠체어서 가도 동반석 밖에
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 18.9?
- ?? ???: 아 네, 안녕하세요. 내일 그 저 ▲▲▲의 편지 표를 어 1명 거를 구하고 싶은데 그 제가 보니까 남아있는 표가 없고 휠체어서 가도 동반석 밖에 아 네, 안녕하세요. 내일 그 저 ▲▲▲의 편지 표를 어 1명 거를 구하고 싶은데 그 제가 보니까 남아있는 표가 없고 휠체어서 가도 동반석 밖에 안 남 아니, 표가 남은 좌석이 0으로 나오더라고요. 네, 맞습니다. 다리 수술을 받아가지고 양쪽을, 그래가지고 지금 이제 다리에 보조기를 착용하고 워커로 이렇게 이동을 하고 있거든요. 그래서 그 이제 이 장애인증이 그 확인이 필수인지 그게 궁금해서 전화드렸고요. 이제 저 같은 경우는 좀 걷는 게 불편해서. 네. 저 수술 확인서는 보여드릴 수 있어요, 10월달에. 네. 아 그 어 그러면 두 번째로 그 현장 구매에 뭐 표가 혹시 배분이 되어있는지 아니면 제가 이제 예매를 어 잔여석이 없어서 예매는 못해도 현장에 
- rule_segments:
  - 그래서 그 이제 이 장애인증이 그 확인이 필수인지 그게 궁금해서 전화드렸고요.
  - 아 그 어 그러면 두 번째로 그 현장 구매에 뭐 표가 혹시 배분이 되어있는지 아니면 제가 이제 예매를 어 잔여석이 없어서 예매는 못해도 현장에 가서 그 표를 살 수 있는지 그게 좀 궁금해요.
  - 아 그러면은 보통 현장에 가서 그 저는 혼자 볼 거여 가지고 혹시 그 이렇게 뭐 취소가 뭐 되기도 하나요, 1명씩 2명씩이라도?
- llm_segments:
  - 장애인증 확인 필수 여부 문의
  - 현장 구매 표 배분 여부 문의
  - 혼자 표 예매 가능 여부 문의
- restored_evidence_texts:
  - 다리 수술을 받아가지고 양쪽을, 그래가지고 지금 이제 다리에 보조기를 착용하고 워커로 이렇게 이동을 하고 있거든요. 그래서 그 이제 이 장애인증이 그 확인이 필수인지 그게 궁금해서 전화드렸고요. 이제 저 같은 경우는 좀 걷는 게 불편해서.
  - 아 그 어 그러면 두 번째로 그 현장 구매에 뭐 표가 혹시 배분이 되어있는지 아니면 제가 이제 예매를 어 잔여석이 없어서 예매는 못해도 현장에 가서 그 표를 살 수 있는지 그게 좀 궁금해요.
  - 아 그러면은 보통 현장에 가서 그 저는 혼자 볼 거여 가지고 혹시 그 이렇게 뭐 취소가 뭐 되기도 하나요, 1명씩 2명씩이라도?
- human_judgment: 
- human_note: 

## 18. assist_limited_safe_candidate / 300138
- ??: 지구단위계획구역 안에서의 가설건축물 질의
- fallback_reasons: strong_candidate_single_segment, heading_list_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 9.73?
- ?? ???: 지구단위계획구역 안에서의 가설건축물 질의 국토의 계획 및 이용에 관한 법률 제54조/시행령 제50조 2에서 지구단위계획구역이 적용되지 않는 가설 건축물은 총 3년의 존치 이후 연장이 불가하다고 나와 있는데, 문의 사항은 가설 건축물이 지구단위계획에 맞게 건축되어 있을 경우 3년 이후 계속 연장이 가능한지 궁금합니다.
- rule_segments:
  - 은 가설 건축물이 지구단위계획에 맞게 건축되어 있을 경우 3년 이후 계속 연장이 가능한지 궁금합니다.
- llm_segments:
  - 가설 건축물의 지구단위계획구역 내 연장 가능 여부 문의
- restored_evidence_texts:
  - 문의 사항은 가설 건축물이 지구단위계획에 맞게 건축되어 있을 경우 3년 이후 계속 연장이 가능한지 궁금합니다.
- human_judgment: 
- human_note: 

## 19. assist_limited_safe_candidate / 6907050
- ??: 문화유산 과학적 분석 - 재질별 연구사례
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 9.84?
- ?? ???: 문화유산 과학적 분석 - 재질별 연구사례 보존과학연구실에서 발간한 「문화유산 과학적 분석 - 재질별 연구 사례」는 무엇인지 궁금합니다.
- rule_segments:
  - 보존과학연구실에서 발간한 「문화유산 과학적 분석 - 재질별 연구 사례」는 무엇인지 궁금합니다.
- llm_segments:
  - 「문화유산 과학적 분석 - 재질별 연구 사례」에 대한 정보를 요청합니다.
- restored_evidence_texts:
  - 보존과학연구실에서 발간한 「문화유산 과학적 분석 - 재질별 연구 사례」는 무엇인지 궁금합니다.
- human_judgment: 
- human_note: 

## 20. assist_limited_safe_candidate / 6907251
- ??: 창업자멘토링
- fallback_reasons: numbered_under_split
- risk_tags: numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 10.61?
- ?? ???: 창업자멘토링 올해 신규로 창업한 영세사업자입니다. 사업자등록 시 창업자 멘토링 제도에 대해 들었습니다. 창업자 멘토링이 뭔 지, 어디에서 신청하는 지, 세무사가 직접 상담을 해주는 것인지 궁금합니다.
- rule_segments:
  - 창업자 멘토링이 뭔 지, 어디에서 신청하는 지, 세무사가 직접 상담을 해주는 것인지 궁금합니다.
- llm_segments:
  - 창업자 멘토링이 뭔 지, 어디에서 신청하는지 궁금합니다. 세무사 상담 여부도 알고 싶습니다.
- restored_evidence_texts:
  - 올해 신규로 창업한 영세사업자입니다. 사업자등록 시 창업자 멘토링 제도에 대해 들었습니다. 창업자 멘토링이 뭔 지, 어디에서 신청하는 지, 세무사가 직접 상담을 해주는 것인지 궁금합니다.
- human_judgment: 
- human_note: 

## 21. assist_limited_needs_review / 600282
- ??: 석면슬레이트 철거 및 처리 지원 사업에 대해 여쭙니다.
- fallback_reasons: numbered_under_split
- risk_tags: phone_dialogue, numbered_or_heading_list
- accepted: True, reject_reason: None, latency: 16.42?
- ?? ???: 석면슬레이트 철거 및 처리 지원 사업에 대해 여쭙니다. 2018년 석면슬레이트 철거 및 처리 지원 문서에 보면 내용은 아래와 같습니다. ○ 지원 근거 - 석면안전관리법의 슬레이트 해체·제거·수집·운반·보관·처리 특례 규정 - 환경부의 “슬레이트 처리 국고보조사업 업무처리 지침(2016. 12월)”  ○ 신청 기간 : 2018. 2월 ∼ 12월  ○ 지원 금액 : 최대 지원금 309만 원(수수료 제외), 지원금 초과 시 자부담  ○ 지원 범위 - 주택·창고의 지붕재 및 벽체로 사용된 석면슬레이트 철거 지원 (최대 지원금 309만 원 내에서 슬레이트 처리비 잔액이 발생 시, 차액은 지붕 개량비에 보탤 수 있음) ※ 무허가 건축물의 슬레이트 철거는 건축물 멸실 조건으로 신청 가능  ○ 지원 대상 및 우선순위 - 기초생활수급자(1순위), 차상위 계층(2순위), 일반가구(3순위) 제가 궁금한 점은 지원 
- rule_segments:
  - 제가 궁금한 점은 지원 범위에 대해 어디까지 지원을 해 주는 건지 알고 싶습니다.
  - : 주택이 없는 과수원의 창고도 포함을 한다는 의미인지요??
- llm_segments:
  - 석면슬레이트 철거 지원 범위 확인
  - 과수원의 무허가 창고 철거 지원 여부 확인
- restored_evidence_texts:
  - 제가 궁금한 점은 지원 범위에 대해 어디까지 지원을 해 주는 건지 알고 싶습니다.
  - : 주택이 없는 과수원의 창고도 포함을 한다는 의미인지요??
- human_judgment: 
- human_note: 

## 22. accepted_review / 6894187
- ??: 종량제 및 쓰레기 수거 차량의 최저 입찰가 관련
- fallback_reasons: fallback_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 11.36?
- ?? ???: 종량제 및 쓰레기 수거 차량의 최저 입찰가 관련 안녕하세요  제가 거주중인 아파트에도 종량제, 음식물, 재활용 차량 등이 정기적으로 방문하는데요,  시에서 관련 업체와의 계약 시, 최저 낙찰가가 아닌 안전이나 위생, 등등의 여러가지 중요한 부분들도 고려하여 거래가 진행되었으면 좋겠네요.  고맙습니다.
- rule_segments:
  - 안녕하세요 제가 거주중인 아파트에도 종량제, 음식물, 재활용 차량 등이 정기적으로 방문하는데요, 시에서 관련 업체와의 계약 시, 최저 낙찰가가 아닌 안전이나 위생, 등등의 여러가지 중요한 부분들도 고려하여 거래가 진행되었으면 좋겠네요. 고맙습니다.
- llm_segments:
  - 최저 낙찰가 외에 안전 및 위생 등 중요 요소를 고려한 계약 진행 요청
- restored_evidence_texts:
  - 시에서 관련 업체와의 계약 시,
  - 최저 낙찰가가 아닌
  - 안전이나 위생, 등등의 여러가지 중요한 부분들도 고려하여 거래가 진행되었으면 좋겠네요.
- human_judgment: 
- human_note: 

## 23. accepted_review / 6893765
- ??: 불법 광고물 단속 요청합니다.
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 10.37?
- ?? ???: 불법 광고물 단속 요청합니다. 불법 광고물 전단지를 계속해서 문앞에 부착하는데 단속할 수 있는 근거는 없나요?
- rule_segments:
  - 불법 광고물 전단지를 계속해서 문앞에 부착하는데 단속할 수 있는 근거는 없나요?
- llm_segments:
  - 불법 광고물 단속 요청합니다.
  - 단속할 수 있는 근거 문의
- restored_evidence_texts:
  - 불법 광고물 단속 요청합니다.
  - 불법 광고물 전단지를 계속해서 문앞에 부착하는데 단속할 수 있는 근거는 없나요?
- human_judgment: 
- human_note: 

## 24. accepted_review / 6892861
- ??: 자동차세 연납승계제도 및 신규 취득 자동차 연납 신청 안내
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.49?
- ?? ???: 자동차세 연납승계제도 및 신규 취득 자동차 연납 신청 안내 자동차세 연납 후 변경이 있는 경우 연납 세금은 어떻게 되나요?
- rule_segments:
  - 자동차세 연납 후 변경이 있는 경우 연납 세금은 어떻게 되나요?
- llm_segments:
  - 자동차세 연납 후 변경이 있는 경우 연납 세금은 어떻게 되나요?
- restored_evidence_texts:
  - 자동차세 연납 후 변경이 있는 경우 연납 세금은 어떻게 되나요?
- human_judgment: 
- human_note: 

## 25. accepted_review / 6895012
- ??: 청소년보호법 위반업소 신고 처리 경과 질의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.19?
- ?? ???: 청소년보호법 위반업소 신고 처리 경과 질의 질의: 안녕하세요.  2024년 1월 1일 구례군청에 청소년보호법 위반 업소들을 신고하였으나,  포상금 및 처분결과를 받지 못하여 민원을 신청합니다.
- rule_segments:
  - 포상금 및 처분결과를 받지 못하여 민원을 신청합니다.
- llm_segments:
  - 청소년보호법 위반 업소의 포상금 및 처분결과 확인 요청
- restored_evidence_texts:
  - 포상금 및 처분결과를 받지 못하여 민원을 신청합니다.
- human_judgment: 
- human_note: 

## 26. accepted_review / 6899198
- ??: 입찰공고에서 품목코드 확인하는 방법
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.75?
- ?? ???: 입찰공고에서 품목코드 확인하는 방법 입찰공고품목의 품목코드 확인은 어떻게 하는지 궁금합니다.
- rule_segments:
  - 입찰공고품목의 품목코드 확인은 어떻게 하는지 궁금합니다.
- llm_segments:
  - 입찰공고품목의 품목코드 확인 방법을 알려주세요.
- restored_evidence_texts:
  - 입찰공고에서 품목코드 확인하는 방법
  - 입찰공고품목의 품목코드 확인은 어떻게 하는지 궁금합니다.
- human_judgment: 
- human_note: 

## 27. accepted_review / 6907901
- ??: 도서관 카드 비밀번호 확인문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: phone_dialogue
- accepted: True, reject_reason: None, latency: 9.68?
- ?? ???: 도서관 카드 비밀번호 확인문의 도서관 카드로 책 대여할 때  비번 숫자 4자리가 필요하던데 기억이 안납니다.  이 비밀번호 확인은 어디서 해야 하나요??
- rule_segments:
  - 이 비밀번호 확인은 어디서 해야 하나요??
- llm_segments:
  - 도서관 카드 비밀번호 확인 방법을 알려주세요.
- restored_evidence_texts:
  - 도서관 카드 비밀번호 확인문의
  - 비번 숫자 4자리가 필요하던데 기억이 안납니다.
  - 이 비밀번호 확인은 어디서 해야 하나요??
- human_judgment: 
- human_note: 

## 28. accepted_review / 800540
- ??: 중원구에서 서울가는 G버스 노선이 없습니다.
- fallback_reasons: weak_request_signal
- risk_tags: weak_request_signal
- accepted: True, reject_reason: None, latency: 20.13?
- ?? ???: 중원구에서 서울가는 G버스 노선이 없습니다. 안녕하세요? 재작년에 분당구에서 중원구로 이사온 시민입니다. 중원구 재개발이 계속 진행되면서 대단지 아파트들이 계속 분양을 하고 거주자들이 늘어나고 있습니다만 중원구에서 서울로 직행하는 G버스 노선은 거의 없는 거나 마찬가지 수준입니다. 일례로 제가 살고있는 ▲▲▲ ▲▲▲▲▲ ▲▲▲▲ 아파트에서 ▲▲역으로 출근을 하려면 거리상으로는 분당구보다 더 가까움에도 불구하고 버스를 타고 가려면 중원구에서 분당구로 버스를타고 가서 거기서 다시 버스를 타야됩니다. 제가 살고 있는 아파트만 5700세대입니다. 완전히 새로 유입된 거주민들이죠. 더 잘 아시겠지만 이 지역에 비슷한 규모의 대단지 아파트가 요 몇년 사이 몇 군데 더 지어졌고 거주민들이 대거 들어왔습니다. 여기서 그치지 않고 내년 내후년까지 계속 신축아파트가 입주를 시작합니다. 또 그들 중 상당수는 저와같
- rule_segments:
  - 시기적으로 이미 늦었지만 지금이라도 주민이 늘어나는 만큼 앞서가는 행정 보여주시길 바랍니다.
  - G버스 노선 적극 신설 부탁드립니다.
  - 가능한 빠른 조치 부탁드리고 혹여 민원수가 부족해 신설이 어렵다면 지역주민과 함께 할 수도 있으니 피드백 부탁드립니다.
- llm_segments:
  - 중원구에서 서울로 직행하는 G버스 노선 신설 요청
  - 버스 이동 경로 개선 요청
  - 주민 증가에 따른 행정 조치 요청
- restored_evidence_texts:
  - 중원구에서 서울가는 G버스 노선이 없습니다.
  - 중원구에서 서울로 직행하는 G버스 노선은 거의 없는 거나 마찬가지 수준입니다.
  - 시기적으로 이미 늦었지만 지금이라도 주민이 늘어나는 만큼 앞서가는 행정 보여주시길 바랍니다. G버스 노선 적극 신설 부탁드립니다.
  - 거리상으로는 분당구보다 더 가까움에도 불구하고 버스를 타고 가려면 중원구에서 분당구로 버스를타고 가서 거기서 다시 버스를 타야됩니다.
  - 가능한 빠른 조치 부탁드리고 혹여 민원수가 부족해 신설이 어렵다면 지역주민과 함께 할 수도 있으니 피드백 부탁드립니다.
- human_judgment: 
- human_note: 

## 29. accepted_review / 6905322
- ??: 결격사유조회신청 방법
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.49?
- ?? ???: 결격사유조회신청 방법 결격사유조회신청은 어떻게 해야 하나요?
- rule_segments:
  - 결격사유조회신청은 어떻게 해야 하나요?
- llm_segments:
  - 결격사유조회신청 방법 알려주세요.
- restored_evidence_texts:
  - 결격사유조회신청 방법
- human_judgment: 
- human_note: 

## 30. accepted_review / 6889777
- ??: 대구어린이기자단은 어떤 활동을 하고 어떻게 가입하나요?
- fallback_reasons: phone_dialogue_uncertain
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.89?
- ?? ???: 대구어린이기자단은 어떤 활동을 하고 어떻게 가입하나요? 대구어린이기자단은 어떤 활동을 하고 어떻게 가입하나요?
- rule_segments:
  - 대구어린이기자단은 어떤 활동을 하고 어떻게 가입하나요?
- llm_segments:
  - 대구어린이기자단의 활동 내용과 가입 방법을 알려주세요.
- restored_evidence_texts:
  - 대구어린이기자단은 어떤 활동을 하고 어떻게 가입하나요?
- human_judgment: 
- human_note: 

## 31. accepted_review / 501065
- ??: 분식점 창업지원 문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.48?
- ?? ???: 분식점 창업지원 문의 김밥 위주의 분식점을 동업으로 창업할 예정입니다. - 분식점의 창업트랜드와 창업절차 및 자금지원 제도를 알려주시기 바랍니다.
- rule_segments:
  - 분식점의 창업트랜드와 창업절차 및 자금지원 제도를 알려주시기 바랍니다.
- llm_segments:
  - 분식점의 창업트랜드와 창업절차 및 자금지원 제도를 알려주세요.
- restored_evidence_texts:
  - 김밥 위주의 분식점을 동업으로 창업할 예정입니다. - 분식점의 창업트랜드와 창업절차 및 자금지원 제도를 알려주시기 바랍니다.
- human_judgment: 
- human_note: 

## 32. accepted_review / 6899062
- ??: 우리나라 원양어업에서 어획하는 다랑어는 몇 종이 있나요?
- fallback_reasons: phone_dialogue_uncertain
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.63?
- ?? ???: 우리나라 원양어업에서 어획하는 다랑어는 몇 종이 있나요? 우리나라 원양어업에서 어획하는 다랑어는 몇 종이 있나요?
- rule_segments:
  - 우리나라 원양어업에서 어획하는 다랑어는 몇 종이 있나요?
- llm_segments:
  - 우리나라 원양어업에서 어획하는 다랑어 종의 수를 알려주세요.
- restored_evidence_texts:
  - 우리나라 원양어업에서 어획하는 다랑어는 몇 종이 있나요?
- human_judgment: 
- human_note: 

## 33. accepted_review / 6906372
- ??: 사직단 복원 정비가 궁금합니다.
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.1?
- ?? ???: 사직단 복원 정비가 궁금합니다. 사직단 복원 정비 사업의 기간, 규모, 사업비가 궁금합니다.
- rule_segments:
  - 사직단 복원 정비 사업의 기간, 규모, 사업비가 궁금합니다.
- llm_segments:
  - 사직단 복원 정비 사업의 기간, 규모, 사업비가 궁금합니다.
- restored_evidence_texts:
  - 사직단 복원 정비 사업의 기간, 규모, 사업비가 궁금합니다.
- human_judgment: 
- human_note: 

## 34. accepted_review / 6893267
- ??: 경산시 시민안전보험 신청요건 및 지원 내용
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.21?
- ?? ???: 경산시 시민안전보험 신청요건 및 지원 내용 경산시 시민안전보험의 신청요건과 지원 내용이 궁금해요.
- rule_segments:
  - 경산시 시민안전보험의 신청요건과 지원 내용이 궁금해요.
- llm_segments:
  - 경산시 시민안전보험의 신청요건과 지원 내용을 알려주세요.
- restored_evidence_texts:
  - 경산시 시민안전보험의 신청요건과 지원 내용이 궁금해요.
- human_judgment: 
- human_note: 

## 35. accepted_review / 6894640
- ??: 출생신고를 늦게 한 경우 부모급여 수령 가능 여부
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.2?
- ?? ???: 출생신고를 늦게 한 경우 부모급여 수령 가능 여부 출생신고 지연으로 부모급여를 늦게 신청하였다면, 부모급여도 신청한 달부터 받을 수 있나요?
- rule_segments:
  - 출생신고를 늦게 한 경우 부모급여 수령 가능 여부
- llm_segments:
  - 출생신고를 늦게 한 경우 부모급여 수령 가능 여부
- restored_evidence_texts:
  - 출생신고를 늦게 한 경우 부모급여 수령 가능 여부
- human_judgment: 
- human_note: 

## 36. accepted_review / 6894741
- ??: 허위지급명세서 확인 방법 및 소득부인 신청 경로
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.6?
- ?? ???: 허위지급명세서 확인 방법 및 소득부인 신청 경로 근무사실이 없는데 제 명의로 지급명세서가 제출되었는지 종합소득세 신고를 하라고 안내를 받았습니다 지급명세서를 어디서 제출했는지 확인할 수 있는 방법과 어떻게 처리를 해야하는지 궁금합니다.
- rule_segments:
  - 지급명세서를 어디서 제출했는지 확인할 수 있는 방법과 어떻게 처리를 해야하는지 궁금합니다.
- llm_segments:
  - 지급명세서 확인 방법 및 처리 절차 문의
- restored_evidence_texts:
  - 허위지급명세서 확인 방법 및 소득부인 신청 경로
  - 근무사실이 없는데 제 명의로 지급명세서가 제출되었는지 종합소득세 신고를 하라고 안내를 받았습니다
  - 지급명세서를 어디서 제출했는지 확인할 수 있는 방법과 어떻게 처리를 해야하는지 궁금합니다.
- human_judgment: 
- human_note: 

## 37. accepted_review / 300106
- ??: 인천발 ktx 정상개통시기 확인
- fallback_reasons: fallback_single_segment, strong_candidate_single_segment, segment_too_long
- risk_tags: none
- accepted: True, reject_reason: None, latency: 13.42?
- ?? ???: 인천발 ktx 정상개통시기 확인 인천발ktx 개통 시기를 2024년 말~2025년 초로 알고 있습니다. 그러나 이번 국정감사 때 의원들의 개통 지연에 대한 문제 제기가 있었습니다. 문제 원인은 로템의 emu 320 신규 차량(2편성) 입찰을 하지 않아 문제였습니다. 선로 공사는 2024년에 완료되지만 인천발KTX에 투입할 5편성 중 2편성이 없어서 정상 개통이 불가하다고 문제를 제기하였고 그래서 개통지연에 따른 지역 주민들의 우려가 대단히 큽니다. 그러나 이와 관련된 뉴스 기사가 있어서 사실 확인코자 합니다. 뉴스 기사와 같이 국토부 철도운영과와 코레일 관계자로부터 부족한 emu 320 2편성을 KTX산천으로 대체하면 정상 개통이 가능하다고 하는데 이 기사 내용이 맞는지와 그렇게 되면 예정된 2025년에 정상적으로 개통이 가능한지를 확인 후 알려주시면 감사하겠습니다.
- rule_segments:
  - 인천발ktx 개통 시기를 2024년 말~2025년 초로 알고 있습니다. 그러나 이번 국정감사 때 의원들의 개통 지연에 대한 문제 제기가 있었습니다. 문제 원인은 로템의 emu 320 신규 차량(2편성) 입찰을 하지 않아 문제였습니다. 선로 공사는 2024년에 완료되지만 인천발KTX에 투입할 5편성 중 2편성이 없어서 정상 개통이 불가하다고 문제를 제기하였고 그래서 개통지연에 따른 지역 주민들의 우려가 대단히 큽니다. 그러나 이와 관련된 뉴스 기사가 있어서 사실 확인코자 합니다. 뉴스 기사와 같이 국토부 철도운영과와 코레일 관계자로부터 부족한 emu 320 2편성을 KTX산천으로 대체하면 정상 개통이 가능하다고 하는데 이 기사 내용이 맞는지와 그렇게 되면 예정된 2025년에 정상적으로 개통이 가능한지를 확인 후 알려주시면 감사하겠습니다.
- llm_segments:
  - 인천발 KTX의 정상 개통 시기 확인
- restored_evidence_texts:
  - 인천발 ktx 정상개통시기 확인
  - 뉴스 기사와 같이 국토부 철도운영과와 코레일 관계자로부터 부족한 emu 320 2편성을 KTX산천으로 대체하면 정상 개통이 가능하다고 하는데 이 기사 내용이 맞는지와 그렇게 되면 예정된 2025년에 정상적으로 개통이 가능한지를 확인 후 알려주시면 감사하겠습니다.
- human_judgment: 
- human_note: 

## 38. accepted_review / 6892314
- ??: 주정차 위반 단속 요청
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.75?
- ?? ???: 주정차 위반 단속 요청 ooo 위치에 주정차 차량으로 인해 불편을 겪고 있습니다. 주정차 위반 단속을 하여 주시기 바랍니다.
- rule_segments:
  - 주정차 위반 단속을 하여 주시기 바랍니다.
- llm_segments:
  - 주정차 위반 단속을 하여 주시기 바랍니다.
- restored_evidence_texts:
  - ooo 위치에 주정차 차량으로 인해 불편을 겪고 있습니다. 주정차 위반 단속을 하여 주시기 바랍니다.
- human_judgment: 
- human_note: 

## 39. accepted_review / 6889152
- ??: 교권침해를 당했는데 신고와 교권보호위원회 개최 절차가 어떻게 되나요
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.3?
- ?? ???: 교권침해를 당했는데 신고와 교권보호위원회 개최 절차가 어떻게 되나요 교권침해 신고 절차와 교권보호위원회 절차, 학생에 대한 징계가 궁금합니다.
- rule_segments:
  - 교권침해 신고 절차와 교권보호위원회 절차, 학생에 대한 징계가 궁금합니다.
- llm_segments:
  - 교권침해 신고 절차와 교권보호위원회 절차 문의
- restored_evidence_texts:
  - 교권침해를 당했는데 신고와 교권보호위원회 개최 절차가 어떻게 되나요
  - 교권침해 신고 절차와 교권보호위원회 절차, 학생에 대한 징계가 궁금합니다.
- human_judgment: 
- human_note: 

## 40. accepted_review / 6893349
- ??: 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법
- fallback_reasons: fallback_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.39?
- ?? ???: 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법
- rule_segments:
  - 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법
- llm_segments:
  - 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법을 알려주세요.
- restored_evidence_texts:
  - 침수방지시설(물막이판, 역류방지시설) 설치 신청 방법
- human_judgment: 
- human_note: 

## 41. accepted_review / 6896474
- ??: 고등학교 배정방법에 대해 궁금합니다.
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.35?
- ?? ???: 고등학교 배정방법에 대해 궁금합니다. 고등학교 신입생의 경우 배정을 어떻게 받나요?
- rule_segments:
  - 고등학교 신입생의 경우 배정을 어떻게 받나요?
- llm_segments:
  - 고등학교 배정방법에 대해 알려주세요.
- restored_evidence_texts:
  - 고등학교 배정방법에 대해 궁금합니다.
- human_judgment: 
- human_note: 

## 42. accepted_review / 6888376
- ??: 학교폭력 관련 학생이 학교장의 긴급조치 결정을 이행하지 않는 경우 어떻게 하나요?
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 10.07?
- ?? ???: 학교폭력 관련 학생이 학교장의 긴급조치 결정을 이행하지 않는 경우 어떻게 하나요? 학교폭력 관련 학생이 학교장의 긴급조치 결정에 대해 이행하지 않는 경우 어떻게 대처해야 하나요?
- rule_segments:
  - 학교폭력 관련 학생이 학교장의 긴급조치 결정에 대해 이행하지 않는 경우 어떻게 대처해야 하나요?
- llm_segments:
  - 학교폭력 관련 학생의 긴급조치 이행 미준수 시 대처 방법을 알려주세요.
- restored_evidence_texts:
  - 학교폭력 관련 학생이 학교장의 긴급조치 결정을 이행하지 않는 경우 어떻게 하나요?
  - 학교폭력 관련 학생이 학교장의 긴급조치 결정에 대해 이행하지 않는 경우 어떻게 대처해야 하나요?
- human_judgment: 
- human_note: 

## 43. accepted_review / 261511
- ??: 자동차 전용도로에 가게 안내표지 설치여부
- fallback_reasons: fallback_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 7.88?
- ?? ???: 자동차 전용도로에 가게 안내표지 설치여부 자동차 전용도로에 가게 안내표지 설치여부
- rule_segments:
  - 자동차 전용도로에 가게 안내표지 설치여부
- llm_segments:
  - 가게 안내표지 설치 여부 확인
- restored_evidence_texts:
  - 자동차 전용도로에 가게 안내표지 설치여부
- human_judgment: 
- human_note: 

## 44. accepted_review / 300759
- ??: 지목상 대지에 행해지는 포장 및 잡석 및 자갈 포설같은 행위를 포장으로 보는지에 관련한 질의
- fallback_reasons: strong_candidate_single_segment, segment_too_long
- risk_tags: none
- accepted: True, reject_reason: None, latency: 12.6?
- ?? ???: 지목상 대지에 행해지는 포장 및 잡석 및 자갈 포설같은 행위를 포장으로 보는지에 관련한 질의 국토계획법 시행령 53조에 조성이 완료된 기존 대지에 건축물이나 그 밖의 공작물을 설치하기 위한 토지의 형질변경(절토 및 성토는 제외한다)은 허가를 받지 않아도 된다고 하였는데 만약 공작물이나 건축물을 설치하고자 행한 포장이 아니고 주차장을 조성하기 위한 포장일시에는 개발행위허가를 받아야 하는지가 궁금하며 또한 국토부에서 배포한 개발행위허가 관련 법령해설집에서 정의하는 포장은 아스팔트, 콘크리트, 자갈 등을 깔아 단단하게 다져 꾸미는 행위라고 하였는데 이는 토지에 자갈을 포설하는 행위 또한 포장으로 해당되어 개발행위허가를 받아야 하는지 궁금합니다.
- rule_segments:
  - 국토계획법 시행령 53조에 조성이 완료된 기존 대지에 건축물이나 그 밖의 공작물을 설치하기 위한 토지의 형질변경(절토 및 성토는 제외한다)은 허가를 받지 않아도 된다고 하였는데 만약 공작물이나 건축물을 설치하고자 행한 포장이 아니고 주차장을 조성하기 위한 포장일시에는 개발행위허가를 받아야 하는지가 궁금하며 또한 국토부에서 배포한 개발행위허가 관련 법령해설집에서 정의하는 포장은 아스팔트, 콘크리트, 자갈 등을 깔아 단단하게 다져 꾸미는 행위라고 하였는데 이는 토지에 자갈을 포설하는 행위 또한 포장으로 해당되어 개발행위허가를 받아야 하는지 궁금합니다.
- llm_segments:
  - 지목상 대지에 행해지는 포장 행위가 개발행위허가 대상인지 확인 부탁드립니다.
- restored_evidence_texts:
  - 지목상 대지에 행해지는 포장 및 잡석 및 자갈 포설같은 행위를 포장으로 보는지에 관련한 질의
- human_judgment: 
- human_note: 

## 45. accepted_review / 6895196
- ??: 경상남도 교육지원카드 신청
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.39?
- ?? ???: 경상남도 교육지원카드 신청 경상남도 교육지원카드를 신청하고 싶은데, 자격요건과 신청방법을 알고 싶습니다.
- rule_segments:
  - 경상남도 교육지원카드를 신청하고 싶은데, 자격요건과 신청방법을 알고 싶습니다.
- llm_segments:
  - 경상남도 교육지원카드 자격요건과 신청방법을 알려주세요.
- restored_evidence_texts:
  - 경상남도 교육지원카드를 신청하고 싶은데, 자격요건과 신청방법을 알고 싶습니다.
- human_judgment: 
- human_note: 

## 46. accepted_review / 6891807
- ??: 율곡수목원 방문 및 산림치유 프로그램 이용 문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.64?
- ?? ???: 율곡수목원 방문 및 산림치유 프로그램 이용 문의 파주시에 위치한 율곡수목원 방문안내 및 산림치유 프로그램 이용방법에 대하여 궁금합니다.
- rule_segments:
  - 파주시에 위치한 율곡수목원 방문안내 및 산림치유 프로그램 이용방법에 대하여 궁금합니다.
- llm_segments:
  - 율곡수목원 방문 안내 및 산림치유 프로그램 이용 방법 문의
- restored_evidence_texts:
  - 율곡수목원 방문 및 산림치유 프로그램 이용 문의
  - 파주시에 위치한 율곡수목원 방문안내 및 산림치유 프로그램 이용방법에 대하여 궁금합니다.
- human_judgment: 
- human_note: 

## 47. accepted_review / 70103
- ??: 좌회전이 가능했으면 좋겠습니다.
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.83?
- ?? ???: 좌회전이 가능했으면 좋겠습니다. 안녕하세요. 교통 관련해서 민원 신청합니다. 충남 천안시 서북구 ▲▲▲ ▲▲ ▲에 위치한 ▲▲▲▲ 푸드 뷔페가 있는데 입구로 들어가는 길이 있습니다. 그런데 이 입구가 ▲▲쪽으로 가는 방향에서 오는 차들은 우회전으로 들어가는 데 무리가 없지만 ▲▲쪽에서 오는 차량들은 중앙선 때문에 좌회전을 할 수가 없습니다. 나올 때도 마찬가지입니다. 우회전은 할 수 있지만 좌회전은 불가하여 돌아가야 합니다. 점심시간에 ▲▲▲▲ 푸드 뷔페를 이용하는 고객들이 많은데 상당히 불편한 부분이 있습니다. 중앙선을 좀 변경해 주셨으면 좋겠습니다. 이상입니다.
- rule_segments:
  - 교통 관련해서 민원 신청합니다.
- llm_segments:
  - 좌회전 가능 요청
- restored_evidence_texts:
  - 좌회전이 가능했으면 좋겠습니다.
  - 그런데 이 입구가 ▲▲쪽으로 가는 방향에서 오는 차들은 우회전으로 들어가는 데 무리가 없지만 ▲▲쪽에서 오는 차량들은 중앙선 때문에 좌회전을 할 수가 없습니다.
  - 나올 때도 마찬가지입니다. 우회전은 할 수 있지만 좌회전은 불가하여 돌아가야 합니다.
- human_judgment: 
- human_note: 

## 48. accepted_review / 6896513
- ??: 중국 체류 기간의 무범죄증명서 발급 방법 문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.59?
- ?? ???: 중국 체류 기간의 무범죄증명서 발급 방법 문의 대련에 장기체류중입니다. 캐나다 장기 비자를 신청하려다 보니 90일 이상 장기체류한 지역의 무범죄증명서를 제출하여야 한다고 합니다. 한국의 무범죄증명은 이미 발급을 받았으며, 중국 거주기간의 무범죄증명서를 발급받아야 하는데 정확한 절차를 몰라 문의합니다.
- rule_segments:
  - 캐나다 장기 비자를 신청하려다 보니 90일 이상 장기체류한 지역의 무범죄증명서를 제출하여야 한다고 합니다.
- llm_segments:
  - 중국 체류 기간의 무범죄증명서 발급 방법 문의
- restored_evidence_texts:
  - 중국 체류 기간의 무범죄증명서 발급 방법 문의
- human_judgment: 
- human_note: 

## 49. accepted_review / 6895867
- ??: 꿈 자람 마을학교 신청 방법
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.31?
- ?? ???: 꿈 자람 마을학교 신청 방법 남구 꿈 자람 마을학교에 신청 및 등록을 하고 싶어요.
- rule_segments:
  - 남구 꿈 자람 마을학교에 신청 및 등록을 하고 싶어요.
- llm_segments:
  - 남구 꿈 자람 마을학교에 신청 및 등록 방법을 알려주세요.
- restored_evidence_texts:
  - 꿈 자람 마을학교 신청 방법
  - 남구 꿈 자람 마을학교에 신청 및 등록을 하고 싶어요.
- human_judgment: 
- human_note: 

## 50. accepted_review / 6907007
- ??: 발굴허가 신청시 토지 동의서 첨부 여부
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.36?
- ?? ???: 발굴허가 신청시 토지 동의서 첨부 여부 시굴,정밀발굴조사를 하기 위하여 토지에 대한 동의서가 필요한지 여부
- rule_segments:
  - 발굴허가 신청시 토지 동의서 첨부 여부
- llm_segments:
  - 토지 동의서 첨부 여부 확인
- restored_evidence_texts:
  - 발굴허가 신청시 토지 동의서 첨부 여부
  - 시굴,정밀발굴조사를 하기 위하여 토지에 대한 동의서가 필요한지 여부
- human_judgment: 
- human_note: 

## 51. accepted_review / 6895942
- ??: 가정폭력피해자 보호를 위한 주민등록등,초본 교부제한 문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 10.16?
- ?? ???: 가정폭력피해자 보호를 위한 주민등록등,초본 교부제한 문의 가정폭력 가해자가 제 현재 주소를 확인할 수 있는 주민등록 등, 초본을 발급 못하게 하는 방법이 있나요?
- rule_segments:
  - 가정폭력 가해자가 제 현재 주소를 확인할 수 있는 주민등록 등, 초본을 발급 못하게 하는 방법이 있나요?
- llm_segments:
  - 가정폭력 가해자에게 현재 주소 확인이 불가능하도록 주민등록 등, 초본 교부 제한 방법 문의
- restored_evidence_texts:
  - 가정폭력 가해자가 제 현재 주소를 확인할 수 있는 주민등록 등, 초본을 발급 못하게 하는 방법이 있나요?
- human_judgment: 
- human_note: 

## 52. accepted_review / 700301
- ??: 
- fallback_reasons: phone_dialogue_uncertain
- risk_tags: none
- accepted: True, reject_reason: None, latency: 22.17?
- ?? ???: 1. ｢산업안전보건법｣ 상 공동 건물, 공용시설에 대한 안전관리책임자는 어느 조직에서 선임해야 하는지? a) 각 회사의 대표자 b) B-1 조직의 장 c) B-2 조직의 장 d) Z 회사의 대표자 2. 예를 들어, 공동 건물 계단 안전난간 설치가 미흡하여 물건 낙하로 아래에서 이동 중인 고객이 머리에 맞아 사망할 경우, ｢산업안전보건법｣상 처벌 대상은 누구인지? 3. 건물이 분리되어 물리적 구분은 가능한 상태로 B-1, B-2 조직은 각각의 안전보건관리책임자, 안전보건총괄책임자를 선정하여 B-1 관리 영역(전유 건물), B-2 관리 영역(공동 건물)을 책임 관리할 수 있는지? - 각각 선임하여 운영할 경우, 산업재해 발생 시 발생건수를 개별로 산정하는지? - 별도의 안전보건관리규정에 따라 운영하되 안전보건교육, 보건관리자 선임 등 일부 항목은 공동으로 시행할 수 있는지? 4. 공동 건물, 공용시
- rule_segments:
  - ｢산업안전보건법｣ 상 공동 건물, 공용시설에 대한 안전관리책임자는 어느 조직에서 선임해야 하는지?
  - 예를 들어, 공동 건물 계단 안전난간 설치가 미흡하여 물건 낙하로 아래에서 이동 중인 고객이 머리에 맞아 사망할 경우, ｢산업안전보건법｣상 처벌 대상은 누구인지?
  - B-2 조직은 각각의 안전보건관리책임자, 안전보건총괄책임자를 선정하여 B-1 관리 영역(전유 건물), B-2 관리 영역(공동 건물)을 책임 관리할 수 있는지?
  - 각각 선임하여 운영할 경우, 산업재해 발생 시 발생건수를 개별로 산정하는지?
  - 별도의 안전보건관리규정에 따라 운영하되 안전보건교육, 보건관리자 선임 등 일부 항목은 공동으로 시행할 수 있는지?
  - 공동 건물, 공용시설에 대해서 안전보건총괄책임자를 건물관리 전문기업인 Z 회사에서 선임할 수 있는지?
- llm_segments:
  - 공동 건물, 공용시설의 안전관리책임자 선임 주체는 어디인가요?
  - 산업재해 발생 시 발생건수는 개별로 산정되나요?
  - 공동 건물 안전보건총괄책임자 선임이 가능한 주체는 어디인가요?
- restored_evidence_texts:
  - 1. ｢산업안전보건법｣ 상 공동 건물, 공용시설에 대한 안전관리책임자는 어느 조직에서 선임해야 하는지?
  - - 각각 선임하여 운영할 경우, 산업재해 발생 시 발생건수를 개별로 산정하는지?
  - 4. 공동 건물, 공용시설에 대해서 안전보건총괄책임자를 건물관리 전문기업인 Z 회사에서 선임할 수 있는지?
- human_judgment: 
- human_note: 

## 53. accepted_review / 80062
- ??: ▲▲▲▲▲ 리모델링의 부정투표에 대한 부당성
- fallback_reasons: weak_request_signal
- risk_tags: weak_request_signal
- accepted: True, reject_reason: None, latency: 11.92?
- ?? ???: ▲▲▲▲▲ 리모델링의 부정투표에 대한 부당성 안녕하십니까? ▲▲▲▲▲주민 ▲▲▲입니다. 안양시민으로 35년 살고 있습니다. 여기서 직장 다니면서 아이들 둘 교육 시키고 열심히 살아 겨우 집 하나 장만해 놓았는데 집이 너무 허름하게 지어져 10년 전부터 주민들 합의로 리모델링하기로 하였지만 분담금이 집값보다 월등히 높아 도저히 감당할 수 없어서 반대의견이 현장투표 91%가 나왔고 리모델링 조합에서 사람들 고용해서 서면투표 받아 투표용지 받아온 것은 80%입니다. 이 많은 안양시민이 이 고통을 받고 울며 부르짖는데 리모델링을 지금도 원하십니까? 정부에서 재건축하면 용적률 적용해서 분담금과 무엇보다 안전한 주택을 원하시는 겁니까? 제발 여야를 떠나 시민을 위해 시정을 운영해 주십시오. 허리 90도로 숙여 부탁드립니다. 민원 받아주신 점 대단히 감사합니다.
- rule_segments:
  - 이 많은 안양시민이 이 고통을 받고 울며 부르짖는데 리모델링을 지금도 원하십니까?
  - 정부에서 재건축하면 용적률 적용해서 분담금과 무엇보다 안전한 주택을 원하시는 겁니까?
  - 제발 여야를 떠나 시민을 위해 시정을 운영해 주십시오.
  - 허리 90도로 숙여 부탁드립니다.
- llm_segments:
  - 리모델링의 부당성에 대한 조사와 조치를 요청합니다.
- restored_evidence_texts:
  - ▲▲▲▲▲ 리모델링의 부정투표에 대한 부당성
- human_judgment: 
- human_note: 

## 54. accepted_review / 6904827
- ??: 외부에서 사용하는 PC에 교육청에서 배포한 V3를 사용 가능 여부
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 10.13?
- ?? ???: 외부에서 사용하는 PC에 교육청에서 배포한 V3를 사용 가능 여부 학교에서 사용하는 PC가 아닌 개인 노트북에 교육청이 배포한 V3를 설치 해도 되나요?
- rule_segments:
  - 학교에서 사용하는 PC가 아닌 개인 노트북에 교육청이 배포한 V3를 설치 해도 되나요?
- llm_segments:
  - 외부에서 사용하는 PC에 교육청에서 배포한 V3 사용 가능 여부 확인
- restored_evidence_texts:
  - 외부에서 사용하는 PC에 교육청에서 배포한 V3를 사용 가능 여부
- human_judgment: 
- human_note: 

## 55. accepted_review / 6906687
- ??: 서울 초등학교 교사 정기전보 관련 질의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.57?
- ?? ???: 서울 초등학교 교사 정기전보 관련 질의 교육지원청 내부의 최종 학교 배정 방식과 관련하여, 관내 계속 거주 기간이나 보직 경력 등이 높은 순서대로 거주지 근거리 학교에 우선 배정되는 것인지 혹은 소문대로 엑셀을 통한 무작위 추첨(랜덤) 방식으로 배정되는지 구체적인 배정 원칙을 알고 싶습니다.
- rule_segments:
  - 교육지원청 내부의 최종 학교 배정 방식과 관련하여, 관내 계속 거주 기간이나 보직 경력 등이 높은 순서대로 거주지 근거리 학교에 우선 배정되는 것인지 혹은 소문대로 엑셀을 통한 무작위 추첨(랜덤) 방식으로 배정되는지 구체적인 배정 원칙을 알고 싶습니다.
- llm_segments:
  - 구체적인 배정 원칙을 알려주세요.
- restored_evidence_texts:
  - 교육지원청 내부의 최종 학교 배정 방식과 관련하여, 관내 계속 거주 기간이나 보직 경력 등이 높은 순서대로 거주지 근거리 학교에 우선 배정되는 것인지 혹은 소문대로 엑셀을 통한 무작위 추첨(랜덤) 방식으로 배정되는지 구체적인 배정 원칙을 알고 싶습니다.
- human_judgment: 
- human_note: 

## 56. accepted_review / 6895954
- ??: 개발제한구역 내 공익이축
- fallback_reasons: fallback_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 12.07?
- ?? ???: 개발제한구역 내 공익이축 2001년 하천정비사업으로 개발제한구역 내 주택을 보상받고 철거한 사항이 현재(2025년) 공익이축권에 해당하는지 여부
- rule_segments:
  - 2001년 하천정비사업으로 개발제한구역 내 주택을 보상받고 철거한 사항이 현재(2025년) 공익이축권에 해당하는지 여부
- llm_segments:
  - 2001년 하천정비사업으로 개발제한구역 내 주택을 보상받고 철거한 사항이 현재(2025년) 공익이축권에 해당하는지 여부
- restored_evidence_texts:
  - 2001년 하천정비사업으로 개발제한구역 내 주택을 보상받고 철거한 사항이 현재(2025년) 공익이축권에 해당하는지 여부
- human_judgment: 
- human_note: 

## 57. accepted_review / 501322
- ??: 사업자 등록 폐지에 대한 문의
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 9.11?
- ?? ???: 사업자 등록 폐지에 대한 문의 40대 법인대표 남성 사업자 등록을 폐지하고자 하는데 어떻게 해야 하는지요?
- rule_segments:
  - 40대 법인대표 남성 사업자 등록을 폐지하고자 하는데 어떻게 해야 하는지요?
- llm_segments:
  - 40대 법인대표 남성 사업자 등록 폐지 방법 문의
- restored_evidence_texts:
  - 40대 법인대표 남성 사업자 등록을 폐지하고자 하는데 어떻게 해야 하는지요?
- human_judgment: 
- human_note: 

## 58. accepted_review / 6898965
- ??: 교사 임용시험 일정과 장소가 어떻게 되나요?
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.9?
- ?? ???: 교사 임용시험 일정과 장소가 어떻게 되나요? 부산광역시 초, 중등 임용후보자 선정경쟁 시험의 일정과 장소는 어떻게 확인하나요?
- rule_segments:
  - 부산광역시 초, 중등 임용후보자 선정경쟁 시험의 일정과 장소는 어떻게 확인하나요?
- llm_segments:
  - 교사 임용시험 일정과 장소를 알려주세요.
- restored_evidence_texts:
  - 교사 임용시험 일정과 장소가 어떻게 되나요?
- human_judgment: 
- human_note: 

## 59. accepted_review / 6886829
- ??: 기업 기후동행카드관련 교통유발부담금 감면
- fallback_reasons: fallback_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.93?
- ?? ???: 기업 기후동행카드관련 교통유발부담금 감면 기업 기후동행카드관련 교통유발부담금 감면
- rule_segments:
  - 기업 기후동행카드관련 교통유발부담금 감면
- llm_segments:
  - 기업 기후동행카드 관련 교통유발부담금 감면 방법을 알려주세요.
- restored_evidence_texts:
  - 기업 기후동행카드관련 교통유발부담금 감면
- human_judgment: 
- human_note: 

## 60. accepted_review / 6901657
- ??: 공동주택 금연구역 지정 신청방법
- fallback_reasons: strong_candidate_single_segment
- risk_tags: none
- accepted: True, reject_reason: None, latency: 8.3?
- ?? ???: 공동주택 금연구역 지정 신청방법 의왕시 관내 아파트입니다. 공동주택 금연 구역 지정 절차가 궁금합니다.
- rule_segments:
  - 공동주택 금연 구역 지정 절차가 궁금합니다.
- llm_segments:
  - 공동주택 금연 구역 지정 절차가 궁금합니다.
- restored_evidence_texts:
  - 의왕시 관내 아파트입니다. 공동주택 금연 구역 지정 절차가 궁금합니다.
- human_judgment: 
- human_note: 

