"""부서 라우팅 기반 시민 표시용 민원 카테고리 매핑."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


PRIMARY_CATEGORIES: Tuple[str, ...] = (
    "경제",
    "일자리·노동·교육",
    "사회복지",
    "여성·가족",
    "보건·건강",
    "도시·건축·주택",
    "안전",
    "공원녹지·환경",
    "교통·물류",
    "해양농수산",
    "행정",
    "문화체육관광",
)

DEFAULT_PRIMARY = "행정"
DEFAULT_SECONDARY = "일반민원"

# 부산시 분야별정보 메뉴와 부서 업무명을 기준으로 한 부서 우선 매핑이다.
# 부서 하나가 복수 주제를 가질 수 있으므로 primary와 secondary 후보를 함께 둔다.
DEPARTMENT_CATEGORY_RULES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "경제정책과": ("경제", ("경제정책",)),
    "금융창업정책관": ("경제", ("금융", "창업")),
    "금융블록체인담당관": ("경제", ("금융", "블록체인")),
    "중소상공인지원과": ("경제", ("소상공인", "중소기업")),
    "기업지원과": ("경제", ("기업지원",)),
    "투자유치과": ("경제", ("투자유치",)),
    "산업정책과": ("경제", ("산업정책",)),
    "산업입지과": ("경제", ("산업단지",)),
    "반도체신소재과": ("경제", ("전략산업", "신소재")),
    "미래에너지산업과": ("경제", ("에너지산업", "신재생에너지")),
    "창업벤처담당관": ("경제", ("창업", "벤처")),
    "일자리노동과": ("일자리·노동·교육", ("일자리", "노동")),
    "창조교육과": ("일자리·노동·교육", ("교육", "평생학습")),
    "지산학협력과": ("일자리·노동·교육", ("대학협력", "인재양성")),
    "청년정책과": ("일자리·노동·교육", ("청년",)),
    "복지정책과": ("사회복지", ("복지정책", "긴급복지")),
    "돌봄복지과": ("사회복지", ("돌봄", "사회서비스")),
    "노인복지과": ("사회복지", ("노인복지",)),
    "장애인복지과": ("사회복지", ("장애인복지",)),
    "여성가족과": ("여성·가족", ("여성", "가족")),
    "출산보육과": ("여성·가족", ("보육", "출산")),
    "아동청소년과": ("여성·가족", ("아동청소년",)),
    "인구정책담당관": ("여성·가족", ("인구정책",)),
    "건강정책과": ("보건·건강", ("건강정책", "금연")),
    "감염병관리과": ("보건·건강", ("감염병", "방역")),
    "보건위생과": ("보건·건강", ("위생", "식품")),
    "바이오헬스과": ("보건·건강", ("바이오헬스",)),
    "건축정책과": ("도시·건축·주택", ("건축허가", "건축물관리")),
    "주택정책과": ("도시·건축·주택", ("주택정책", "공동주택")),
    "도시정비과": ("도시·건축·주택", ("재개발", "재건축")),
    "도시계획과": ("도시·건축·주택", ("도시계획", "지구단위계획")),
    "시설계획과": ("도시·건축·주택", ("도시계획시설",)),
    "토지정보과": ("도시·건축·주택", ("토지정보", "부동산")),
    "건설행정과": ("도시·건축·주택", ("건설업", "건설기계")),
    "기술심사과": ("도시·건축·주택", ("건설기술",)),
    "도시공간활력과": ("도시·건축·주택", ("도시재생", "노후계획도시")),
    "도시공간전략과": ("도시·건축·주택", ("공간전략",)),
    "생활공간혁신과": ("도시·건축·주택", ("생활공간",)),
    "북항재개발추진과": ("도시·건축·주택", ("북항재개발",)),
    "안전정책과": ("안전", ("안전정책",)),
    "자연재난과": ("안전", ("자연재난", "침수")),
    "사회재난과": ("안전", ("사회재난",)),
    "재난예방담당관": ("안전", ("재난예방", "소방안전")),
    "중대재해예방과": ("안전", ("중대재해", "산업안전")),
    "원자력안전과": ("안전", ("원자력안전",)),
    "특별사법경찰과": ("안전", ("단속", "특별사법경찰")),
    "구조구급과": ("안전", ("구조구급",)),
    "방호조사과": ("안전", ("화재조사", "소방")),
    "119종합상황실": ("안전", ("119", "재난상황")),
    "119특수대응단": ("안전", ("119", "특수재난")),
    "119안전체험관": ("안전", ("안전체험",)),
    "환경정책과": ("공원녹지·환경", ("환경정책", "생활환경")),
    "탄소중립정책과": ("공원녹지·환경", ("탄소중립", "대기")),
    "자원순환과": ("공원녹지·환경", ("폐기물", "재활용")),
    "공원여가정책과": ("공원녹지·환경", ("공원", "공원시설")),
    "공원도시과": ("공원녹지·환경", ("공원",)),
    "푸른숲도시과": ("공원녹지·환경", ("산림", "녹지")),
    "하천관리과": ("공원녹지·환경", ("하천",)),
    "공공하수인프라과": ("공원녹지·환경", ("하수", "배수")),
    "맑은물정책과": ("공원녹지·환경", ("물환경", "상수도")),
    "대중교통과": ("교통·물류", ("버스", "대중교통")),
    "택시운수과": ("교통·물류", ("택시",)),
    "도로안전과": ("교통·물류", ("도로시설물", "도로안전")),
    "도로계획과": ("교통·물류", ("도로계획", "도로건설")),
    "철도시설과": ("교통·물류", ("철도", "도시철도")),
    "교통혁신과": ("교통·물류", ("교통정책",)),
    "공항기획과": ("교통·물류", ("공항", "항공")),
    "신공항도시과": ("교통·물류", ("신공항",)),
    "신공항사업지원단": ("교통·물류", ("신공항",)),
    "트라이포트기획과": ("교통·물류", ("물류", "트라이포트")),
    "해양수도정책과": ("해양농수산", ("해양정책",)),
    "해운항만과": ("해양농수산", ("항만", "해운")),
    "수산정책과": ("해양농수산", ("수산",)),
    "수산진흥과": ("해양농수산", ("수산진흥",)),
    "농축산유통과": ("해양농수산", ("농축산", "유통")),
    "반려동물과": ("해양농수산", ("동물보호", "반려동물")),
    "문화예술과": ("문화체육관광", ("문화예술", "공연")),
    "문화유산과": ("문화체육관광", ("문화유산",)),
    "영상콘텐츠산업과": ("문화체육관광", ("영상콘텐츠",)),
    "관광정책과": ("문화체육관광", ("관광",)),
    "관광마이스산업과": ("문화체육관광", ("관광", "마이스")),
    "생활체육과": ("문화체육관광", ("생활체육", "체육시설")),
    "체육정책과": ("문화체육관광", ("체육정책",)),
    "전국체전기획단": ("문화체육관광", ("체육행사",)),
    "통합민원과": ("행정", ("민원",)),
    "권익보호담당관": ("행정", ("권익보호", "감사")),
    "국제협력과": ("행정", ("국제교류",)),
    "빅테이터과": ("행정", ("데이터", "디지털행정")),
}

CATEGORY_ALIAS_RULES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "경제": ("경제", ("경제",)),
    "복지": ("사회복지", ("복지정책",)),
    "사회복지": ("사회복지", ("복지정책",)),
    "여성가족": ("여성·가족", ("여성", "가족")),
    "보건": ("보건·건강", ("보건",)),
    "건강": ("보건·건강", ("건강",)),
    "문화관광": ("문화체육관광", ("문화", "관광")),
    "교통": ("교통·물류", ("교통",)),
    "교통행정": ("교통·물류", ("교통행정",)),
    "도로안전": ("교통·물류", ("도로시설물", "도로안전")),
    "환경": ("공원녹지·환경", ("환경",)),
    "환경위생": ("공원녹지·환경", ("생활환경", "위생")),
    "주거복지": ("도시·건축·주택", ("주거복지", "주택")),
    "안전": ("안전", ("생활안전",)),
}

KEYWORD_CATEGORY_RULES: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (("버스",), "교통·물류", "버스"),
    (("택시",), "교통·물류", "택시"),
    (("철도",), "교통·물류", "철도"),
    (("지하철",), "교통·물류", "철도"),
    (("도로",), "교통·물류", "도로시설물"),
    (("포트홀",), "교통·물류", "도로시설물"),
    (("가로등",), "교통·물류", "도로시설물"),
    (("보안등",), "교통·물류", "도로시설물"),
    (("건축",), "도시·건축·주택", "건축허가"),
    (("건축허가",), "도시·건축·주택", "건축허가"),
    (("재개발",), "도시·건축·주택", "재개발"),
    (("재건축",), "도시·건축·주택", "재개발"),
    (("공동주택",), "도시·건축·주택", "공동주택"),
    (("공원",), "공원녹지·환경", "공원"),
    (("산림",), "공원녹지·환경", "산림"),
    (("하천",), "공원녹지·환경", "하천"),
    (("하수",), "공원녹지·환경", "하수"),
    (("쓰레기",), "공원녹지·환경", "폐기물"),
    (("폐기물",), "공원녹지·환경", "폐기물"),
    (("악취",), "공원녹지·환경", "생활환경"),
    (("침수",), "안전", "자연재난"),
    (("태풍",), "안전", "자연재난"),
    (("화재",), "안전", "사회재난"),
    (("감염병",), "보건·건강", "감염병"),
    (("코로나",), "보건·건강", "감염병"),
    (("어린이집",), "여성·가족", "보육"),
    (("장애인",), "사회복지", "장애인복지"),
    (("노인",), "사회복지", "노인복지"),
    (("문화",), "문화체육관광", "문화예술"),
    (("공연",), "문화체육관광", "공연"),
    (("관광",), "문화체육관광", "관광"),
    (("체육",), "문화체육관광", "생활체육"),
    (("수산",), "해양농수산", "수산"),
    (("항만",), "해양농수산", "항만"),
    (("반려동물",), "해양농수산", "동물보호"),
    (("창업",), "경제", "창업"),
    (("소상공인",), "경제", "소상공인"),
    (("청년",), "일자리·노동·교육", "청년"),
    (("임금",), "일자리·노동·교육", "노동"),
    (("교육",), "일자리·노동·교육", "교육"),
)


def _normalize_match_text(value: Any) -> str:
    """공백과 대소문자 흔들림을 줄여 규칙 비교용 문자열로 만든다."""
    return re.sub(r"\s+", "", str(value or "").casefold())


def _append_unique(target: List[str], values: Iterable[Any]) -> None:
    """중복 없이 순서를 보존해 문자열 값을 추가한다."""
    for value in values:
        text = " ".join(str(value or "").split())
        if text and text not in target:
            target.append(text)


def _signal_values(items: Any, keys: Sequence[str] = ("name", "text")) -> List[str]:
    """dict/list/string 형태의 구조화 신호에서 표시 가능한 값을 뽑는다."""
    if items is None:
        return []
    if isinstance(items, str):
        return [item for item in re.split(r"[|,]", items) if item.strip()]
    if isinstance(items, dict):
        return [str(items.get(key) or "").strip() for key in keys if str(items.get(key) or "").strip()]
    if isinstance(items, list):
        values: List[str] = []
        for item in items:
            _append_unique(values, _signal_values(item, keys=keys))
        return values
    return [str(items).strip()] if str(items).strip() else []


def _responsible_unit_items(value: Any) -> List[Dict[str, Any]]:
    """담당부서 후보를 dict 리스트로 표준화한다."""
    if isinstance(value, list):
        items = value
    elif value:
        items = [value]
    else:
        items = []

    out: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("unit") or item.get("text") or "").strip()
            if name:
                out.append({**item, "name": name})
        else:
            name = str(item or "").strip()
            if name:
                out.append({"name": name, "source": "department_name"})
    return out


def _add_score(
    scores: Dict[str, Dict[str, Any]],
    *,
    primary: str,
    secondary_values: Sequence[str],
    amount: float,
    evidence: Sequence[str],
    source: str,
) -> None:
    """primary/secondary별 점수를 누적한다."""
    if primary not in PRIMARY_CATEGORIES:
        return
    bucket = scores.setdefault(
        primary,
        {"score": 0.0, "secondary": {}, "evidence": [], "sources": []},
    )
    bucket["score"] += amount
    _append_unique(bucket["evidence"], evidence)
    _append_unique(bucket["sources"], [source])
    secondary_scores: Dict[str, float] = bucket["secondary"]
    for secondary in secondary_values:
        if not secondary:
            continue
        secondary_scores[secondary] = secondary_scores.get(secondary, 0.0) + amount


def _category_from_alias(category: Any) -> Tuple[str, Tuple[str, ...]] | None:
    normalized = _normalize_match_text(category)
    if not normalized:
        return None
    for alias, rule in CATEGORY_ALIAS_RULES.items():
        if _normalize_match_text(alias) == normalized:
            return rule
    return None


def _keyword_text(
    *,
    text: str,
    category: Any,
    entity_texts: Any,
    key_terms: Any,
) -> str:
    values: List[str] = [text, str(category or "")]
    values.extend(_signal_values(entity_texts))
    values.extend(_signal_values(key_terms, keys=("term", "text", "name")))
    return _normalize_match_text(" ".join(values))


def classify_civil_category(
    *,
    text: str = "",
    category: Any = "",
    responsible_unit: Any = None,
    entity_texts: Any = None,
    key_terms: Any = None,
) -> Dict[str, Any]:
    """민원 처리인에게 보여줄 primary/secondary 카테고리를 산출한다.

    기존 source category는 지역/기관별 값이라 프론트 표시 품질이 낮을 수 있다.
    담당부서 라우팅 결과가 있으면 이를 우선하고, 부족할 때 원문 키워드와
    기존 category를 보조 신호로만 사용한다.
    """
    scores: Dict[str, Dict[str, Any]] = {}

    for item in _responsible_unit_items(responsible_unit):
        department = item["name"]
        rule = DEPARTMENT_CATEGORY_RULES.get(department)
        if not rule:
            continue
        primary, secondary = rule
        raw_confidence = item.get("confidence")
        try:
            confidence = float(raw_confidence) if raw_confidence not in (None, "") else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        source = str(item.get("source") or "department_name")
        base = 4.0 if source == "be1_structured" else 2.5
        _add_score(
            scores,
            primary=primary,
            secondary_values=secondary,
            amount=base + min(max(confidence, 0.0), 1.0),
            evidence=[department],
            source="responsible_unit",
        )

    search_text = _keyword_text(
        text=text,
        category=category,
        entity_texts=entity_texts,
        key_terms=key_terms,
    )
    for terms, primary, secondary in KEYWORD_CATEGORY_RULES:
        if all(_normalize_match_text(term) in search_text for term in terms):
            _add_score(
                scores,
                primary=primary,
                secondary_values=(secondary,),
                amount=1.35,
                evidence=terms,
                source="keyword",
            )

    alias_rule = _category_from_alias(category)
    if alias_rule:
        primary, secondary = alias_rule
        _add_score(
            scores,
            primary=primary,
            secondary_values=secondary,
            amount=1.0,
            evidence=[str(category)],
            source="category_alias",
        )

    if not scores:
        return {
            "primary": DEFAULT_PRIMARY,
            "secondary": DEFAULT_SECONDARY,
            "secondary_candidates": [DEFAULT_SECONDARY],
            "confidence": 0.3,
            "evidence": [],
            "source": "default",
        }

    ranked = sorted(scores.items(), key=lambda item: (-item[1]["score"], PRIMARY_CATEGORIES.index(item[0])))
    primary, bucket = ranked[0]
    secondary_ranked = sorted(bucket["secondary"].items(), key=lambda item: (-item[1], item[0]))
    secondary_candidates = [name for name, _score in secondary_ranked[:3]] or [DEFAULT_SECONDARY]
    confidence = min(0.95, 0.45 + float(bucket["score"]) * 0.07)

    return {
        "primary": primary,
        "secondary": secondary_candidates[0],
        "secondary_candidates": secondary_candidates,
        "confidence": round(confidence, 4),
        "evidence": bucket["evidence"][:8],
        "source": "+".join(bucket["sources"]) or "unknown",
    }


def civil_category_label(category: Dict[str, Any]) -> str:
    """프론트/리포트에서 쓰기 쉬운 '대분류 > 세부태그' 문자열을 만든다."""
    primary = str(category.get("primary") or DEFAULT_PRIMARY)
    secondary = str(category.get("secondary") or DEFAULT_SECONDARY)
    return f"{primary} > {secondary}" if secondary else primary
