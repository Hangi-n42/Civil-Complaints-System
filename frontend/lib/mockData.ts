export type MockAssignedCase = {
  case_id: string;
  title: string;
  category: string;
  region: string;
  assignee?: string;
  priority: "매우급함" | "급함" | "보통";
  received_at: string;
  status?: "미처리" | "검토중" | "처리완료" | "보류";
  raw_text: string;
  summary?: string;
  description?: string;
  text?: string;
  structured?: {
    observation?: { text?: string };
    request?: { text?: string };
    result?: { text?: string };
    context?: { text?: string };
  };
};

export type MockWorkbenchSimilarCase = {
  case_id: string;
  title: string;
  received_at: string;
  snippet: string;
  similarity_score: number;
  complaint: string;
  answer: string;
  department_tracks: Array<{
    admin_unit: string;
    complaint: string;
    answer: string;
  }>;
};

export const mockAssignedCases: MockAssignedCase[] = [
  {
    case_id: "CASE-2026-0001",
    title: "도로 포트홀 보수 요청",
    category: "도로",
    region: "서울특별시 강남구",
    assignee: "강남구 도로과",
    priority: "매우급함",
    received_at: "2026-05-07",
    status: "미처리",
    raw_text: "강남구 테헤란로 인근 도로에 포트홀이 크게 생겨 차량 통행이 위험합니다. 신속한 보수가 필요합니다.",
    structured: {
      observation: { text: "테헤란로 인근 도로에 포트홀이 발생했습니다." },
      request: { text: "신속한 보수와 안전 표지 설치를 요청합니다." },
      result: { text: "차량 통행 위험 및 2차 사고 우려가 있습니다." },
    },
  },
  {
    case_id: "CASE-2026-0002",
    title: "야간 소음 민원",
    category: "환경",
    region: "부산광역시 해운대구",
    assignee: "해운대구 환경과",
    priority: "급함",
    received_at: "2026-05-06",
    status: "검토중",
    raw_text: "밤 11시 이후 공사 소음이 지속되어 수면 방해가 심합니다. 단속이 필요합니다.",
    structured: {
      observation: { text: "야간 공사 소음이 지속되고 있습니다." },
      request: { text: "공사 시간 준수 여부 확인과 단속을 요청합니다." },
    },
  },
  {
    case_id: "CASE-2026-0003",
    title: "횡단보도 신호등 점검",
    category: "안전",
    region: "대구광역시 수성구",
    assignee: "수성구 교통안전과",
    priority: "보통",
    received_at: "2026-05-05",
    status: "미처리",
    raw_text: "횡단보도 보행신호가 간헐적으로 작동하지 않아 노약자 통행이 불편합니다.",
    summary: "보행신호등 점검 및 유지보수 요청",
  },
  {
    case_id: "CASE-2026-0004",
    title: "버스정류장 노후 의자 교체",
    category: "교통",
    region: "인천광역시 연수구",
    assignee: "연수구 교통행정과",
    priority: "보통",
    received_at: "2026-05-05",
    status: "미처리",
    raw_text: "정류장 의자가 파손되어 있어 어르신들이 앉기 어렵습니다. 교체 부탁드립니다.",
    description: "버스정류장 편의시설 교체 건",
  },
  {
    case_id: "CASE-2026-0005",
    title: "하수구 악취 및 역류",
    category: "환경",
    region: "광주광역시 북구",
    assignee: "북구 하수관리팀",
    priority: "매우급함",
    received_at: "2026-05-04",
    status: "검토중",
    raw_text: "집 앞 하수구에서 악취가 나고 비가 오면 물이 역류합니다. 긴급 조치가 필요합니다.",
    structured: {
      observation: { text: "하수구 악취와 우천 시 역류 현상이 있습니다." },
      request: { text: "배수로 점검 및 긴급 준설을 요청합니다." },
    },
  },
  {
    case_id: "CASE-2026-0006",
    title: "공원 조명 고장",
    category: "안전",
    region: "대전광역시 서구",
    assignee: "서구 공원녹지과",
    priority: "급함",
    received_at: "2026-05-04",
    status: "미처리",
    raw_text: "공원 산책로 조명이 여러 개 꺼져 있어 야간 보행이 불안합니다.",
  },
  {
    case_id: "CASE-2026-0007",
    title: "불법 주정차 단속 요청",
    category: "교통",
    region: "서울특별시 마포구",
    assignee: "마포구 주차관리과",
    priority: "보통",
    received_at: "2026-05-03",
    status: "미처리",
    raw_text: "골목 입구에 상시 불법 주정차가 있어 소방차 진입이 어렵습니다.",
  },
  {
    case_id: "CASE-2026-0008",
    title: "복지관 냉난방 점검",
    category: "복지",
    region: "경기도 성남시 분당구",
    assignee: "분당구 복지지원과",
    priority: "급함",
    received_at: "2026-05-03",
    status: "검토중",
    raw_text: "복지관 에어컨이 고장나 어르신들이 더위를 호소하고 있습니다. 빠른 점검이 필요합니다.",
    structured: {
      observation: { text: "복지관 냉방 장비가 고장났습니다." },
      request: { text: "즉시 점검 및 수리를 요청합니다." },
      context: { text: "폭염 대비가 필요한 상황입니다." },
    },
  },
  {
    case_id: "CASE-2026-0009",
    title: "인도 블록 파손",
    category: "도로",
    region: "울산광역시 남구",
    assignee: "남구 도로시설과",
    priority: "보통",
    received_at: "2026-05-02",
    status: "검토중",
    raw_text: "보도블록이 들떠 넘어질 위험이 있습니다. 보수 부탁드립니다.",
  },
  {
    case_id: "CASE-2026-0010",
    title: "학교 주변 쓰레기 무단투기",
    category: "환경",
    region: "충청북도 청주시 흥덕구",
    assignee: "흥덕구 청소행정과",
    priority: "급함",
    received_at: "2026-05-02",
    status: "미처리",
    raw_text: "학교 후문 주변에 쓰레기 투기가 반복되어 악취와 위생 문제가 심합니다.",
  },
  {
    case_id: "CASE-2026-0011",
    title: "가로수 가지치기 요청",
    category: "환경",
    region: "경기도 고양시 일산동구",
    assignee: "일산동구 녹지과",
    priority: "보통",
    received_at: "2026-05-01",
    status: "처리완료",
    raw_text: "가로수가 전봇대와 부딪혀 가지치기가 필요합니다.",
  },
  {
    case_id: "CASE-2026-0012",
    title: "어린이보호구역 과속 방지",
    category: "안전",
    region: "세종특별자치시",
    assignee: "세종시 교통정책과",
    priority: "매우급함",
    received_at: "2026-05-01",
    status: "검토중",
    raw_text: "어린이보호구역에서 차량 과속이 심해 단속 및 추가 안전시설 설치가 필요합니다.",
    structured: {
      observation: { text: "어린이보호구역 차량 과속이 잦습니다." },
      request: { text: "과속 단속과 안전시설 보강을 요청합니다." },
    },
  },
];

export const mockWorkbenchSimilarCases: MockWorkbenchSimilarCase[] = [
  {
    case_id: "SIM-1001",
    title: "도로 포트홀 보수 및 표지 요청",
    received_at: "2026-04-28",
    snippet: "상습 포트홀 구간에 대한 긴급 보수와 야간 안전 표지 설치가 필요합니다.",
    similarity_score: 0.96,
    complaint: "차량 통행이 많은 도로에 포트홀이 생겨 위험합니다.",
    answer: "관할 도로과에 즉시 전달하여 현장 점검과 임시 안전조치를 진행했습니다.",
    department_tracks: [
      {
        admin_unit: "도로과",
        complaint: "차량 통행이 많은 도로에 포트홀이 생겨 위험합니다.",
        answer: "현장 확인 후 임시 복구와 정비 일정을 안내했습니다.",
      },
      {
        admin_unit: "안전관리팀",
        complaint: "야간 운전자 사고 위험이 우려됩니다.",
        answer: "야간 주의 표지판과 임시 콘을 추가 배치했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-1002",
    title: "공사 소음 민원",
    received_at: "2026-04-27",
    snippet: "야간 공사 소음은 생활 민원이므로 공사 시간 준수 여부 확인이 필요합니다.",
    similarity_score: 0.93,
    complaint: "밤늦은 공사 소음으로 수면을 방해받고 있습니다.",
    answer: "환경지도팀에서 현장 계도와 소음 기준 준수 여부를 점검했습니다.",
    department_tracks: [
      {
        admin_unit: "환경지도팀",
        complaint: "야간 소음 기준을 초과하는지 확인이 필요합니다.",
        answer: "현장 계도 후 소음 저감 계획 제출을 요구했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-1003",
    title: "하수구 역류 및 악취 처리",
    received_at: "2026-04-26",
    snippet: "우천 시 반복되는 역류는 배수로 정비와 준설이 필요한 전형적인 사례입니다.",
    similarity_score: 0.91,
    complaint: "비만 오면 하수구가 역류하고 악취가 납니다.",
    answer: "배수시설 점검 후 준설 작업을 완료하고 재발 방지 계획을 수립했습니다.",
    department_tracks: [
      {
        admin_unit: "하수과",
        complaint: "배수로 막힘으로 역류가 발생합니다.",
        answer: "준설 및 배수관 세척을 실시했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-1004",
    title: "횡단보도 신호등 수리",
    received_at: "2026-04-25",
    snippet: "보행신호 불량은 즉시 조치가 필요한 안전 민원입니다.",
    similarity_score: 0.89,
    complaint: "횡단보도 신호가 간헐적으로 꺼집니다.",
    answer: "교통신호 제어반을 점검하고 램프 교체를 진행했습니다.",
    department_tracks: [
      {
        admin_unit: "교통안전과",
        complaint: "보행자 안전 확보를 위한 빠른 수리가 필요합니다.",
        answer: "현장 점검 후 신호장비 교체를 완료했습니다.",
      },
    ],
  },
  {
    case_id: "SIM-1005",
    title: "복지관 냉난방 장비 긴급 점검",
    received_at: "2026-04-24",
    snippet: "폭염 대응을 위해 복지시설 냉방 설비를 우선 점검한 사례입니다.",
    similarity_score: 0.88,
    complaint: "복지관 냉방이 고장나 어르신들이 불편합니다.",
    answer: "시설관리부서에서 당일 긴급 점검과 임시 냉방기 설치를 지원했습니다.",
    department_tracks: [
      {
        admin_unit: "시설관리부",
        complaint: "복지관 냉난방 설비 점검이 필요합니다.",
        answer: "긴급 점검과 수리를 통해 운영을 재개했습니다.",
      },
    ],
  },
];

export const mockHazardStatistics = {
  total_cases: 1248,
  cases_this_month: 186,
  cases_this_week: 54,
  category_stats: {
    category: ["도로", "환경", "안전", "교통", "복지"],
    count: [412, 298, 264, 181, 93],
  },
  hazard_top5: [
    { hazard: "포트홀", count: 121 },
    { hazard: "야간소음", count: 98 },
    { hazard: "불법주정차", count: 87 },
    { hazard: "배수불량", count: 74 },
    { hazard: "조명고장", count: 61 },
  ],
  region_stats: {
    region: ["서울", "경기", "부산", "인천", "대구"],
    count: [356, 301, 203, 178, 122],
  },
};

export const mockModelBenchmarkReport = {
  model_info: {
    llm_model: "gemma-4-9b-it",
    embedding_model: "bge-m3",
  },
  summary: {
    average_f1_score: 0.842,
    average_recall_at_5: 0.914,
    average_latency_sec: 1.74,
  },
  scenarios: [
    { name: "도로/안전", f1_score: 0.86, recall_at_5: 0.94, latency_sec: 1.62 },
    { name: "환경/복지", f1_score: 0.83, recall_at_5: 0.91, latency_sec: 1.71 },
    { name: "교통/기타", f1_score: 0.82, recall_at_5: 0.90, latency_sec: 1.89 },
  ],
};