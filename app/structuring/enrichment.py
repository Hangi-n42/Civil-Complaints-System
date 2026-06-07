"""BE1 구조화 산출물 고도화 — 검색 신호 보강 필드 생성.

요청 #1 entity_texts 정규화 + 요청 #4 issue_type 분류.
규칙 #6 준수: 모든 항목에 confidence 와 evidence(원문 근거 문구)를 포함한다.

설계 원칙:
  - 결정적(deterministic) 사전/규칙 기반. 모델·네트워크 불필요 → 단위 테스트 가능.
  - confidence 는 매칭 강도에서 유도한 '미보정' 휴리스틱이다. BE2 는 상대 강도로만 사용.
  - evidence 는 원문에서 실제로 매칭된 짧은 문구다(왜 그렇게 판단했는지 보여줌).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# ──────────────────────────────────────────────────────────────────────────
# 시설 체크리스트 고도화 (기존 8개 → 확장)
# service.py 의 _facility_keywords 로 사용된다. 저모호성 시설 명사 위주.
# ──────────────────────────────────────────────────────────────────────────
FACILITY_KEYWORDS: List[str] = [
    # 도로/교통 시설
    "도로", "교차로", "횡단보도", "보도블록", "과속방지턱", "가드레일",
    "신호등", "가로등", "표지판", "버스정류장", "택시승강장", "주차장", "육교", "지하차도",
    # 상하수/환경 시설
    "하수구", "맨홀", "배수구", "정화조", "상수도", "하수도", "정수장", "쓰레기통", "환기구", "덕트",
    # 공원/체육/생활 시설
    "공원", "놀이터", "체육관", "운동장", "풋살장", "수영장", "정자", "벤치", "흡연부스",
    # 건축/공동주택 시설
    "옹벽", "담장", "승강기", "엘리베이터", "에스컬레이터", "계단", "가설건축물", "공사",
]

# ──────────────────────────────────────────────────────────────────────────
# 객체 정규화 사전 (entity_texts)
#   canonical(표준 객체명) → 표면형(변이) 목록.
#   표면형이 원문에 등장하면 canonical 로 정규화하고, 좌측 수식어를 포함한
#   짧은 span 을 evidence 로 잡는다. 예: "3톤 미만 지게차" → text=지게차.
# ──────────────────────────────────────────────────────────────────────────
OBJECT_LEXICON: Dict[str, List[str]] = {
    "지게차": ["지게차"],
    "굴착기": ["굴착기", "굴삭기", "포크레인"],
    "크레인": ["크레인", "기중기"],
    "건설기계": ["건설기계", "중장비"],
    "가로등": ["가로등"],
    "신호등": ["신호등"],
    "가로수": ["가로수"],
    "포트홀": ["포트홀", "도로 파임", "도로파임"],
    "맨홀": ["맨홀"],
    "흡연부스": ["흡연부스", "흡연실", "흡연구역"],
    "풋살장": ["풋살장"],
    "덕트": ["덕트"],
    "환기구": ["환기구", "급배기구"],
    "승강기": ["승강기", "엘리베이터", "리프트"],
    "에스컬레이터": ["에스컬레이터", "무빙워크"],
    "가설건축물": ["가설건축물", "가설 건축물", "컨테이너"],
    "옹벽": ["옹벽"],
    "주차장": ["주차장", "주차타워"],
    "버스정류장": ["버스정류장", "버스 정류장", "정류장", "정류소"],
    "쓰레기": ["쓰레기", "폐기물", "생활폐기물"],
    "반려동물": ["반려동물", "반려견", "반려묘"],
    "유기동물": ["유기견", "유기묘", "유기동물", "길고양이", "들개"],
    "현수막": ["현수막", "불법광고물", "광고물"],
}

def _find_span(text: str, surface: str) -> str:
    """surface 가 등장하는 위치에서 좌측 수식어(한글/영숫자 0~8자)를 포함한 짧은 span 을 반환."""
    pat = re.compile(r"([0-9A-Za-z가-힣]{0,8}\s?" + re.escape(surface) + r")")
    m = pat.search(text)
    if not m:
        return surface
    return m.group(1).strip()


def normalize_entity_texts(
    entities: List[Dict[str, str]],
    raw_text: str,
) -> List[Dict[str, Any]]:
    """원문 + 규칙 NER 결과에서 '실제 대상 객체'를 정규화해 반환.

    Returns:
        [{"text": canonical, "label": "OBJECT"|"FACILITY",
          "confidence": float, "evidence": [span]}, ...]
        text 기준 중복 제거, confidence 내림차순.
    """
    text = raw_text or ""
    by_canonical: Dict[str, Dict[str, Any]] = {}

    # 1) 객체 사전 스캔 (정규화의 핵심)
    for canonical, surfaces in OBJECT_LEXICON.items():
        for surface in surfaces:
            if surface not in text:
                continue
            span = _find_span(text, surface)
            # canonical 자체가 그대로 등장하면 신뢰도 ↑, 변이로만 등장하면 약간 ↓
            conf = 0.9 if canonical in text else 0.85
            slot = by_canonical.get(canonical)
            if slot is None or conf > slot["confidence"]:
                by_canonical[canonical] = {
                    "text": canonical, "label": "OBJECT",
                    "confidence": conf, "evidence": [span],
                }
            break  # canonical 당 한 번만

    # 2) 규칙 NER 의 FACILITY 엔티티를 객체로 흡수 (사전에 없던 시설 보강)
    for ent in entities or []:
        if not isinstance(ent, dict) or ent.get("label") != "FACILITY":
            continue
        t = str(ent.get("text", "")).strip()
        if not t or t in by_canonical:
            continue
        by_canonical[t] = {
            "text": t, "label": "FACILITY",
            "confidence": 0.8, "evidence": [_find_span(text, t)],
        }

    out = list(by_canonical.values())
    out.sort(key=lambda r: r["confidence"], reverse=True)
    return out


# ──────────────────────────────────────────────────────────────────────────
# 쟁점 유형 분류 (issue_type)
#   유형 → 트리거 어휘. 일반어("신청/신고") 단독은 피하고 변별력 있는 복합어 사용.
# ──────────────────────────────────────────────────────────────────────────
ISSUE_TYPE_LEXICON: Dict[str, List[str]] = {
    "면허/자격": ["면허", "자격증", "적성검사", "응시", "운전면허", "조종", "기능사", "기사자격", "1종", "2종"],
    "허가/등록": ["허가", "인허가", "등록", "영업신고", "개설", "사업자등록", "승인", "점용허가", "건축허가"],
    "갱신/연장": ["갱신", "연장", "재발급", "만료", "유효기간"],
    "보상/배상": ["보상", "배상", "손해배상", "피해보상", "변상", "합의금", "위자료"],
    "단속/점검": ["단속", "점검", "적발", "위반", "불법", "과태료", "계도"],
    "지원금/급여": ["지원금", "보조금", "급여", "수당", "바우처", "장려금", "환급", "지급"],
    "증빙/서류": ["증명서", "구비서류", "제출서류", "등본", "확인서", "발급", "증빙"],
    "예매/예약": ["예매", "예약", "매표", "입장권", "좌석", "관람권"],
    "시설 개선/보수": ["보수", "정비", "수리", "교체", "복구", "파손", "고장", "개선", "설치"],
    "법령 해석": ["법령", "조례", "규정", "유권해석", "적용기준", "법적근거", "해석"],
}


def classify_issue_type(text: str, top_n: int = 3) -> List[Dict[str, Any]]:
    """민원이 무엇을 묻거나 요구하는지 유형화한다.

    Returns:
        [{"name": 유형, "confidence": float, "evidence": [매칭어...]}, ...]
        confidence 내림차순, 매칭 0 유형 제외.

    confidence = min(0.95, 0.5 + 0.14 × 매칭어수)  (미보정 휴리스틱)
    """
    text = text or ""
    results: List[Dict[str, Any]] = []
    for name, triggers in ISSUE_TYPE_LEXICON.items():
        matched: List[str] = []
        for kw in triggers:
            if kw in text and kw not in matched:
                matched.append(kw)
        if not matched:
            continue
        confidence = round(min(0.95, 0.5 + 0.14 * len(matched)), 2)
        results.append({"name": name, "confidence": confidence, "evidence": matched[:3]})

    results.sort(key=lambda r: (r["confidence"], len(r["evidence"])), reverse=True)
    return results[:top_n]


# ──────────────────────────────────────────────────────────────────────────
# 법령 후보 (legal_refs) — 요청 #2
#   실제 대한민국 현행 법령명만 사용한다(환각 금지). 확정이 아니라 '후보'.
#   법령 → 트리거 어휘. 트리거가 원문에 등장하면 후보로 제시(confidence+evidence).
# ──────────────────────────────────────────────────────────────────────────
LEGAL_REF_LEXICON: Dict[str, List[str]] = {
    "건설기계관리법": ["지게차", "굴착기", "굴삭기", "기중기", "건설기계", "조종사면허", "중장비"],
    "건축법": ["건축물", "가설건축물", "건축허가", "용도변경", "위반건축물", "무허가", "증축", "대수선"],
    "주택법": ["주택공급", "입주자모집", "분양", "청약", "공동주택", "주택조합"],
    "주택공급에 관한 규칙": ["입주자모집", "청약", "특별공급", "일반공급", "주택공급"],
    "근로기준법": ["근로계약", "임금", "휴직", "해고", "연차", "퇴직금", "근로시간", "체불"],
    "고용보험법": ["실업급여", "구직급여", "육아휴직급여", "고용보험", "고용유지지원금"],
    "도로법": ["도로점용", "도로굴착", "점용허가", "도로점용허가"],
    "도로교통법": ["신호위반", "불법주정차", "불법주차", "과속", "횡단보도", "주정차"],
    "주차장법": ["주차장", "부설주차장", "주차구획"],
    "식품위생법": ["식품접객", "영업신고", "위생점검", "음식점", "유통기한"],
    "소음·진동관리법": ["소음", "진동", "공사소음"],
    "악취방지법": ["악취"],
    "대기환경보전법": ["분진", "매연", "대기오염", "비산먼지"],
    "폐기물관리법": ["폐기물", "무단투기", "생활폐기물", "쓰레기 무단"],
    "동물보호법": ["반려동물", "유기동물", "동물학대", "맹견", "반려견", "길고양이"],
    "옥외광고물 등의 관리와 옥외광고산업 진흥에 관한 법률": ["현수막", "불법광고물", "옥외광고", "광고물"],
    "국민기초생활 보장법": ["기초생활수급", "생계급여", "수급자", "기초수급"],
    "자동차관리법": ["자동차등록", "차량말소", "번호판", "정기검사"],
}


def classify_legal_refs(text: str, top_n: int = 4) -> List[Dict[str, Any]]:
    """민원과 관련 있을 가능성이 있는 현행 법령 '후보'를 제시한다 (요청 #2).

    Returns:
        [{"name": 법령명, "confidence": float, "evidence": [매칭어...]}, ...]
        confidence 내림차순.

    confidence = min(0.9, 0.45 + 0.15 × 매칭어수)  (미보정 휴리스틱)
    주의: 매칭은 어휘 동시출현일 뿐 법적 적용을 단정하지 않는다. 반드시 '후보'로 사용.
    """
    text = text or ""
    results: List[Dict[str, Any]] = []
    for name, triggers in LEGAL_REF_LEXICON.items():
        matched: List[str] = []
        for kw in triggers:
            if kw in text and kw not in matched:
                matched.append(kw)
        if not matched:
            continue
        confidence = round(min(0.9, 0.45 + 0.15 * len(matched)), 2)
        results.append({"name": name, "confidence": confidence, "evidence": matched[:3]})

    results.sort(key=lambda r: (r["confidence"], len(r["evidence"])), reverse=True)
    return results[:top_n]


# ──────────────────────────────────────────────────────────────────────────
# 핵심 키워드 (key_terms) — 요청 #5
#   entity_texts / issue_type / legal_refs + 행정어 사전을 종합해
#   검색 변별력 있는 명사·행정어를 3~8개 랭킹 추출한다. 일반어는 배제.
# ──────────────────────────────────────────────────────────────────────────
# 검색 신호가 강한 행정·법무 어휘(원문에 등장하면 가중).
ADMIN_TERMS: List[str] = [
    "면허", "자격증", "적성검사", "허가", "인허가", "등록", "갱신", "연장", "재발급",
    "과태료", "단속", "점검", "보상", "배상", "보조금", "지원금", "급여", "수당", "바우처",
    "증명서", "등본", "확인서", "예약", "예매", "보수", "정비", "청약", "분양", "입주자모집",
    "근로계약", "임금", "휴직", "해고", "퇴직금", "실업급여", "건축허가", "용도변경",
    "점용허가", "무단투기", "영업신고", "위반건축물", "가설건축물",
]
# key_terms 에서 제외할 일반어(검색 변별력 없음).
_KEY_TERM_GENERIC = {
    "신청", "문의", "절차", "방법", "요청", "관련", "내용", "처리", "민원", "사항",
    "안내", "가능", "여부", "부탁", "확인", "문제", "발생", "경우", "필요", "궁금",
}


def build_key_terms(
    text: str,
    entity_texts: List[Dict[str, Any]],
    issue_types: List[Dict[str, Any]],
    legal_refs: List[Dict[str, Any]],
    limit: int = 8,
    min_terms: int = 3,
) -> List[str]:
    """검색용 핵심 키워드를 랭킹 추출한다 (요청 #5).

    우선순위(가중치): entity_texts(객체) > 행정어 사전 > issue_type 근거 > legal_refs 근거.
    일반어 제외, 다른 키워드의 부분문자열이면 제외(더 구체적인 표현 우선), 3~8개.
    """
    text = text or ""
    scores: Dict[str, float] = {}

    def add(term: str, s: float) -> None:
        t = (term or "").strip()
        if len(t) < 2 or t in _KEY_TERM_GENERIC:
            return
        if scores.get(t, 0.0) < s:
            scores[t] = s

    for e in entity_texts or []:
        add(str(e.get("text", "")), 3.0)
    for kw in ADMIN_TERMS:
        if kw in text:
            add(kw, 2.4)
    for it in issue_types or []:
        for ev in it.get("evidence", []):
            add(str(ev), 2.0)
    for lr in legal_refs or []:
        for ev in lr.get("evidence", []):
            add(str(ev), 1.8)

    ranked = sorted(scores, key=lambda t: (scores[t], len(t)), reverse=True)

    out: List[str] = []
    for t in ranked:
        # 이미 선택된 더 긴 키워드의 부분문자열이면 건너뜀 (예: '지게차' vs '소형 지게차')
        if any(t != o and t in o for o in out):
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return out
