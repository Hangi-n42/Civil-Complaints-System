"""enrichment 순수 로직 단위 테스트 (모델/네트워크 불필요)."""

from app.structuring.enrichment import (
    FACILITY_KEYWORDS,
    normalize_entity_texts,
)


# ── 시설 체크리스트 고도화 ────────────────────────────────────────────────
def test_facility_keywords_expanded_and_keeps_legacy():
    assert len(FACILITY_KEYWORDS) >= 30          # 기존 8개 → 확장
    for legacy in ["도로", "가로등", "하수구", "교차로", "놀이터"]:
        assert legacy in FACILITY_KEYWORDS       # 기존 키워드 보존(회귀 방지)


# ── entity_texts 정규화 ──────────────────────────────────────────────────
def test_entity_texts_normalizes_variant_to_canonical():
    res = normalize_entity_texts([], "3톤 미만 지게차 면허 문의")
    item = next(r for r in res if r["text"] == "지게차")
    assert item["label"] == "OBJECT"
    assert item["confidence"] >= 0.85
    assert "지게차" in item["evidence"][0]        # evidence 에 원문 근거 포함


def test_entity_texts_variant_maps_to_canonical_굴착기():
    res = normalize_entity_texts([], "포크레인이 인도를 막고 있습니다")
    texts = [r["text"] for r in res]
    assert "굴착기" in texts                       # 포크레인 → 굴착기 정규화
    assert "포크레인" not in texts


def test_entity_texts_folds_facility_entities():
    res = normalize_entity_texts([{"label": "FACILITY", "text": "가로등"}], "가로등 고장")
    g = next(r for r in res if r["text"] == "가로등")
    assert g["confidence"] > 0                      # confidence 포함
    assert g["evidence"]                            # evidence 포함


def test_entity_texts_dedup_and_sorted_by_confidence():
    res = normalize_entity_texts([], "지게차 지게차 가로등")
    assert [r["text"] for r in res].count("지게차") == 1
    confs = [r["confidence"] for r in res]
    assert confs == sorted(confs, reverse=True)


def test_entity_texts_every_item_has_confidence_and_evidence():
    res = normalize_entity_texts([], "흡연부스 옆 풋살장 덕트 보수 요청")
    assert res
    for r in res:
        assert isinstance(r["confidence"], float)
        assert r["evidence"]


def test_entity_texts_lighting_variants_normalize_to_streetlight():
    res = normalize_entity_texts([], "보안등과 공원등이 꺼져 야간 보행이 위험합니다")
    light = next(r for r in res if r["text"] == "가로등")

    assert light["label"] == "OBJECT"
    assert any("보안등" in ev or "공원등" in ev for ev in light["evidence"])
    assert "보안등" not in [r["text"] for r in res]


def test_entity_texts_extracts_administrative_objects():
    res = normalize_entity_texts([], "영주 지역사랑상품권 환불과 청년월세 지원 이사 처리를 문의합니다")
    texts = [r["text"] for r in res]

    assert "지역사랑상품권" in texts
    assert "청년월세" in texts


def test_entity_texts_suppresses_road_legal_reference_only():
    legal_only = normalize_entity_texts([], "도로법과 도로교통법 적용 기준이 궁금합니다")
    real_road = normalize_entity_texts([], "도로가 파손되어 보행로 보수를 요청합니다")

    assert "도로" not in [r["text"] for r in legal_only]
    assert "도로" in [r["text"] for r in real_road]


def test_entity_texts_allows_evidence_fallback_for_missing_raw_span():
    res = normalize_entity_texts([{"label": "FACILITY", "text": "민원대상시설"}], "원문에는 다른 표현만 있습니다")
    item = next(r for r in res if r["text"] == "민원대상시설")

    assert item["evidence"] == ["민원대상시설"]


def test_entity_texts_covers_transport_and_public_facility_samples():
    samples = [
        "BRT 버스전용차선과 SRT 기차 개통 일정이 궁금합니다",
        "시외버스 정류장 노선도와 버스 배차를 개선해 주세요",
        "수도계량기 교체와 상수도 수압 저하를 확인해 주세요",
        "공동주택 스프링클러와 방화문 기준을 문의합니다",
        "전기차 충전기와 태양광 설비 지원 사업이 궁금합니다",
    ]

    assert all(normalize_entity_texts([], text) for text in samples)


def test_entity_texts_covers_culture_reservation_objects():
    res = normalize_entity_texts([], "비회원 예매로 공연 티켓 잔여석 확인과 홈페이지 로그인 오류가 발생했습니다")
    texts = [r["text"] for r in res]

    assert "회원계정" in texts
    assert "예매" in texts
    assert "공연" in texts
    assert "티켓" in texts
    assert "홈페이지" in texts


def test_entity_texts_covers_labor_and_business_admin_objects():
    text = "임금체불과 퇴직금, 고용보험 실업급여, 창업자금 대출, 수출신고 원산지증명서를 문의합니다"
    texts = [r["text"] for r in normalize_entity_texts([], text)]

    assert "임금체불" in texts
    assert "고용보험" in texts
    assert "정책자금" in texts
    assert "대출보증" in texts
    assert "수출입" in texts


def test_entity_texts_covers_housing_construction_vehicle_objects():
    text = "건설업 등록과 하도급대금, 분양권 청약, 전세보증금, 차량등록 명의이전을 확인하고 싶습니다"
    texts = [r["text"] for r in normalize_entity_texts([], text)]

    assert "건설업등록" in texts
    assert "하도급" in texts
    assert "분양" in texts
    assert "전세보증금" in texts
    assert "자동차등록" in texts


def test_entity_texts_suppresses_household_count_as_jeonse_object():
    res = normalize_entity_texts([], "아파트 전세대 소방 점검 일정이 궁금합니다")

    assert "전세보증금" not in [r["text"] for r in res]


def test_entity_texts_covers_program_event_and_facility_use_objects():
    text = "워크숍 강좌 신청과 행사 대관, 체험관 물품보관함 분실물 처리를 문의합니다"
    texts = [r["text"] for r in normalize_entity_texts([], text)]

    assert "교육프로그램" in texts
    assert "행사" in texts
    assert "대관" in texts
    assert "문화시설" in texts
    assert "분실물" in texts


def test_entity_texts_covers_tax_safety_logistics_and_support_objects():
    text = "세금계산서와 부가가치세, 중대재해 위험성평가, 화물 운송, 보조금 지원사업을 문의합니다"
    texts = [r["text"] for r in normalize_entity_texts([], text)]

    assert "세무신고" in texts
    assert "중대재해" in texts
    assert "화물운송" in texts
    assert "지원사업" in texts


# ── legal_refs (요청 #2) ──────────────────────────────────────────────────
from app.structuring.enrichment import classify_legal_refs, build_key_terms


def test_legal_refs_forklift_to_construction_machinery_law():
    res = classify_legal_refs("3톤 미만 지게차 조종 면허 문의")
    assert res[0]["name"] == "건설기계관리법"
    assert "지게차" in res[0]["evidence"]
    assert 0.0 < res[0]["confidence"] <= 0.9


def test_legal_refs_building_law():
    res = classify_legal_refs("무허가 가설건축물 건축법 위반 신고")
    names = [r["name"] for r in res]
    assert "건축법" in names


def test_legal_refs_labor_laws():
    res = classify_legal_refs("임금 체불과 부당해고, 근로계약 위반 문의")
    assert res[0]["name"] == "근로기준법"


def test_legal_refs_confidence_scales_and_capped():
    res = classify_legal_refs("입주자모집 청약 특별공급 일반공급 주택공급")
    top = next(r for r in res if r["name"] == "주택공급에 관한 규칙")
    assert top["confidence"] <= 0.9
    assert top["confidence"] >= 0.6


def test_legal_refs_empty_when_no_signal():
    assert classify_legal_refs("안녕하세요 감사합니다") == []


def test_legal_refs_every_item_has_confidence_and_evidence():
    for r in classify_legal_refs("반려동물 유기견 동물학대 신고"):
        assert isinstance(r["confidence"], float) and r["evidence"]


# ── key_terms (요청 #5) ───────────────────────────────────────────────────
def test_key_terms_prioritizes_specific_objects_and_admin_terms():
    text = "3톤 미만 지게차 면허 적성검사 갱신 신청 절차 문의"
    et = normalize_entity_texts([], text)
    lr = classify_legal_refs(text)
    kt = build_key_terms(text, et, lr)
    assert "지게차" in kt
    assert "적성검사" in kt
    assert 3 <= len(kt) <= 8


def test_key_terms_excludes_generic_words():
    text = "지게차 면허 신청 문의 절차 방법"
    kt = build_key_terms(text, normalize_entity_texts([], text), classify_legal_refs(text))
    for g in ["신청", "문의", "절차", "방법"]:
        assert g not in kt


def test_key_terms_drops_substring_of_longer_term():
    # 'OBJECT' canonical 과 행정어가 부분문자열 관계일 때 더 긴 표현만 유지
    et = [{"text": "가설건축물", "label": "OBJECT", "confidence": 0.9, "evidence": ["가설건축물"]}]
    kt = build_key_terms("가설건축물 건축물 허가", et, classify_legal_refs("가설건축물 건축물 허가"))
    assert "가설건축물" in kt
    assert "건축물" not in kt          # 부분문자열 → 제외


def test_key_terms_respects_limit():
    text = "지게차 굴착기 가로등 면허 허가 등록 갱신 보상 단속 보조금 증명서 예약 보수"
    kt = build_key_terms(text, normalize_entity_texts([], text), classify_legal_refs(text), limit=8)
    assert len(kt) <= 8
