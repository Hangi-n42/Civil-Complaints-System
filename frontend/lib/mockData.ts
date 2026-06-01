import type { AssignedCase } from "./api";

export const mockAssignedCases: AssignedCase[] = [
  {
    case_id: "CA-2026-0001",
    title: "독거 어르신 난방비 및 주거 지원 요청",
    received_at: "2026-05-29",
    category: "복지",
    region: "서울특별시 중구",
    priority: "매우급함",
    status: "미처리",
    assignee: "복지정책과",
    raw_text:
      "중구 신당동에 거주하는 독거 어르신이 최근 난방비 체납과 주거 누수 문제로 어려움을 겪고 있습니다. 긴급 복지 지원과 주거 점검을 요청합니다.",
    summary: "독거 어르신의 난방비 체납과 누수 문제에 대한 긴급 복지 및 주거 점검 요청",
    structured: {
      observation: { text: "독거 어르신의 난방비 체납과 주거 누수 문제가 확인됨" },
      result: { text: "생활 안정과 안전 확보를 위한 긴급 지원 검토 필요" },
      request: { text: "긴급 복지 지원 및 주거 상태 현장 점검 요청" },
      context: { text: "취약계층 지원 대상 여부 확인 필요" },
    },
  },
  {
    case_id: "CA-2026-0002",
    title: "초등학교 앞 불법 주정차 단속 요청",
    received_at: "2026-05-28",
    category: "교통",
    region: "경기도 성남시",
    priority: "급함",
    status: "검토중",
    assignee: "교통행정과",
    raw_text:
      "등하교 시간 초등학교 정문 앞 불법 주정차 차량으로 아이들이 차도 쪽으로 걸어야 합니다. 단속 강화와 안전시설 설치가 필요합니다.",
    summary: "초등학교 앞 불법 주정차로 인한 통학 안전 위험",
    structured: {
      observation: { text: "등하교 시간대 학교 앞 불법 주정차가 반복됨" },
      result: { text: "보행 시야 확보가 어렵고 어린이 교통사고 위험 증가" },
      request: { text: "집중 단속 및 어린이보호구역 안전시설 보강 요청" },
    },
  },
  {
    case_id: "CA-2026-0003",
    title: "하천 산책로 악취 및 쓰레기 처리 요청",
    received_at: "2026-05-27",
    category: "환경",
    region: "인천광역시 남동구",
    priority: "보통",
    status: "미처리",
    assignee: "환경관리과",
    raw_text:
      "하천 산책로 주변에 쓰레기가 쌓이고 악취가 심합니다. 주말 이용객이 많아 정기 청소와 안내 표지 설치를 요청합니다.",
    summary: "하천 산책로 쓰레기 적치와 악취 민원",
    structured: {
      observation: { text: "하천 산책로 주변 쓰레기 적치 및 악취 발생" },
      result: { text: "주민 이용 만족도 저하와 위생 문제 우려" },
      request: { text: "정기 청소 확대 및 무단투기 안내 표지 설치 요청" },
    },
  },
  {
    case_id: "CA-2026-0004",
    title: "이면도로 포트홀 보수 요청",
    received_at: "2026-05-26",
    category: "도로안전",
    region: "부산광역시 해운대구",
    priority: "급함",
    status: "처리완료",
    assignee: "도로안전과",
    raw_text:
      "아파트 진입 이면도로에 큰 포트홀이 생겨 차량 하부가 긁히고 보행자도 넘어질 위험이 있습니다. 빠른 보수를 요청합니다.",
    summary: "아파트 진입로 포트홀로 인한 차량 및 보행 안전 위험",
    structured: {
      observation: { text: "아파트 진입 이면도로에 대형 포트홀 발생" },
      result: { text: "차량 파손과 보행자 낙상 위험 존재" },
      request: { text: "긴급 도로 보수 및 임시 안전 조치 요청" },
    },
  },
  {
    case_id: "CA-2026-0005",
    title: "공원 야간 조명 고장 신고",
    received_at: "2026-05-25",
    category: "안전",
    region: "대전광역시 서구",
    priority: "보통",
    status: "미처리",
    assignee: "공원녹지과",
    raw_text:
      "근린공원 산책로 조명 여러 개가 꺼져 야간 이용 시 불안합니다. 조명 점검과 교체를 부탁드립니다.",
    summary: "공원 산책로 야간 조명 고장으로 인한 안전 불안",
    structured: {
      observation: { text: "근린공원 산책로 조명 다수 고장" },
      result: { text: "야간 보행 안전과 범죄 예방 측면에서 개선 필요" },
      request: { text: "조명 점검 및 고장 설비 교체 요청" },
    },
  },
];

export const mockWorkbenchSimilarCases = [
  {
    case_id: "SIM-2026-101",
    complaint: "독거 어르신 난방비 체납 및 긴급 생계 지원 문의",
    answer: "복지정책과에서 긴급복지지원 대상 여부를 확인하고 동 주민센터 방문 상담을 연계했습니다.",
    category: "복지",
    region: "서울특별시 중구",
    received_at: "2026-04-18",
    score: 0.94,
    department_tracks: [
      {
        admin_unit: "복지정책과",
        complaint: "난방비 체납으로 생활 유지가 어렵다는 민원",
        answer: "소득 및 재산 기준 확인 후 긴급복지 생계비 지원 절차를 안내했습니다.",
      },
      {
        admin_unit: "동 주민센터",
        complaint: "현장 방문 상담 요청",
        answer: "방문 일정을 조율하고 필요 서류를 사전 안내했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-2026-102",
    complaint: "어린이보호구역 불법 주정차 상시 단속 요청",
    answer: "등하교 시간대 집중 단속을 편성하고 불법 주정차 금지 안내 현수막을 설치했습니다.",
    category: "교통",
    region: "경기도 성남시",
    received_at: "2026-03-22",
    score: 0.9,
    department_tracks: [
      {
        admin_unit: "교통행정과",
        complaint: "학교 앞 불법 주정차로 통학로가 위험하다는 신고",
        answer: "단속반 순찰 시간을 조정하고 주민 안내문을 발송했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-2026-103",
    complaint: "하천변 쓰레기 적치 및 악취 개선 요청",
    answer: "환경관리과와 청소행정팀이 합동 점검 후 수거 일정을 주 2회로 확대했습니다.",
    category: "환경",
    region: "인천광역시 남동구",
    received_at: "2026-02-11",
    score: 0.87,
    department_tracks: [
      {
        admin_unit: "환경관리과",
        complaint: "하천변 악취와 쓰레기 방치 신고",
        answer: "현장 확인 결과 무단투기 취약 구간으로 분류해 계도 표지를 설치했습니다.",
      },
    ],
  },
];

export const mockHazardStatistics = {
  total_cases: 1284,
  cases_this_month: 217,
  cases_this_week: 64,
  category_stats: {
    category: ["복지", "교통", "환경", "도로안전", "안전"],
    count: [342, 286, 238, 211, 207],
  },
  hazard_top5: [
    { hazard: "통학 안전", count: 93 },
    { hazard: "주거 취약", count: 76 },
    { hazard: "도로 파손", count: 69 },
    { hazard: "악취", count: 58 },
    { hazard: "야간 조명", count: 41 },
  ],
  region_stats: {
    region: ["서울특별시", "경기도", "인천광역시", "부산광역시", "대전광역시"],
    count: [356, 331, 214, 198, 185],
  },
};

export const mockModelBenchmarkReport = {
  model_info: {
    llm_model: "mock-llm-civil-affairs",
    embedding_model: "mock-embedding-ko",
  },
  summary: {
    average_f1_score: 0.87,
    average_recall_at_5: 0.82,
    average_latency_sec: 1.34,
  },
  scenarios: [
    { name: "단일 요청 민원", f1_score: 0.91, recall_at_5: 0.86, latency_sec: 1.12 },
    { name: "복합 요청 민원", f1_score: 0.84, recall_at_5: 0.79, latency_sec: 1.58 },
    { name: "부서 라우팅", f1_score: 0.88, recall_at_5: 0.83, latency_sec: 1.31 },
    { name: "유사 사례 검색", f1_score: 0.85, recall_at_5: 0.81, latency_sec: 1.36 },
  ],
};
