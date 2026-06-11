"""담당부서/소관기관 후보 도출 (responsible_unit).

BE1 구조화 산출물 고도화 — 요청 #3.

설계 (벡터 핵심 + LLM 선택):
  1) busan_departments_master.json (배정용 정제본)의 업무(task) 단위 텍스트를
     bge-m3 로 임베딩해 전용 Chroma 컬렉션(busan_departments_v1)에 적재.
  2) 민원 질의를 임베딩해 의미상 가까운 업무 Top-K 를 검색.
  3) 업무 히트를 '부서' 단위로 집계 → confidence(유사도 기반 휴리스틱) + evidence 산출.
     부서명은 항상 컬렉션(=마스터 JSON)에 실재하는 정확한 부산시청 부서명 → 환각 0.
  4) (선택) LLM 재랭킹: 검색된 후보 집합 '안에서만' 선택/근거 보강.
     출력은 사후검증으로 후보 밖 이름·범위 초과 confidence 를 폐기.

주의:
  - confidence 는 코사인 유사도에서 유도한 '검증되지 않은' 점수다.
    민원→부서 정답셋이 없으므로 보정(calibration)된 확률이 아니다. BE2 는 상대값으로만 사용.
  - 무거운 의존성(chromadb / sentence_transformers / httpx / settings)은
    메서드 내부에서 지연 임포트한다. 모듈 임포트만으로 모델이 로드되지 않는다.
  - 순수 함수(extract_key_terms / aggregate_candidates / validate_llm_units)는
    모델·네트워크 없이 단위 테스트 가능하다.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.retrieval.law_article_store import BM25Index, rrf_fuse, tokenize
from app.structuring.enrichment import FACILITY_KEYWORDS, LEGAL_REF_LEXICON, OBJECT_LEXICON

# ── 상수 ─────────────────────────────────────────────────────────────────
COLLECTION_NAME = "busan_departments_v1"
MASTER_FILENAME = "busan_departments_master.json"
RESPONSIBLE_UNIT_SOURCE_BE1 = "be1_structured"

# 다중 히트 1건당 confidence 가산치와 가산 상한(휴리스틱).
_MULTIHIT_BONUS = 0.02
_MAX_BONUS_HITS = 5
_CONF_CEILING = 0.99
_REL_CONF_BASE = 0.12
_REL_CONF_MARGIN_WEIGHT = 2.0
_REL_CONF_HIT_BONUS = 0.015
_REL_CONF_EVIDENCE_BONUS = 0.02
_REL_CONF_RANK_DECAY = 0.10
_REL_CONF_GAP_DECAY = 0.50
_DEPARTMENT_RRF_K = 60
_DENSE_RRF_WEIGHT = 2

# 민원 원문에는 분명히 드러나지만 부서 업무 라벨에는 짧게만 적히는 고정밀 행정 객체 힌트.
# dense 검색 결과를 대체하지 않고 보조 hit로만 합쳐 top-3 recall을 끌어올린다.
_QUERY_DEPARTMENT_HINTS: List[Tuple[str, Tuple[Tuple[str, ...], ...]]] = [
    ("대중교통과", (("대중교통",), ("시내버스",), ("마을버스",), ("광역버스",), ("버스노선",), ("버스정류장",), ("버스", "배차"), ("버스", "증차"), ("터미널",), ("교통인프라",), ("화물차", "주차"), ("대형차량", "주차"), ("운수", "허가"))),
    ("철도시설과", (("서해선",), ("지하철",), ("도시철도",), ("7호선",), ("전철",), ("역출구",), ("역", "출구"), ("철도교통",), ("철도노선",), ("철도건설",))),
    ("도로안전과", (("가로환경정비",), ("보안등",), ("가드레일",), ("횡단보도",), ("과속방지턱",), ("도로열선",), ("반사경",), ("원미러",), ("육교",), ("교량", "균열"), ("도로표지판",), ("택시승강장",), ("불법주차", "통행"))),
    ("도로계획과", (("도로계획",), ("도로건설",), ("국도건설",), ("혼잡도로",), ("터널", "건설"), ("교량", "기초"), ("기초터파기",), ("도로폭",), ("차로수",), ("도시계획도로", "건설"))),
    ("건설행정과", (("건설기계",), ("지게차",), ("굴착기",), ("기중기",), ("조종사면허",), ("전문건설업",), ("종합건설업",), ("건설업등록",), ("건설업", "행정처분"), ("건설기술자",), ("건설산업",), ("기계설비법",), ("기계설비", "기술기준"), ("기계설비", "표준시방서"), ("기계설비유지관리자",), ("표준시장단가",), ("하도급",), ("기재사항", "변경신청"))),
    ("공공하수인프라과", (("토구",), ("분뇨",), ("하수",), ("하수도",), ("배수구",), ("악취", "도로"), ("악취", "보행"))),
    ("하천관리과", (("강변산책로",), ("하천",), ("도림천",), ("양재천",), ("한강변",), ("시민의강",))),
    ("자원순환과", (("음식물처리기",), ("음식물쓰레기",), ("RFID",), ("RIFD",), ("종량기",), ("폐지",), ("우유팩",), ("소형가전",), ("재활용품",), ("분리수거",), ("쓰레기통",), ("길거리쓰레기",), ("소각장",), ("생활폐기물",), ("일회용", "비닐봉지"), ("공공화장실", "위생"))),
    ("환경정책과", (("소음",), ("야간소음",), ("환경오염",), ("빛공해",), ("인공조명",), ("전기차충전",), ("전기차", "충전구역"), ("전기차", "보조금"), ("수소충전소",), ("수소", "충전소"), ("유해동물",), ("야생동물",), ("비둘기",), ("고라니",), ("너구리",), ("까마귀",), ("새똥",), ("조류", "배설물"), ("조류방지",))),
    ("탄소중립정책과", (("노후경유차",), ("조기폐차",), ("배출가스",), ("탄소중립",))),
    ("주택정책과", (("소규모공동주택",), ("공동주택보조금",), ("아파트관리규약",), ("공동주택관리준칙",), ("관리준칙",), ("주택임대차",), ("민간임대주택",), ("촉진지구",), ("청년월세",), ("월세지원",), ("누수분쟁",), ("위층", "아래층", "누수"), ("우수관", "공용", "전용"), ("지역주택조합",), ("주택조합",), ("주택법",), ("분양가상한제",), ("분상제",), ("실거주의무",), ("공공택지",), ("조합원", "주택법"), ("사업계획승인", "주택"), ("임대사업자",), ("주택임대사업자",), ("렌트홈",), ("표준임대차",), ("임대보증금",), ("장기수선충당금",), ("입주자대표회의",), ("공동주택", "관리"), ("공동주택", "신축"), ("공동주택", "리모델링"), ("공동주택", "바닥충격음"), ("주택건설기준",), ("청약신청",), ("아파트", "관리비"), ("경비원",), ("경비", "제한업무"))),
    ("건축정책과", (("건축법",), ("건축허가",), ("건축물관리법",), ("건축물관리점검",), ("건축물점검",), ("건축물용도",), ("건축물", "용도"), ("근린생활시설",), ("가설건축물",), ("공작물",), ("건축면적",), ("바닥면적",), ("이행강제금",), ("건축선",), ("일조권",), ("일조", "건축물"), ("필로티",), ("다락",), ("옥탑",), ("거실", "정의"), ("기숙사", "개별취사"), ("건축", "도로지정"), ("건축", "관계전문기술자"), ("현황도로",), ("도로사용승낙서",), ("소요폭", "도로"), ("가각전제",), ("건축행위허가",), ("면적산정", "지붕"), ("감리계약",), ("방화창",), ("방화유리창",), ("방화구획",), ("방화댐퍼",), ("층간방화",), ("건축물해체",), ("해체공사",), ("해체허가",), ("내진설계",), ("조경면적",), ("창세트",), ("열관류율",), ("배기구", "이격거리"), ("전열교환기",))),
    ("도시계획과", (("도시계획",), ("도시관리계획",), ("도시기본계획",), ("지구단위계획",), ("도시계획시설",), ("도심복합사업",), ("3080",), ("택지", "지구단위"), ("노외주차장", "지구단위"), ("노유자시설", "설치"), ("도시계획", "규제"), ("보존녹지",), ("녹지지역",), ("취락지구",), ("농지훼손",), ("법원부지",), ("국토의계획및이용",), ("국토의 계획 및 이용",), ("국계법",), ("개발행위허가",), ("개발제한구역",), ("토지거래허가구역",), ("토지형질변경",), ("용도지역",), ("용도지구",), ("군계획시설",), ("도시군계획시설",), ("건폐율",), ("용적률",), ("그린벨트",))),
    ("도시정비과", (("재개발",), ("재건축",), ("도시정비법",), ("도정법",), ("정비계획",), ("정비구역",), ("서면결의서",), ("조합", "정비"), ("조합장",), ("대의원",), ("비례율",), ("정비사업",), ("조합원", "재개발"), ("조합원", "입주"))),
    ("재난예방담당관", (("스프링클러",), ("소방법",), ("소방",), ("화재",))),
    ("노인복지과", (("기초연금",), ("국민연금",), ("노인",), ("어르신",))),
    ("복지정책과", (("재난긴급생계비",), ("긴급생계비",), ("생계비지원",), ("국가유공자",), ("보훈",), ("명예수당",), ("종합사회복지관",), ("사회복지관",), ("복지관",), ("노숙자",), ("노숙인",), ("심리지원서비스",), ("사회서비스",), ("복지시설", "위탁"))),
    ("여성가족과", (("가족센터",), ("다문화가정",), ("양성평등",), ("여성가족",), ("육아휴직",), ("아빠육아휴직",), ("다자녀", "등록금"), ("가족정책",), ("성별영향평가",), ("여성친화도시",), ("가족돌봄수당",), ("솔로몬의선택",), ("결혼", "미팅"), ("출산", "보조"), ("임산부", "정책"))),
    ("출산보육과", (("어린이집",), ("보육",), ("국공립",), ("보조교사",), ("보조금소급",), ("영유아",))),
    ("감염병관리과", (("사회적거리두기",), ("방역지침",), ("코로나",), ("감염병",), ("방역조치",))),
    ("건강정책과", (("금연구역",), ("실내흡연",), ("흡연", "단속"), ("고령산모",), ("의료비지원",), ("손목닥터",), ("스마트워치",), ("공공보건의료",), ("가정간호",))),
    ("보건위생과", (("조리사면허",), ("음식점위생",), ("식당방역",))),
    ("관광정책과", (("해수욕장",), ("해수욕장", "캠핑"), ("관광지",), ("여행패키지",), ("울릉도여행",), ("관광", "가이드"), ("관광", "알파카"), ("관광", "동물"))),
    ("생활체육과", (("야구장",), ("인조구장",), ("축구장",), ("풋살",), ("풋살경기장",), ("체육시설",), ("운동장",), ("체육관",), ("수영장",), ("테니스장",), ("배드민턴",), ("생활체육",), ("스포츠강좌",))),
    ("문화예술과", (("예술영재",), ("문화예술",), ("문화센터",), ("복합문화센터",), ("축제",), ("핼러윈",), ("문화시설",))),
    ("일자리노동과", (("특고지원",), ("특고",), ("고용장려금",), ("근로자고용",))),
    ("기업지원과", (("기업지원",), ("중견기업",), ("기업", "시설투자"), ("산업단지", "기업"), ("지식산업센터", "기업"), ("원스톱기업지원",))),
    ("창업벤처담당관", (("창업",), ("창업비용",), ("창업자",))),
    ("미래에너지산업과", (("태양광",), ("신재생에너지",), ("발전지원",), ("에너지지원",))),
    ("공원여가정책과", (("도시공원",), ("어린이공원",), ("근린공원",), ("공원관리",), ("공원녹지",), ("황톳길",), ("맨발걷기",), ("물놀이장",), ("공원", "벌집"), ("공원", "임시주차장"))),
    ("푸른숲도시과", (("산지전용",), ("보전산지",), ("산림",), ("숲길",), ("등산로",), ("임야",), ("도시숲",), ("식물원",), ("나무병원",), ("녹지", "공사"))),
]

# 검색용 task 확장 규칙.
# 원본 task 문구는 metadata/evidence로 그대로 보존하고, 임베딩/BM25 대상 text에만 붙인다.
# 부서명만으로 전체 살포하지 않고 해당 task 원문에 트리거가 있을 때만 적용한다.
_TASK_TEXT_EXPANSION_RULES: List[Dict[str, Tuple[str, ...]]] = [
    {
        "departments": ("건설행정과",),
        "triggers": ("종합건설업", "전문건설업", "지역건설산업", "건설기계", "하도급"),
        "terms": (
            "전문건설업", "종합건설업", "건설업등록", "건설업 행정처분",
            "건설기술자", "기계설비법", "기계설비유지관리자", "표준시장단가",
            "하도급", "기재사항 변경신청", "과태료", "건설산업기본법",
        ),
    },
    {
        "departments": ("주택정책과",),
        "triggers": ("주택정책", "주택 부동산 정책", "주택분야", "주택행정", "국민주택"),
        "terms": (
            "민간임대주택", "임대사업자", "주택임대사업자", "표준임대차",
            "렌트홈", "임대보증금", "공동주택관리", "장기수선충당금",
            "입주자대표회의", "관리규약", "주택건설기준", "청약신청",
        ),
    },
    {
        "departments": ("건축정책과",),
        "triggers": ("건축관련", "건축행정", "건축기본계획", "건축지원", "초고층 건축허가", "한국건축규정"),
        "terms": (
            "건축법", "건축허가", "용도변경", "건축물관리법", "건축물 해체",
            "방화창", "방화유리창", "방화구획", "방화댐퍼", "내진설계",
            "조경면적", "창호", "열관류율", "건축물 용도", "면적산정",
        ),
    },
    {
        "departments": ("도시계획과",),
        "triggers": ("도시계획", "도시관리계획", "도시기본계획", "국토종합계획"),
        "terms": (
            "국토의 계획 및 이용", "국계법", "지구단위계획", "도시계획시설",
            "개발행위허가", "개발제한구역", "토지형질변경", "토지거래허가구역",
            "용도지역", "용도지구", "건폐율", "용적률",
        ),
    },
    {
        "departments": ("도시공간활력과",),
        "triggers": ("노후계획도시", "도시재생"),
        "terms": (
            "노후계획도시정비", "노후계획도시기본계획", "도시재생사업",
            "도시재생전략계획", "도시재생 공모", "경제기반형 도시재생",
        ),
    },
    {
        "departments": ("공원여가정책과",),
        "triggers": ("공원여가", "도시공원", "공원녹지", "공원 사회공헌", "공원 여가", "목조전망대", "오륙도"),
        "terms": (
            "도시공원", "어린이공원", "근린공원", "공원관리", "공원녹지",
            "공원 여가프로그램", "공원 문화예술공연", "황톳길", "맨발걷기",
            "물놀이장", "공원 안전", "공원 시설",
        ),
    },
    {
        "departments": ("푸른숲도시과",),
        "triggers": ("산림", "산지", "금정산", "임도", "숲길", "도시숲", "나무병원"),
        "terms": (
            "산지전용", "보전산지", "산림정책", "임도시설", "숲길 조성",
            "등산로", "도시숲", "나무병원", "산림사업법인", "토석채취",
        ),
    },
    {
        "departments": ("철도시설과",),
        "triggers": ("도시철도", "철도", "BuTX", "정거장"),
        "terms": (
            "도시철도", "지하철", "전철", "철도노선", "철도건설",
            "역 출구", "정거장", "역세권", "광역철도", "철도시설",
        ),
    },
    {
        "departments": ("대중교통과",),
        "triggers": ("대중교통", "시내버스", "마을버스", "전세버스", "버스"),
        "terms": (
            "시내버스", "마을버스", "전세버스", "버스노선", "버스정류장",
            "버스 배차", "버스 증차", "운수종사자", "난폭운전", "버스 민원",
        ),
    },
    {
        "departments": ("생활체육과",),
        "triggers": ("생활체육", "스포츠강좌", "체력인증", "체육", "운동"),
        "terms": (
            "생활체육", "체육시설", "운동장", "풋살장", "축구장",
            "야구장", "인조구장", "스포츠강좌", "국민체력100",
        ),
    },
    {
        "departments": ("건강정책과",),
        "triggers": ("공공보건의료", "공공의료", "어린이병원", "의료지원", "공공병원"),
        "terms": (
            "공공보건의료", "공공의료", "의료비지원", "고령산모",
            "금연구역", "흡연 단속", "가정간호", "건강증진",
        ),
    },
]

# 키워드 추출 시 제거할 일반어(검색 신호가 약한 행정 상투어).
_STOPWORDS = {
    "신청", "문의", "절차", "관련", "사항", "경우", "등", "내용", "처리", "민원",
    "요청", "부탁", "안녕하세요", "감사합니다", "확인", "문제", "발생", "통해",
    "대한", "대해", "위해", "있습니다", "합니다", "해주세요", "주세요", "때문",
}

# 한글 2자 이상 또는 영숫자 2자 이상 토큰.
_TOKEN_RE = re.compile(r"[가-힣]{2,}|[A-Za-z0-9]{2,}")


# ── 순수 함수 (모델 불필요, 테스트 대상) ──────────────────────────────────
def _append_unique(target: List[str], values: List[str]) -> None:
    """빈 문자열과 중복을 제거하면서 순서를 보존해 단어를 추가한다."""
    for value in values:
        term = str(value or "").strip()
        if term and term not in target:
            target.append(term)


def _has_any_trigger(text: str, triggers: List[str]) -> bool:
    """부서/업무 원문 안에 같은 사전군의 트리거가 하나라도 있는지 확인한다."""
    return any(trigger and trigger in text for trigger in triggers)


def _task_expansion_terms(department: str, task: str) -> List[str]:
    """부서와 task 원문에 맞는 검색용 확장어를 반환한다.

    부서명 자체는 트리거로 쓰지 않는다. 짧은 업무 라벨이지만 실제 업무 의미가
    분명한 task에만 확장어를 붙여 자동 alias 노이즈가 검색 문서로 전파되지 않게 한다.
    """
    normalized_task = _normalize_match_text(task)
    if not normalized_task:
        return []

    terms: List[str] = []
    for rule in _TASK_TEXT_EXPANSION_RULES:
        if department not in rule["departments"]:
            continue
        if any(_normalize_match_text(trigger) in normalized_task for trigger in rule["triggers"]):
            _append_unique(terms, list(rule["terms"]))
    return terms


def _normalize_match_text(text: str) -> str:
    """키워드 힌트 비교를 위해 공백과 대소문자 흔들림을 줄인다."""
    return re.sub(r"\s+", "", str(text or "").casefold())


def _query_group_matches(normalized_query: str, group: Sequence[str]) -> bool:
    """AND 조건 키워드 그룹이 민원 query에 모두 포함되는지 확인한다."""
    return all(_normalize_match_text(term) in normalized_query for term in group if term)


def query_department_prior_hits(
    query_text: str,
    allowed_departments: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """민원 query의 고정밀 행정 키워드를 부서 후보 hit로 변환한다.

    벡터 검색이 놓치는 짧은 제도명/시설명 신호를 보강하기 위한 보조 hit다.
    allowed_departments가 주어지면 현재 마스터에 실제 있는 부서만 반환한다.
    """

    normalized_query = _normalize_match_text(query_text)
    if not normalized_query:
        return []

    out: List[Dict[str, Any]] = []
    allowed = allowed_departments if allowed_departments is not None else None
    for department, groups in _QUERY_DEPARTMENT_HINTS:
        if allowed is not None and department not in allowed:
            continue
        matched: List[str] = []
        for group in groups:
            if _query_group_matches(normalized_query, group):
                matched.append(" ".join(group))
        if not matched:
            continue

        similarity = min(0.95, 0.74 + 0.04 * min(len(matched) - 1, 4))
        out.append({
            "doc_id": f"query_prior::{department}",
            "department": department,
            "task": f"민원 키워드 담당부서 힌트: {', '.join(matched[:5])}",
            "similarity": round(similarity, 4),
            "_query_prior": True,
        })
    return out


def expand_department_task_text(department: str, task: str) -> str:
    """부서 업무를 인덱싱용 문서 텍스트로 확장한다.

    메타데이터의 표시용 task는 원문을 유지하고, 임베딩 대상 문서에만 부서명과
    기존 enrichment 사전의 도메인 동의어를 붙인다. 확장은 부서명/업무에 실제로
    등장한 트리거군으로 제한해 무관한 동의어가 모든 부서에 퍼지지 않게 한다.
    """
    base_terms: List[str] = []
    _append_unique(base_terms, [department, task])
    base_text = " ".join(base_terms)

    expansion_terms: List[str] = []
    for canonical, surfaces in OBJECT_LEXICON.items():
        group = [canonical, *surfaces]
        if _has_any_trigger(base_text, group):
            _append_unique(expansion_terms, group)

    for law_name, triggers in LEGAL_REF_LEXICON.items():
        group = [law_name, *triggers]
        if _has_any_trigger(base_text, group):
            _append_unique(expansion_terms, group)

    _append_unique(expansion_terms, [kw for kw in FACILITY_KEYWORDS if kw in base_text])
    _append_unique(expansion_terms, _task_expansion_terms(department, task))
    return " ".join([*base_terms, *[term for term in expansion_terms if term not in base_terms]])


def rrf_similarity(score: float, ranking_count: int, k: int = _DEPARTMENT_RRF_K) -> float:
    """RRF 원점수를 aggregate_candidates가 다루는 0~1 범위로 보정한다."""
    if ranking_count <= 0:
        return 0.0
    scaled = score * (k + 1) / ranking_count
    return round(max(0.0, min(1.0, scaled)), 4)


def sigmoid_similarity(score: float) -> float:
    """CrossEncoder logit을 0~1 범위의 task 랭킹 점수로 변환한다."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    if value >= 0:
        similarity = 1.0 / (1.0 + math.exp(-value))
    else:
        exp_value = math.exp(value)
        similarity = exp_value / (1.0 + exp_value)
    return round(max(0.0, min(1.0, similarity)), 4)


def _resolve_device(device_name: Optional[str]) -> str:
    """요청한 디바이스가 불가하면 CPU로 안전하게 낮춘다."""
    device = str(device_name or "cpu").strip().lower()
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                return "cpu"
        except Exception:
            return "cpu"
    return device or "cpu"


def _relative_confidences(ranked: List[Dict[str, Any]]) -> List[float]:
    """정렬된 부서 후보에 상대적 confidence를 부여한다.

    rank_score는 순위를 정하는 내부 점수이고, confidence는 질의 내부에서 top 후보가
    얼마나 분리됐는지를 나타내는 soft 신호다. raw cosine 절대값은 직접 쓰지 않는다.
    """
    if not ranked:
        return []

    top_score = float(ranked[0].get("_rank_score", 0.0))
    second_score = float(ranked[1].get("_rank_score", 0.0)) if len(ranked) > 1 else 0.0
    top_margin = max(0.0, top_score - second_score)
    top_hits = int(ranked[0].get("_hits", 1))
    top_evidence_count = int(ranked[0].get("_evidence_terms", 0))
    top_confidence = (
        _REL_CONF_BASE
        + _REL_CONF_MARGIN_WEIGHT * top_margin
        + _REL_CONF_HIT_BONUS * min(max(top_hits - 1, 0), _MAX_BONUS_HITS)
        + _REL_CONF_EVIDENCE_BONUS * min(top_evidence_count, 3)
    )
    top_confidence = max(0.0, min(_CONF_CEILING, top_confidence))

    confidences: List[float] = []
    for idx, item in enumerate(ranked):
        score_gap = max(0.0, top_score - float(item.get("_rank_score", 0.0)))
        confidence = top_confidence - _REL_CONF_RANK_DECAY * idx - _REL_CONF_GAP_DECAY * score_gap
        confidences.append(round(max(0.0, min(_CONF_CEILING, confidence)), 4))
    return confidences


def extract_key_terms(text: str, limit: int = 12) -> List[str]:
    """질의/업무 텍스트에서 검색 신호가 되는 명사형 토큰을 추출한다.

    형태소 분석기가 아니라 경량 정규식 기반. evidence 겹침 계산과
    LLM 프롬프트 보조용으로 충분한 수준만 목표로 한다.
    """
    terms: List[str] = []
    seen = set()
    for tok in _TOKEN_RE.findall(text or ""):
        if tok in _STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
        if len(terms) >= limit:
            break
    return terms


def _evidence_terms(query_terms: List[str], task_text: str, max_terms: int = 3) -> List[str]:
    """질의 키워드 중 해당 업무 텍스트에 실제로 등장하는 것만 근거로 반환."""
    out: List[str] = []
    for t in query_terms:
        if t in task_text and t not in out:
            out.append(t)
        if len(out) >= max_terms:
            break
    return out


def aggregate_candidates(
    task_hits: List[Dict[str, Any]],
    query_terms: Optional[List[str]] = None,
    top_n: int = 3,
    min_confidence: float = 0.0,
) -> List[Dict[str, Any]]:
    """업무 단위 검색 히트를 부서 단위 responsible_unit 후보로 집계한다.

    Args:
        task_hits: [{"department": str, "task": str, "similarity": float in [0,1]}, ...]
                   similarity 는 랭킹 입력 점수이며 내림차순일 필요는 없음.
        query_terms: evidence 겹침 계산용 질의 키워드.
        top_n: 반환할 부서 수.
        min_confidence: 이 값 미만 후보는 제외.

    Returns:
        [{"name": 부서명, "confidence": float, "evidence": [근거 문구...]}, ...]
        rank_score 내림차순. confidence는 질의 내부 마진/합의 기반 상대 신호.
    """
    query_terms = query_terms or []
    by_dept: Dict[str, Dict[str, Any]] = {}

    for hit in task_hits:
        dept = str(hit.get("department", "")).strip()
        task = str(hit.get("task", "")).strip()
        try:
            sim = float(hit.get("similarity", 0.0))
        except (TypeError, ValueError):
            sim = 0.0
        if not dept:
            continue
        sim = max(0.0, min(1.0, sim))

        slot = by_dept.setdefault(dept, {"best_sim": 0.0, "hits": 0, "best_task": "", "tasks": []})
        slot["hits"] += 1
        slot["tasks"].append((sim, task))
        if sim > slot["best_sim"]:
            slot["best_sim"] = sim
            slot["best_task"] = task

    ranked: List[Dict[str, Any]] = []
    for dept, slot in by_dept.items():
        extra = min(slot["hits"] - 1, _MAX_BONUS_HITS)
        rank_score = min(_CONF_CEILING, slot["best_sim"] + _MULTIHIT_BONUS * extra)

        # 근거: 가장 유사한 업무 문구 + 질의와 겹치는 키워드
        evidence: List[str] = []
        if slot["best_task"]:
            evidence.append(slot["best_task"])
        matched_terms = _evidence_terms(query_terms, slot["best_task"])
        evidence.extend(matched_terms)
        # 중복 제거(순서 보존)
        evidence = list(dict.fromkeys(evidence))

        ranked.append({
            "name": dept,
            "evidence": evidence,
            "_hits": slot["hits"],  # 디버그용; 호출부에서 제거 가능
            "_rank_score": round(rank_score, 4),
            "_evidence_terms": len(matched_terms),
        })

    ranked.sort(key=lambda r: r["_rank_score"], reverse=True)
    confidences = _relative_confidences(ranked)
    results: List[Dict[str, Any]] = []
    for item, confidence in zip(ranked, confidences):
        if confidence < min_confidence:
            continue
        out = dict(item)
        out["confidence"] = confidence
        results.append(out)
        if len(results) >= top_n:
            break
    return results


def validate_llm_units(
    llm_units: Any,
    allowed_names: set,
) -> List[Dict[str, Any]]:
    """LLM 출력 responsible_unit 를 후보 집합 기준으로 사후검증한다.

    - name 이 allowed_names 에 없으면(환각) 폐기.
    - confidence 를 [0,1] 로 클램프, 누락 시 0.0.
    - evidence 는 리스트로 정규화.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(llm_units, list):
        return out
    seen = set()
    for u in llm_units:
        if not isinstance(u, dict):
            continue
        name = str(u.get("name", "")).strip()
        if name not in allowed_names or name in seen:
            continue
        seen.add(name)
        try:
            conf = float(u.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = round(max(0.0, min(1.0, conf)), 4)
        ev = u.get("evidence", [])
        if isinstance(ev, str):
            ev = [ev]
        elif not isinstance(ev, list):
            ev = []
        out.append({
            "name": name,
            "confidence": conf,
            "evidence": [str(e) for e in ev],
            "source": RESPONSIBLE_UNIT_SOURCE_BE1,
        })
    return out


def build_query_text(
    raw_text: str = "",
    entity_texts: Optional[List[str]] = None,
    key_terms: Optional[List[str]] = None,
) -> str:
    """BE1 산출물 요소들을 검색 질의 문자열로 합친다.

    entity_texts/key_terms 를 앞에 배치해 핵심 객체에 가중되도록 한다.
    """
    parts: List[str] = []
    if key_terms:
        parts.append(" ".join(key_terms))
    if entity_texts:
        parts.append(" ".join(entity_texts))
    if raw_text:
        parts.append(raw_text)
    return "\n".join(p for p in parts if p).strip()


# ── LLM 재랭킹 프롬프트 ───────────────────────────────────────────────────
_LLM_SYSTEM = """\
당신은 부산시청 민원 배정 보조 AI입니다.
[시민 민원]과 [후보 부서별 업무]를 비교해 책임 부서(responsible_unit)를 고르세요.

[규칙]
1. name 은 반드시 아래 [후보 부서] 목록에 있는 정확한 부서명만 사용합니다. 목록에 없는 이름은 절대 만들지 마세요.
2. confidence 는 민원과 부서 업무의 일치도를 0.0~1.0 실수로 매깁니다.
3. evidence 는 민원과 업무에서 일치하는 핵심어 2~3개를 배열로 넣습니다.
4. 아래 JSON 형식만 출력하고 다른 설명은 덧붙이지 마세요.

{"responsible_unit": [{"name": "...", "confidence": 0.0, "evidence": ["...", "..."]}]}\
"""


class DepartmentAssigner:
    """responsible_unit 도출기 (벡터 검색 핵심 + 선택적 LLM 재랭킹)."""

    def __init__(
        self,
        master_path: Optional[str] = None,
        persist_directory: Optional[str] = None,
        embedding_model_name: Optional[str] = None,
        embedding_device: Optional[str] = None,
    ) -> None:
        from pathlib import Path
        from app.core.config import PROJECT_ROOT, settings

        self.master_path = Path(master_path) if master_path else (PROJECT_ROOT / "data" / "departments" / MASTER_FILENAME)
        self.persist_directory = persist_directory or settings.CHROMA_DB_PATH
        self.embedding_model_name = embedding_model_name or settings.EMBEDDING_MODEL
        self.embedding_device = embedding_device or settings.EMBEDDING_DEVICE
        self.min_confidence = float(getattr(settings, "RESPONSIBLE_UNIT_MIN_CONFIDENCE", 0.0))
        self.use_hybrid = bool(getattr(settings, "RESPONSIBLE_UNIT_USE_HYBRID", False))
        self.use_reranker = bool(getattr(settings, "RESPONSIBLE_UNIT_USE_RERANKER", False))
        self.reranker_model_name = str(getattr(settings, "RESPONSIBLE_UNIT_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"))
        self.reranker_device = str(getattr(settings, "RESPONSIBLE_UNIT_RERANKER_DEVICE", self.embedding_device))
        self.reranker_batch_size = int(getattr(settings, "RESPONSIBLE_UNIT_RERANKER_BATCH_SIZE", 16))
        self._model = None
        self._reranker_model = None
        self._reranker_unavailable = False
        self._reranker_used = False
        self._client = None
        self._collection = None
        self._task_records: Optional[List[Dict[str, Any]]] = None
        self._task_docid_to_idx: Dict[str, int] = {}
        self._task_department_count = 0
        self._bm25: Optional[BM25Index] = None

    # ── 임베딩 / 컬렉션 (지연 로딩) ───────────────────────────────────────
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            device = _resolve_device(self.embedding_device)
            self._model = SentenceTransformer(self.embedding_model_name, device=device)
        return self._model

    def _get_reranker(self):
        """CrossEncoder 리랭커를 지연 로딩한다. 실패하면 같은 프로세스에서는 재시도하지 않는다."""
        if self._reranker_unavailable:
            return None
        if self._reranker_model is None:
            try:
                from sentence_transformers import CrossEncoder

                device = _resolve_device(self.reranker_device)
                self._reranker_model = CrossEncoder(self.reranker_model_name, device=device)
            except Exception:
                self._reranker_unavailable = True
                return None
        return self._reranker_model

    def _embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self._get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.tolist() if hasattr(vecs, "tolist") else [list(v) for v in vecs]

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            from pathlib import Path
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_directory))
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── 부서 업무 코퍼스 / BM25 (지연 로딩) ───────────────────────────────
    def _reset_task_corpus(self) -> None:
        self._task_records = None
        self._task_docid_to_idx = {}
        self._task_department_count = 0
        self._bm25 = None

    def _task_corpus(self) -> List[Dict[str, Any]]:
        if self._task_records is None:
            import json

            master = json.loads(self.master_path.read_text(encoding="utf-8"))
            master = master if isinstance(master, list) else []
            records: List[Dict[str, Any]] = []
            for d_idx, dept in enumerate(master):
                if not isinstance(dept, dict):
                    continue
                name = str(dept.get("department", "")).strip()
                if not name:
                    continue
                for t_idx, task in enumerate(dept.get("tasks", [])):
                    task_text = str(task or "").strip()
                    if not task_text:
                        continue
                    records.append({
                        "doc_id": f"{d_idx}_{t_idx}",
                        "department": name,
                        "url": str(dept.get("url", "")),
                        "task": task_text,
                        "text": expand_department_task_text(name, task_text),
                    })
            self._task_records = records
            self._task_docid_to_idx = {r["doc_id"]: i for i, r in enumerate(records)}
            self._task_department_count = len(master)
        return self._task_records

    def _department_names(self) -> set[str]:
        """현재 마스터에 실제 존재하는 부서명 집합을 반환한다."""
        try:
            return {str(r.get("department", "")).strip() for r in self._task_corpus() if r.get("department")}
        except Exception:
            return set()

    def _task_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        self._task_corpus()
        idx = self._task_docid_to_idx.get(doc_id)
        if idx is None or self._task_records is None:
            return None
        return self._task_records[idx]

    def _get_bm25(self) -> BM25Index:
        if self._bm25 is None:
            records = self._task_corpus()
            self._bm25 = BM25Index().fit(
                [r["doc_id"] for r in records],
                [tokenize(r["text"]) for r in records],
            )
        return self._bm25

    # ── 인덱스 빌드 ──────────────────────────────────────────────────────
    def build_index(self, rebuild: bool = False) -> Dict[str, int]:
        """마스터 JSON 의 업무 텍스트를 임베딩해 컬렉션에 적재한다."""
        collection = self._get_collection()
        if rebuild:
            self._reset_task_corpus()
            self._client.delete_collection(COLLECTION_NAME)
            self._collection = None
            collection = self._get_collection()
        elif collection.count() > 0:
            return {"departments": -1, "tasks": collection.count(), "skipped": 1}

        records = self._task_corpus()
        ids = [r["doc_id"] for r in records]
        docs = [r["text"] for r in records]
        metas = [{"department": r["department"], "url": r["url"], "task": r["task"]} for r in records]

        # 배치 임베딩/적재
        BATCH = 128
        for i in range(0, len(docs), BATCH):
            chunk = docs[i:i + BATCH]
            collection.upsert(
                ids=ids[i:i + BATCH],
                documents=chunk,
                embeddings=self._embed(chunk),
                metadatas=metas[i:i + BATCH],
            )
        return {"departments": self._task_department_count, "tasks": len(docs), "skipped": 0}

    # ── Dense + BM25 + RRF ───────────────────────────────────────────────
    def _dense_task_hits(self, query_text: str, fetch_k: int) -> List[Dict[str, Any]]:
        collection = self._get_collection()
        q_vec = self._embed([query_text])[0]
        res = collection.query(
            query_embeddings=[q_vec],
            n_results=fetch_k,
            include=["metadatas", "distances"],
        )
        ids = (res.get("ids") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        return [
            {
                "doc_id": doc_id,
                "department": meta.get("department", ""),
                "task": meta.get("task", ""),
                "similarity": 1.0 - float(dist),
            }
            for doc_id, meta, dist in zip(ids, metas, dists)
        ]

    def _bm25_ranked_task_ids(
        self,
        query_text: str,
        query_terms: Optional[List[str]],
        fetch_k: int,
    ) -> List[str]:
        bm25 = self._get_bm25()
        query_tokens: List[str] = []
        for term in query_terms or [query_text]:
            query_tokens.extend(tokenize(term))
        scored = bm25.scores(query_tokens)
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:fetch_k]
        return [doc_id for doc_id, _ in ranked]

    def _hybrid_task_hits(
        self,
        query_text: str,
        fetch_k: int,
        query_terms: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        dense_hits = self._dense_task_hits(query_text, fetch_k)
        dense_ids = [h["doc_id"] for h in dense_hits if h.get("doc_id")]
        bm25_ids = self._bm25_ranked_task_ids(query_text, query_terms, fetch_k)

        rankings: List[List[str]] = []
        if dense_ids:
            rankings.extend([dense_ids] * (_DENSE_RRF_WEIGHT if bm25_ids else 1))
        if bm25_ids:
            rankings.append(bm25_ids)
        fused = rrf_fuse(rankings, k=_DEPARTMENT_RRF_K) if rankings else []
        if not fused:
            return dense_hits

        dense_by_id = {h["doc_id"]: h for h in dense_hits if h.get("doc_id")}
        out: List[Dict[str, Any]] = []
        for doc_id, score in fused[:fetch_k]:
            item = dict(dense_by_id.get(doc_id) or {})
            if not item:
                rec = self._task_by_doc_id(doc_id)
                if rec is None:
                    continue
                item = {"doc_id": doc_id, "department": rec["department"], "task": rec["task"]}
            item["similarity"] = rrf_similarity(score, len(rankings), k=_DEPARTMENT_RRF_K)
            out.append(item)
        return out

    # ── CrossEncoder task 리랭킹 ─────────────────────────────────────────
    def _reranker_task_text(self, hit: Dict[str, Any]) -> str:
        """리랭커에 넣을 부서 업무 문맥을 만든다."""
        doc_id = str(hit.get("doc_id", "")).strip()
        if doc_id:
            try:
                rec = self._task_by_doc_id(doc_id)
            except Exception:
                rec = None
            if rec:
                return str(rec.get("text") or rec.get("task") or doc_id)

        department = str(hit.get("department", "")).strip()
        task = str(hit.get("task", "")).strip()
        return " ".join(part for part in (department, task) if part).strip() or doc_id

    def _rerank_task_hits(self, query_text: str, task_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dense/Hybrid task 후보를 CrossEncoder로 재점수화한다.

        리랭커 모델이 없거나 예외가 나면 Phase 2 후보를 그대로 반환한다.
        """
        if len(task_hits) <= 1:
            return task_hits
        model = self._get_reranker()
        if model is None:
            return task_hits

        pairs = [[query_text, self._reranker_task_text(hit)] for hit in task_hits]
        try:
            raw_scores = model.predict(pairs, batch_size=self.reranker_batch_size)
        except Exception:
            self._reranker_unavailable = True
            return task_hits
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()
        if not isinstance(raw_scores, list) or len(raw_scores) != len(task_hits):
            return task_hits

        reranked: List[Dict[str, Any]] = []
        for hit, score in zip(task_hits, raw_scores):
            try:
                raw_score = float(score)
            except (TypeError, ValueError):
                raw_score = 0.0
            item = dict(hit)
            item["similarity"] = sigmoid_similarity(raw_score)
            item["_reranker_score"] = raw_score
            reranked.append(item)
        self._reranker_used = True
        reranked.sort(key=lambda h: h["similarity"], reverse=True)
        return reranked

    # ── 검색 + 집계 ──────────────────────────────────────────────────────
    def assign(
        self,
        query_text: str,
        top_k_tasks: int = 20,
        top_n_units: int = 3,
        min_confidence: Optional[float] = None,
        use_llm: bool = False,
        use_hybrid: Optional[bool] = None,
        use_reranker: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """민원 질의 → responsible_unit 후보 리스트.

        min_confidence 미지정 시 설정값(RESPONSIBLE_UNIT_MIN_CONFIDENCE)을 적용한다.
        하한 미달이면 후보가 빈 배열로 폐기된다(자신 없는 출력 억제 = soft 폴백).
        """
        if min_confidence is None:
            min_confidence = self.min_confidence
        if use_hybrid is None:
            use_hybrid = self.use_hybrid
        if use_reranker is None:
            use_reranker = self.use_reranker
        query_terms = extract_key_terms(query_text)
        if use_hybrid:
            task_hits = self._hybrid_task_hits(query_text, top_k_tasks, query_terms)
        else:
            task_hits = self._dense_task_hits(query_text, top_k_tasks)
        prior_hits = query_department_prior_hits(
            query_text,
            allowed_departments=self._department_names(),
        )
        if prior_hits:
            task_hits = [*prior_hits, *task_hits]
        if use_reranker:
            task_hits = self._rerank_task_hits(query_text, task_hits)
        candidates = aggregate_candidates(
            task_hits, query_terms=query_terms,
            top_n=top_n_units, min_confidence=min_confidence,
        )
        for c in candidates:
            c.pop("_hits", None)
            c.pop("_rank_score", None)
            c.pop("_evidence_terms", None)
            c["source"] = RESPONSIBLE_UNIT_SOURCE_BE1

        if use_llm and candidates:
            reranked = self._llm_rerank(query_text, candidates)
            if reranked:
                return reranked
        return candidates

    # ── 선택적 LLM 재랭킹 ────────────────────────────────────────────────
    def _llm_rerank(self, query_text: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """검색 후보 집합 안에서만 LLM 이 선택/근거 보강. 실패 시 빈 리스트(폴백)."""
        import json
        import httpx
        from app.core.config import settings

        allowed = {c["name"] for c in candidates}
        lines = []
        # 후보별 근거 업무 문구를 함께 제공 (name 은 후보 목록으로 고정)
        for c in candidates:
            ev_task = next((e for e in c.get("evidence", []) if len(e) > 6), "")
            lines.append(f"- 부서: {c['name']} | 업무: {ev_task}")
        user = (
            "[후보 부서별 업무]\n" + "\n".join(lines) +
            "\n\n[시민 민원]\n" + query_text[:1500]
        )
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0, "num_predict": 512},
        }
        try:
            with httpx.Client(timeout=settings.OLLAMA_TIMEOUT) as client:
                r = client.post(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat", json=payload)
                r.raise_for_status()
                raw = str(r.json().get("message", {}).get("content", "")).strip()
            parsed = json.loads(raw)
        except Exception:
            return []  # Ollama 불가/파싱 실패 → 벡터 결과 유지

        validated = validate_llm_units(parsed.get("responsible_unit"), allowed)
        return validated


# ── 싱글톤 ───────────────────────────────────────────────────────────────
_assigner: Optional[DepartmentAssigner] = None


def get_department_assigner() -> DepartmentAssigner:
    global _assigner
    if _assigner is None:
        _assigner = DepartmentAssigner()
    return _assigner
