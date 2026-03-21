import html
import json
import re
import time
from urllib import error as urlerror
from urllib import request as urlrequest

import streamlit as st

from app.ui.services.retrieval_parser import ResponseContractError, parse_search_response

st.set_page_config(page_title="GovAI - Frontend Integrated", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
    :root {
        --primary: #2563eb;
        --bg: #f8fafc;
        --surface: #ffffff;
        --border: #e2e8f0;
        --text-main: #0f172a;
        --text-muted: #64748b;
    }

    .stApp {
        background: var(--bg);
        color: var(--text-main);
    }

    section[data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #334155;
        min-width: 260px;
    }

    section[data-testid="stSidebar"] * {
        color: #e2e8f0;
    }

    /* Streamlit 기본 페이지 네비(Home/init) 숨김 */
    section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
        display: none;
    }

    section[data-testid="stSidebar"] button[kind="secondary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        width: 100%;
        border-radius: 10px;
        min-height: 50px;
        padding: 12px 14px;
        margin-bottom: 8px;
        font-size: 1rem;
        font-weight: 700;
        text-align: left;
        justify-content: flex-start;
    }

    section[data-testid="stSidebar"] button[kind="secondary"] {
        background: transparent;
        border: 1px solid #334155;
        color: #94a3b8;
    }

    section[data-testid="stSidebar"] button[kind="primary"] {
        background: #2563eb;
        border: 1px solid #60a5fa;
        color: #ffffff;
    }

    section[data-testid="stSidebar"] button[kind="secondary"]:focus,
    section[data-testid="stSidebar"] button[kind="primary"]:focus {
        box-shadow: none;
        outline: none;
    }

    /* 우측 상단 Deploy/메뉴 숨김 */
    [data-testid="stAppDeployButton"],
    [data-testid="stToolbar"],
    [data-testid="stHeaderActionElements"],
    #MainMenu,
    header[data-testid="stHeader"] {
        display: none !important;
        visibility: hidden !important;
    }

    div[data-testid="stDecoration"] {
        display: none;
    }

    .block-container {
        padding-top: 1rem;
    }

    .toolbar {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 10px 14px;
        margin-bottom: 14px;
    }

    .card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 20px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid var(--border);
        border-left: 4px solid var(--primary);
        border-radius: 12px;
        padding: 18px;
    }

    .kpi-label {
        color: var(--text-muted);
        font-size: 0.9rem;
    }

    .kpi-value-good {
        color: #10b981;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .kpi-value-warn {
        color: #f59e0b;
        font-size: 1.8rem;
        font-weight: 700;
    }

    .badge {
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 8px;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 700;
    }

    .search-card {
        padding: 16px;
        border: 1px solid var(--border);
        border-radius: 8px;
        border-left: 4px solid var(--primary);
        background: white;
        margin-bottom: 12px;
    }

    .chat-wrapper {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
    }

    .cit {
        background: #fef08a;
        padding: 2px 6px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .status-loading {
        background: #dbeafe;
        color: #1e40af;
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-success {
        background: #d1fae5;
        color: #065f46;
        border: 1px solid #a7f3d0;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-error {
        background: #fee2e2;
        color: #991b1b;
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

    .status-empty {
        background: #fef3c7;
        color: #92400e;
        border: 1px solid #fde68a;
        border-radius: 8px;
        padding: 12px;
        font-weight: 700;
    }

</style>
""",
    unsafe_allow_html=True,
)


SCENARIOS = {
    "road": {
        "label": "1. 도로안전 (포트홀)",
        "raw": "어제 비 오고 나서 중앙로 사거리 횡단보도 앞에 구멍이 크게 파였어요. 오토바이 지나가다 넘어질 뻔했습니다. 빨리 메워주세요.",
        "search": "포트홀, 도로 파손, 이륜차 사고",
        "chat": "이 사례를 바탕으로 도로보수팀 긴급 작업 지시서를 작성해줘.",
        "entities": [
            ("LOCATION: 중앙로 사거리", "#dbeafe", "#1e40af"),
            ("HAZARD: 구멍(포트홀)", "#fee2e2", "#991b1b"),
            ("TIME: 어제 우천 후", "#fef3c7", "#92400e"),
        ],
        "struct": {
            "관찰": "횡단보도 앞 노면 파손(포트홀) 발생",
            "결과": "이륜차(오토바이) 통행 시 전도 등 안전사고 발생 위험 고조",
            "요청": "추가 사고 예방을 위한 신속한 노면 보수 및 평탄화 작업",
            "맥락": "우천 직후 아스팔트 지반 약화로 인한 파손 추정",
        },
        "docs": [
            {
                "id": "DOC-25-102",
                "score": "0.94",
                "title": "중앙로 10m 인근 포트홀 임시 복구 완료건",
                "snippet": "...우천 후 배수 불량으로 발생한 포트홀에 대해 긴급 아스팔트 타설 완료...",
            },
            {
                "id": "DOC-25-088",
                "score": "0.89",
                "title": "이륜차 전도사고 발생 (노면 불량)",
                "snippet": "...야간 주행 중 도로 파인 곳을 발견하지 못하고 배달 오토바이가 전도됨...",
            },
            {
                "id": "DOC-24-912",
                "score": "0.81",
                "title": "장마철 상습 침수 및 지반 약화 구간 안내",
                "snippet": "...해당 교차로는 장마철마다 노면 패임 현상이 잦아 근본적인 재포장 필요...",
            },
        ],
        "chat_response": """
<b>[도로보수팀 긴급 작업 지시서]</b><br><br>
<b>1. 작업 개요</b><br>
- 위치: 중앙로 사거리 횡단보도 앞<br>
- 내용: 우천으로 인한 포트홀 긴급 평탄화 및 복구<br><br>
<b>2. 특이 및 위험 사항</b><br>
- 이륜차 전도 위험이 매우 높으므로 최우선 처리 요망. <span class='cit'>[출처 2]</span><br>
- 과거 우천 후 파손 이력이 있으므로 단순 땜질이 아닌 방수 처리를 병행할 것. <span class='cit'>[출처 1]</span>
""",
    },
    "env": {
        "label": "2. 환경 (무단투기)",
        "raw": "골목길 전봇대 아래에 누가 자꾸 쓰레기를 버리고 도망갑니다. 냄새나서 창문을 못 열겠어요. CCTV 달아주세요.",
        "search": "무단투기, 악취, CCTV 설치",
        "chat": "CCTV 설치 타당성 검토 요청서를 유관 부서용으로 작성해줘.",
        "entities": [
            ("FACILITY: 전봇대 아래", "#e0e7ff", "#3730a3"),
            ("HAZARD: 쓰레기 무단투기", "#fee2e2", "#991b1b"),
        ],
        "struct": {
            "관찰": "골목길 전봇대 주변 상습적인 생활 쓰레기 불법 투기",
            "결과": "악취 및 해충 유입으로 인한 주민 주거 환경 침해",
            "요청": "무단투기자 단속 및 예방을 위한 CCTV 설치",
            "맥락": "야간 사각지대를 이용한 상습적 행위로 추정",
        },
        "docs": [
            {
                "id": "DOC-25-301",
                "score": "0.96",
                "title": "상습 투기지역 이동식 단속 카메라 배치 결과",
                "snippet": "...고정식 CCTV 예산 부족으로 센서형 이동식 카메라를 배치한 결과 투기율 70% 감소...",
            },
            {
                "id": "DOC-25-215",
                "score": "0.85",
                "title": "야간 형광 경고문 부착 및 효과 분석",
                "snippet": "...CCTV 설치 전 임시 조치로 부착한 야간 형광 경고문이 일정 부분 억제 효과를 보임...",
            },
            {
                "id": "DOC-24-882",
                "score": "0.82",
                "title": "전신주 주변 폐기물 수거 지연 민원",
                "snippet": "...전신주 아래 방치된 쓰레기로 인해 여름철 해충 민원이 급증...",
            },
        ],
        "chat_response": """
<b>[방범용 CCTV 설치 타당성 검토 요청서]</b><br><br>
<b>1. 현황 및 문제점</b><br>
전신주 주변 사각지대를 이용한 상습 투기가 반복되고 악취 피해가 심각합니다. <span class='cit'>[출처 3]</span><br><br>
<b>2. 검토 요청 사항</b><br>
- 고정식 예산이 부족하면 센서형 이동식 단속 카메라 우선 배치를 검토 바랍니다. <span class='cit'>[출처 1]</span><br>
- 설치 전 임시 조치로 야간 형광 경고문 선부착을 요청합니다. <span class='cit'>[출처 2]</span>
""",
    },
    "noise": {
        "label": "3. 소음 (층간소음)",
        "raw": "밤 11시만 되면 위층에서 쿵쿵대고 의자 끄는 소리가 납니다. 관리사무소에 말해도 안 고쳐집니다. 미치겠어요.",
        "search": "층간소음, 아파트 분쟁, 야간 소음",
        "chat": "층간소음 분쟁 중재 절차 안내문을 민원인에게 보낼 형식으로 작성해줘.",
        "entities": [
            ("TIME: 밤 11시", "#fef3c7", "#92400e"),
            ("TYPE: 층간소음(발망치)", "#fee2e2", "#991b1b"),
        ],
        "struct": {
            "관찰": "심야 시간대(23시 이후) 상층부 거주자의 지속적인 층간소음 유발",
            "결과": "수면 방해 및 극심한 스트레스로 이웃 간 갈등 심화",
            "요청": "행정적/법적 분쟁 중재 절차 제공",
            "맥락": "공동주택 구조와 거주자 인식 부족이 복합적으로 작용",
        },
        "docs": [
            {
                "id": "DOC-25-412",
                "score": "0.95",
                "title": "환경부 층간소음 이웃사이센터 연계 지원 사례",
                "snippet": "...전문가 방문 상담 및 소음 측정 지원으로 갈등 완화...",
            },
            {
                "id": "DOC-25-188",
                "score": "0.91",
                "title": "공동주택 층간소음 관리규약 준수 권고",
                "snippet": "...야간(22시~06시) 가구 이동과 충격 소음 금지 권고...",
            },
            {
                "id": "DOC-24-765",
                "score": "0.79",
                "title": "층간소음 분쟁조정위원회 회부 절차 안내",
                "snippet": "...합의 결렬 시 관할 지자체 조정위원회 신청 가능...",
            },
        ],
        "chat_response": """
<b>[층간소음 분쟁 중재 절차 안내]</b><br><br>
심야 층간소음으로 인한 불편에 공감하며 아래의 공적 절차를 안내드립니다.<br><br>
<b>1. 층간소음 이웃사이센터 신청</b><br>
전문가 현장 방문 상담 및 소음 측정 지원이 가능합니다. <span class='cit'>[출처 1]</span><br><br>
<b>2. 분쟁조정위원회 회부</b><br>
센터 지원으로 해결되지 않으면 관할 지자체 조정위원회에 공식 신청할 수 있습니다. <span class='cit'>[출처 3]</span>
""",
    },
}

ALLOWED_ENTITY_LABELS = {"LOCATION", "TIME", "FACILITY", "HAZARD", "ADMIN_UNIT"}
ENTITY_LABEL_FALLBACK_MAP = {
    "TYPE": "HAZARD",
    "RISK": "HAZARD",
    "DATE": "TIME",
    "PLACE": "LOCATION",
    "AREA": "ADMIN_UNIT",
}


def parse_entity_item(entity_item: str) -> tuple[str, str]:
    label, _, text = entity_item.partition(":")
    return label.strip(), text.strip()


def normalize_entity_label(raw_label: str) -> tuple[str, str | None]:
    upper_label = raw_label.strip().upper()
    mapped_label = ENTITY_LABEL_FALLBACK_MAP.get(upper_label, upper_label)

    if mapped_label in ALLOWED_ENTITY_LABELS:
        if mapped_label != upper_label:
            return mapped_label, f"[ENTITY_LABEL] {upper_label} -> {mapped_label} 정규화"
        return mapped_label, None

    return "HAZARD", f"[ENTITY_LABEL] {upper_label} -> HAZARD 강제 매핑"


def get_entity_badge_color(label: str) -> tuple[str, str]:
    palette = {
        "LOCATION": ("#dbeafe", "#1e40af"),
        "TIME": ("#fef3c7", "#92400e"),
        "FACILITY": ("#e0e7ff", "#3730a3"),
        "HAZARD": ("#fee2e2", "#991b1b"),
        "ADMIN_UNIT": ("#dcfce7", "#166534"),
    }
    return palette.get(label, ("#f1f5f9", "#334155"))


def reset_outputs() -> None:
    st.session_state.struct_done = False
    st.session_state.search_done = False
    st.session_state.chat_history = []
    st.session_state.ingest_state = "idle"
    st.session_state.ingest_payload = {}
    st.session_state.ingest_error = {}


def push_status(kind: str, message: str) -> None:
    st.session_state.status_kind = kind
    st.session_state.status_message = message


def post_json(base_url: str, path: str, payload: dict, timeout: float = 15.0) -> tuple[dict, int, str | None]:
    url = f"{base_url.rstrip('/')}{path}"
    req = urlrequest.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return parsed, int(response.status), None
    except urlerror.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {}
        return parsed, int(getattr(e, "code", 500)), str(e)
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {}, 0, str(e)


def render_answer_with_citations(answer: str, citations: list[dict]) -> str:
    citation_map: dict[int, dict] = {}
    for citation in citations:
        try:
            ref_id = int(citation.get("ref_id", 0))
        except (TypeError, ValueError):
            continue
        citation_map[ref_id] = citation

    def _replace(match: re.Match[str]) -> str:
        ref_id = int(match.group(1))
        snippet = str(citation_map.get(ref_id, {}).get("snippet", "근거 스니펫 없음"))
        hover = html.escape(snippet, quote=True)
        return f"<span class='cit' title='{hover}'>[출처 {ref_id}]</span>"

    return re.sub(r"\[\[CITE:(\d+)\]\]", _replace, answer or "")


def build_sample_qa_success_payload(query: str, search_results: list[dict]) -> dict:
    first = search_results[0] if search_results else {}
    doc_id = str(first.get("doc_id") or first.get("id") or "DOC-SAMPLE-001")
    chunk_id = str(first.get("chunk_id") or "CASE-SAMPLE-001__chunk-0")
    case_id = str(first.get("case_id") or "CASE-SAMPLE-001")
    snippet = str(first.get("snippet") or "샘플 근거 스니펫")
    return {
        "success": True,
        "request_id": "REQ-SAMPLE-QA-0001",
        "timestamp": "2026-03-21T10:00:00+09:00",
        "answer": f"질문 '{query}'에 대한 검증 모드 샘플 답변입니다. [[CITE:1]]",
        "citations": [
            {
                "ref_id": 1,
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "case_id": case_id,
                "snippet": snippet,
                "relevance_score": 0.82,
                "source": "verification_sample",
            }
        ],
        "confidence": "medium",
        "limitations": "Ollama 실패로 검증 모드 샘플 응답을 사용했습니다.",
        "meta": {
            "processing_time": 0.1,
            "model": "verification-sample",
            "validation_warning": "검증 모드 샘플 응답입니다.",
        },
        "qa_validation": {
            "is_valid": True,
            "errors": [],
            "warnings": [
                {
                    "code": "SAMPLE_FALLBACK",
                    "message": "실제 QA 성공 응답이 없어 샘플 payload로 렌더링을 검증했습니다.",
                }
            ],
        },
    }


def check_search_contract_fields(items: list[dict]) -> tuple[bool, list[dict]]:
    required = ["doc_id", "score", "title", "snippet"]
    failures = []
    for idx, item in enumerate(items, start=1):
        missing = [key for key in required if key not in item or item.get(key) in (None, "")]
        score_ok = isinstance(item.get("score"), (int, float))
        if missing or not score_ok:
            failures.append({"index": idx, "missing": missing, "score_type_ok": score_ok})
    return len(failures) == 0 and len(items) > 0, failures


def build_structure_success_payload(scenario_key: str, source_text: str) -> dict:
    curr = SCENARIOS[scenario_key]
    s = curr["struct"]
    normalized_entities = []
    label_warnings = []

    for entity_item, _, _ in curr["entities"]:
        raw_label, text = parse_entity_item(entity_item)
        normalized_label, warning = normalize_entity_label(raw_label)
        normalized_entities.append({"label": normalized_label, "text": text})
        if warning:
            label_warnings.append(warning)

    return {
        "success": True,
        "request_id": "REQ-20260320-AB12CD34",
        "timestamp": "2026-03-20T10:00:00+09:00",
        "data": {
            "results": [
                {
                    "case_id": "CASE-2026-DEMO-001",
                    "source": "demo_input",
                    "created_at": "2026-03-20T10:00:00+09:00",
                    "observation": {
                        "text": s["관찰"],
                        "confidence": 0.91,
                        "evidence_span": [0, min(40, len(source_text))],
                    },
                    "result": {
                        "text": s["결과"],
                        "confidence": 0.87,
                        "evidence_span": [41, min(90, len(source_text))],
                    },
                    "request": {
                        "text": s["요청"],
                        "confidence": 0.93,
                        "evidence_span": [91, min(140, len(source_text))],
                    },
                    "context": {
                        "text": s["맥락"],
                        "confidence": 0.84,
                        "evidence_span": [141, min(190, len(source_text))],
                    },
                    "entities": normalized_entities,
                    "validation": {
                        "is_valid": True,
                        "errors": [],
                        "warnings": ["context confidence가 0.85 미만입니다."] + label_warnings,
                    },
                }
            ]
        },
    }


def build_structure_error_payload() -> dict:
    return {
        "success": False,
        "request_id": "REQ-20260320-EF56GH78",
        "timestamp": "2026-03-20T10:00:01+09:00",
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "요청 본문 형식이 올바르지 않습니다.",
            "retryable": False,
            "details": {
                "field": "created_at",
                "reason": "ISO-8601 datetime 형식 불일치",
            },
        },
    }


if "view" not in st.session_state:
    st.session_state.view = "📊 관리자 대시보드"
if "scenario" not in st.session_state:
    st.session_state.scenario = "road"
if "struct_done" not in st.session_state:
    st.session_state.struct_done = False
if "search_done" not in st.session_state:
    st.session_state.search_done = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "status_kind" not in st.session_state:
    st.session_state.status_kind = ""
if "status_message" not in st.session_state:
    st.session_state.status_message = ""
if "ingest_state" not in st.session_state:
    st.session_state.ingest_state = "idle"
if "ingest_payload" not in st.session_state:
    st.session_state.ingest_payload = {}
if "ingest_error" not in st.session_state:
    st.session_state.ingest_error = {}
if "use_be_mode" not in st.session_state:
    st.session_state.use_be_mode = False
if "api_base_url" not in st.session_state:
    st.session_state.api_base_url = "http://localhost:8000"
if "search_api_results" not in st.session_state:
    st.session_state.search_api_results = []
if "qa_last_response" not in st.session_state:
    st.session_state.qa_last_response = {}
if "search_last_raw_response" not in st.session_state:
    st.session_state.search_last_raw_response = {}
if "qa_last_raw_response" not in st.session_state:
    st.session_state.qa_last_raw_response = {}
if "ui_mode" not in st.session_state:
    st.session_state.ui_mode = "테스트 모드"
if "verification_mode" not in st.session_state:
    st.session_state.verification_mode = False
if "qa_unverifiable_reason" not in st.session_state:
    st.session_state.qa_unverifiable_reason = ""


with st.sidebar:
    st.markdown("### GovAI System")
    menu_items = ["📊 관리자 대시보드", "📝 데이터 적재", "💬 워크스페이스"]
    for menu in menu_items:
        if st.button(
            f"{menu}",
            key=f"menu_{menu}",
            use_container_width=True,
            type="primary" if st.session_state.view == menu else "secondary",
        ):
            if st.session_state.view != menu:
                st.session_state.view = menu
                st.rerun()

curr_data = SCENARIOS[st.session_state.scenario]

toolbar_left, toolbar_right = st.columns([2.4, 1.6])
with toolbar_left:
    selected = st.selectbox(
        "데모 시나리오",
        options=list(SCENARIOS.keys()),
        format_func=lambda key: SCENARIOS[key]["label"],
        index=list(SCENARIOS.keys()).index(st.session_state.scenario),
    )
with toolbar_right:
    b1, b2 = st.columns(2)
    if b1.button("Error UI", use_container_width=True):
        push_status("error", "OOM 발생: VRAM 용량 초과")
    if b2.button("Empty UI", use_container_width=True):
        push_status("empty", "해당 조건의 검색 결과가 없습니다.")

if selected != st.session_state.scenario:
    st.session_state.scenario = selected
    reset_outputs()
    st.rerun()

status_placeholder = st.empty()

curr_data = SCENARIOS[st.session_state.scenario]

if st.session_state.view == "📊 관리자 대시보드":
    st.markdown("## 시스템 실시간 KPI (최소 요건)")
    c1, c2, c3 = st.columns(3)
    c1.markdown(
        '<div class="kpi-card"><div class="kpi-label">구조화 F1 Score</div><div class="kpi-value-good">0.84</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        '<div class="kpi-card"><div class="kpi-label">검색 정확도 Recall@5</div><div class="kpi-value-good">0.88</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        '<div class="kpi-card"><div class="kpi-label">평균 응답 지연 (초)</div><div class="kpi-value-warn">6.8s</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="card"><p style="color:#64748b; text-align:center; margin:0;">(통계 차트 영역 - 추후 연동)</p></div>', unsafe_allow_html=True)

elif st.session_state.view == "📝 데이터 적재":
    st.markdown("## 신규 민원 데이터 적재 및 구조화")
    raw_text = st.text_area("원본 텍스트 입력", value=curr_data["raw"], height=120)
    test_mode = st.selectbox(
        "리그레션 시나리오",
        options=["정상 응답", "검증 오류 응답", "빈 결과 응답"],
        index=0,
        help="화면 상태(loading/success/error/empty)와 계약 필드 렌더링을 점검하기 위한 모드입니다.",
    )

    if st.button("업로드 -> 구조화 -> 검증 실행", type="primary", use_container_width=True):
        if not raw_text.strip():
            st.session_state.struct_done = False
            st.session_state.ingest_state = "empty"
            st.session_state.ingest_payload = {}
            st.session_state.ingest_error = {
                "code": "BAD_REQUEST",
                "message": "민원 원문 텍스트를 입력해주세요.",
                "retryable": False,
                "details": {"field": "text"},
            }
            st.rerun()

        st.session_state.ingest_state = "loading"
        st.markdown('<div class="status-loading">업로드/구조화/검증 처리를 진행 중입니다...</div>', unsafe_allow_html=True)
        time.sleep(1.0)

        if test_mode == "정상 응답":
            st.session_state.struct_done = True
            st.session_state.ingest_state = "success"
            st.session_state.ingest_payload = build_structure_success_payload(st.session_state.scenario, raw_text)
            st.session_state.ingest_error = {}
            push_status("success", "구조화 및 검증 완료 (계약 필드 렌더링 성공)")
        elif test_mode == "검증 오류 응답":
            st.session_state.struct_done = False
            st.session_state.ingest_state = "error"
            err_payload = build_structure_error_payload()
            st.session_state.ingest_payload = {}
            st.session_state.ingest_error = err_payload["error"]
            push_status("error", f"{err_payload['error']['code']}: {err_payload['error']['message']}")
        else:
            st.session_state.struct_done = False
            st.session_state.ingest_state = "empty"
            st.session_state.ingest_payload = {
                "success": True,
                "request_id": "REQ-20260320-EMPTY000",
                "timestamp": "2026-03-20T10:00:02+09:00",
                "data": {"results": []},
            }
            st.session_state.ingest_error = {}
            push_status("empty", "구조화 가능한 결과가 없습니다. 입력 데이터를 확인해주세요.")

        st.rerun()

    if st.session_state.ingest_state == "idle":
        st.markdown('<div class="status-empty">실행 전 상태입니다. 시나리오를 선택하고 통합 실행 버튼을 눌러주세요.</div>', unsafe_allow_html=True)
    elif st.session_state.ingest_state == "loading":
        st.markdown('<div class="status-loading">업로드 -> 구조화 -> 검증 처리 중입니다...</div>', unsafe_allow_html=True)
    elif st.session_state.ingest_state == "success":
        st.markdown('<div class="status-success">업로드, 구조화, 검증이 모두 완료되었습니다.</div>', unsafe_allow_html=True)
    elif st.session_state.ingest_state == "error":
        st.markdown('<div class="status-error">처리에 실패했습니다. 아래 오류 정보를 확인해주세요.</div>', unsafe_allow_html=True)
    elif st.session_state.ingest_state == "empty":
        st.markdown('<div class="status-empty">처리 결과가 비어 있습니다. 입력 또는 필터 조건을 확인해주세요.</div>', unsafe_allow_html=True)

    if st.session_state.struct_done:
        st.markdown("### 구조화 결과")
        result = st.session_state.ingest_payload["data"]["results"][0]
        badge_html = ""
        for entity in result.get("entities", []):
            label = entity.get("label", "")
            text = entity.get("text", "")
            bg, fg = get_entity_badge_color(label)
            badge_html += f'<span class="badge" style="background:{bg}; color:{fg};">{label}: {text}</span>'
        st.markdown(f"<div>{badge_html}</div>", unsafe_allow_html=True)
        st.caption(f"배지 렌더링 확인: 총 {len(result.get('entities', []))}개")

        if st.checkbox("배지 렌더링 디버그 보기", value=True, key="badge_debug"):
            st.json(
                {
                    "badge_count": len(result.get("entities", [])),
                    "badge_entities": result.get("entities", []),
                    "allowed_labels": sorted(list(ALLOWED_ENTITY_LABELS)),
                }
            )

        s = {
            "관찰": result["observation"]["text"],
            "결과": result["result"]["text"],
            "요청": result["request"]["text"],
            "맥락": result["context"]["text"],
        }
        st.markdown(
            f"""
<div class="card" style="line-height:1.8;">
    <div><b style="display:inline-block; width:60px; color:#2563eb;">관찰</b>{s['관찰']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">결과</b>{s['결과']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">요청</b>{s['요청']}</div>
    <div><b style="display:inline-block; width:60px; color:#2563eb;">맥락</b><span style="color:#64748b;">{s['맥락']}</span></div>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown("### 검증 상태")
        validation = result["validation"]
        if validation["is_valid"]:
            st.markdown('<div class="status-success">validation.is_valid = true</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-error">validation.is_valid = false</div>', unsafe_allow_html=True)

        warnings = validation.get("warnings", [])
        errors = validation.get("errors", [])
        col_w, col_e = st.columns(2)
        with col_w:
            st.markdown("#### warnings")
            if warnings:
                for item in warnings:
                    st.write(f"- {item}")
            else:
                st.write("- 없음")
        with col_e:
            st.markdown("#### errors")
            if errors:
                for item in errors:
                    st.write(f"- {item}")
            else:
                st.write("- 없음")

        st.markdown("### 근거(evidence span)")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("관찰", str(result["observation"]["evidence_span"]))
        e2.metric("결과", str(result["result"]["evidence_span"]))
        e3.metric("요청", str(result["request"]["evidence_span"]))
        e4.metric("맥락", str(result["context"]["evidence_span"]))

    if st.session_state.ingest_state == "error" and st.session_state.ingest_error:
        err = st.session_state.ingest_error
        st.markdown("### 오류 상세")
        st.json(
            {
                "code": err.get("code"),
                "message": err.get("message"),
                "retryable": err.get("retryable"),
                "details": err.get("details", {}),
            }
        )

else:
    st.markdown("## 민원 해결 워크스페이스")
    mode_col, verify_col, url_col = st.columns([1.2, 1.3, 2.5])
    with mode_col:
        st.session_state.ui_mode = st.radio(
            "데이터 경로",
            options=["테스트 모드", "BE 연동 모드"],
            index=1 if st.session_state.use_be_mode else 0,
            horizontal=False,
        )
        st.session_state.use_be_mode = st.session_state.ui_mode == "BE 연동 모드"
    with verify_col:
        st.session_state.verification_mode = st.checkbox(
            "검증 모드(샘플 QA 폴백)",
            value=st.session_state.verification_mode,
            help="Ollama 실패 시에도 1/2/4 항목 UI 검증을 위해 샘플 QA 성공 payload를 주입합니다.",
        )
    with url_col:
        st.session_state.api_base_url = st.text_input(
            "API Base URL",
            value=st.session_state.api_base_url,
            help="예: http://localhost:8000",
        )

    st.caption(
        f"현재 모드: {st.session_state.ui_mode} | "
        + ("검색/QA 모두 API 응답 기반" if st.session_state.use_be_mode else "검색/QA 모두 시나리오 목데이터 기반")
    )

    left, right = st.columns([1, 1.2])

    with left:
        st.markdown("### 유사 민원 검색")
        search_query = st.text_input("검색어 입력", value=curr_data["search"], key="search_query")
        if st.button("유사 민원 검색", use_container_width=True):
            if st.session_state.use_be_mode:
                payload = {
                    "query": search_query,
                    "top_k": 5,
                }
                data, _, err = post_json(st.session_state.api_base_url, "/api/v1/search", payload)
                st.session_state.search_last_raw_response = data if data else {"_error": err or "unknown"}
                if err and not data:
                    st.session_state.search_done = False
                    push_status("error", f"검색 API 연결 실패: {err}")
                elif data.get("success") is False:
                    st.session_state.search_done = False
                    message = str(data.get("error", {}).get("message", "검색 API 오류"))
                    push_status("error", message)
                else:
                    try:
                        parsed_data = parse_search_response(data)
                    except ResponseContractError as e:
                        st.session_state.search_done = False
                        push_status("error", f"search 계약 위반: {str(e)}")
                        st.rerun()

                    results = parsed_data.get("results", [])
                    normalized_results = []
                    for item in results:
                        normalized_results.append(
                            {
                                "doc_id": item.get("doc_id", "N/A"),
                                "score": item.get("score", 0.0),
                                "title": item.get("title", "제목 없음"),
                                "snippet": item.get("snippet", ""),
                                "chunk_id": item.get("chunk_id", ""),
                                "case_id": item.get("case_id", ""),
                            }
                        )
                    st.session_state.search_api_results = normalized_results
                    st.session_state.search_done = True
                    push_status("success", f"검색 완료 (총 {len(normalized_results)}건)")
            else:
                st.markdown('<div class="status-loading">벡터 DB에서 BGE-m3 임베딩으로 유사 민원을 검색 중입니다...</div>', unsafe_allow_html=True)
                time.sleep(1.2)
                st.session_state.search_done = True
                push_status("success", f'검색 완료 (총 {len(curr_data["docs"])}건)')
            st.rerun()

        if st.session_state.search_done:
            docs_to_render = st.session_state.search_api_results if st.session_state.use_be_mode else curr_data["docs"]
            for idx, doc in enumerate(docs_to_render, start=1):
                if st.session_state.use_be_mode:
                    display_id = str(doc.get("doc_id", "")).strip() or "N/A"
                    contract_missing = [
                        key for key in ["doc_id", "score", "title", "snippet"] if doc.get(key) in (None, "")
                    ]
                else:
                    display_id = str(doc.get("id", "")).strip() or "N/A"
                    contract_missing = []
                try:
                    display_score = f"{float(doc.get('score', 0.0)):.2f}"
                except (TypeError, ValueError):
                    display_score = "0.00"
                st.markdown(
                    f"""
<div class="search-card">
    <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
        <span style="font-weight:700; color:#0f172a;">[출처 {idx}] {doc['title']}</span>
        <span style="font-size:0.8rem; background:#d1fae5; color:#065f46; padding:2px 6px; border-radius:4px; font-weight:700;">유사도: {display_score}</span>
    </div>
    <div style="font-size:0.86rem; color:#475569;">{doc['snippet']}</div>
    <div style="font-size:0.75rem; color:#94a3b8; text-align:right; margin-top:8px;">ID: {display_id}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
                if st.session_state.use_be_mode:
                    if contract_missing:
                        st.markdown(
                            f"<div class='status-error'>계약 필드 누락: {', '.join(contract_missing)}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div class='status-success'>계약 필드 확인: doc_id, score, title, snippet</div>",
                            unsafe_allow_html=True,
                        )

        with st.expander("디버그: raw /api/v1/search 응답 JSON", expanded=False):
            if st.session_state.use_be_mode:
                st.json(st.session_state.search_last_raw_response or {"info": "검색 실행 전"})
            else:
                st.info("테스트 모드에서는 API 호출을 수행하지 않습니다.")

    with right:
        st.markdown("### AI 어시스턴트")

        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"], unsafe_allow_html=True)

        prompt = st.chat_input(placeholder=f"지시사항 입력... 예시) {curr_data['chat']}")
        if prompt:
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
                if st.session_state.use_be_mode:
                    st.markdown("_BE QA API 호출 중..._")
                    time.sleep(0.4)

                    search_results_payload = []
                    for item in st.session_state.search_api_results:
                        search_results_payload.append(
                            {
                                "doc_id": item.get("id"),
                                "chunk_id": item.get("chunk_id", ""),
                                "case_id": item.get("case_id", ""),
                                "snippet": item.get("snippet", ""),
                                "score": float(item.get("score", 0.0) or 0.0),
                            }
                        )

                    qa_payload = {
                        "query": prompt,
                        "top_k": 5,
                        "use_search_results": bool(search_results_payload),
                        "search_results": search_results_payload,
                    }

                    qa_data, _, qa_err = post_json(st.session_state.api_base_url, "/api/v1/qa", qa_payload, timeout=25.0)
                    st.session_state.qa_last_raw_response = qa_data if qa_data else {"_error": qa_err or "unknown"}

                    if qa_err and not qa_data:
                        st.session_state.qa_unverifiable_reason = f"QA API 연결 실패: {qa_err}"
                        if st.session_state.verification_mode:
                            qa_data = build_sample_qa_success_payload(prompt, st.session_state.search_api_results)
                            st.session_state.qa_last_raw_response = {
                                "_verification_mode": True,
                                "_reason": st.session_state.qa_unverifiable_reason,
                                "sample_payload": qa_data,
                            }
                        else:
                            answer = f"<div class='status-error'>BE QA 연결 실패: {html.escape(qa_err)}</div>"
                    elif qa_data.get("success") is False:
                        error_message = str(qa_data.get("error", {}).get("message", "QA API 오류"))
                        st.session_state.qa_unverifiable_reason = f"QA 실패 응답: {error_message}"
                        if st.session_state.verification_mode:
                            qa_data = build_sample_qa_success_payload(prompt, st.session_state.search_api_results)
                            st.session_state.qa_last_raw_response = {
                                "_verification_mode": True,
                                "_reason": st.session_state.qa_unverifiable_reason,
                                "sample_payload": qa_data,
                            }
                        else:
                            answer = f"<div class='status-error'>{html.escape(error_message)}</div>"

                    if qa_data.get("success") is True:
                        st.session_state.qa_unverifiable_reason = ""
                        st.session_state.qa_last_response = qa_data
                        citations = qa_data.get("citations", [])
                        rendered_answer = render_answer_with_citations(qa_data.get("answer", ""), citations)

                        meta = qa_data.get("meta", {})
                        warnings = qa_data.get("qa_validation", {}).get("warnings", [])

                        warning_lines = ""
                        for warning in warnings:
                            if isinstance(warning, dict):
                                message = str(warning.get("message", ""))
                            else:
                                message = str(warning)
                            if message:
                                warning_lines += f"<div>- {html.escape(message)}</div>"

                        meta_html = (
                            "<div style='margin-top:12px; padding-top:12px; border-top:1px dashed #e2e8f0; font-size:0.8rem; color:#475569;'>"
                            f"<div>처리시간: {meta.get('processing_time', '-') }s</div>"
                            f"<div>모델: {html.escape(str(meta.get('model', '-')))}</div>"
                            f"<div>검증 안내: {html.escape(str(meta.get('validation_warning', '-')))}</div>"
                            "</div>"
                        )

                        warnings_html = ""
                        warning_body = warning_lines if warning_lines else "<div>- 없음</div>"
                        warnings_html = (
                            "<div style='margin-top:10px; padding:10px; background:#fff7ed; border:1px solid #fdba74; border-radius:8px; color:#9a3412;'>"
                            "<b>qa_validation.warnings</b>"
                            f"{warning_body}"
                            "</div>"
                        )

                        citation_rows = ""
                        for citation in citations:
                            citation_rows += (
                                "<tr>"
                                f"<td style='padding:4px 8px;'>{citation.get('ref_id')}</td>"
                                f"<td style='padding:4px 8px;'>{html.escape(str(citation.get('chunk_id', '')))}</td>"
                                f"<td style='padding:4px 8px;'>{html.escape(str(citation.get('snippet', '')))}</td>"
                                "</tr>"
                            )

                        empty_row_html = "<tr><td colspan='3' style='padding:4px 8px;'>없음</td></tr>"

                        citations_debug_html = (
                            "<details style='margin-top:8px;'>"
                            "<summary>출처 매핑 확인 (click)</summary>"
                            "<table style='width:100%; border-collapse:collapse; font-size:0.82rem;'>"
                            "<thead><tr><th style='text-align:left; padding:4px 8px;'>ref_id</th><th style='text-align:left; padding:4px 8px;'>chunk_id</th><th style='text-align:left; padding:4px 8px;'>snippet</th></tr></thead>"
                            f"<tbody>{citation_rows or empty_row_html}</tbody>"
                            "</table>"
                            "</details>"
                        )

                        answer = f"{rendered_answer}{meta_html}{warnings_html}{citations_debug_html}"
                    elif not st.session_state.verification_mode:
                        st.session_state.qa_last_response = {}
                else:
                    st.markdown("_타닥타닥... AI가 답변을 작성하고 있습니다..._")
                    time.sleep(2.5)
                    answer = (
                        f"{curr_data['chat_response']}"
                        "<div style='margin-top:12px; padding-top:12px; border-top:1px dashed #e2e8f0; font-size:0.75rem; "
                        "color:#94a3b8; text-align:right;'>⚡ 생성 속도: 6.2s | 기반 모델: Qwen2.5-7B</div>"
                    )

                st.markdown(answer, unsafe_allow_html=True)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

        with st.expander("디버그: raw /api/v1/qa 응답 JSON", expanded=False):
            if st.session_state.use_be_mode:
                st.json(st.session_state.qa_last_raw_response or {"info": "QA 실행 전"})
                if st.session_state.qa_unverifiable_reason:
                    st.warning(f"검증 불가 이유: {st.session_state.qa_unverifiable_reason}")
                    st.info("대체 검증 절차: 검증 모드(샘플 QA 폴백)를 켜고 같은 질문을 다시 전송하세요.")
            else:
                st.info("테스트 모드에서는 API 호출을 수행하지 않습니다.")

        st.markdown("### Week1 검증 체크리스트 (1,2,4)")
        search_items = st.session_state.search_api_results if st.session_state.use_be_mode else []
        pass1, fail1 = check_search_contract_fields(search_items)
        na1 = st.session_state.use_be_mode and st.session_state.search_done and len(search_items) == 0

        qa_resp = st.session_state.qa_last_response if st.session_state.use_be_mode else {}
        qa_success = bool(qa_resp.get("success") is True)
        citations = qa_resp.get("citations", []) if qa_success else []
        answer_text = str(qa_resp.get("answer", "")) if qa_success else ""
        token_ids = {int(v) for v in re.findall(r"\[\[CITE:(\d+)\]\]", answer_text)} if answer_text else set()
        ref_ids = set()
        for c in citations:
            try:
                ref_ids.add(int(c.get("ref_id", 0)))
            except (TypeError, ValueError):
                continue
        pass2 = qa_success and bool(citations) and token_ids == ref_ids and bool(token_ids)

        meta = qa_resp.get("meta", {}) if qa_success else {}
        warnings = qa_resp.get("qa_validation", {}).get("warnings", []) if qa_success else []
        pass4 = qa_success and all(k in meta for k in ["processing_time", "model", "validation_warning"]) and isinstance(warnings, list)

        c1, c2, c4 = st.columns(3)
        with c1:
            if pass1:
                st.success("1) Pass")
            elif na1:
                st.info("1) N/A")
            else:
                st.error("1) Fail")
            st.caption("기준: 검색 카드에 doc_id, score, title, snippet 누락 없음")
            if na1:
                st.caption("검색 결과 0건으로 필드 렌더링 검증 불가")
            elif fail1:
                st.json({"missing_details": fail1})
        with c2:
            if pass2:
                st.success("2) Pass")
            else:
                st.error("2) Fail")
            st.caption("기준: [[CITE:n]] 토큰과 citations.ref_id 1:1 매칭 + 배지 렌더링")
        with c4:
            if pass4:
                st.success("4) Pass")
            else:
                st.error("4) Fail")
            st.caption("기준: meta 3필드와 qa_validation.warnings 섹션 노출")

if st.session_state.status_message:
    status_placeholder.markdown(
        f'<div class="status-{st.session_state.status_kind}">{st.session_state.status_message}</div>',
        unsafe_allow_html=True,
    )
    time.sleep(2.0)
    status_placeholder.empty()
    st.session_state.status_kind = ""
    st.session_state.status_message = ""
