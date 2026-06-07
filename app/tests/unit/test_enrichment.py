"""enrichment 순수 로직 단위 테스트 (모델/네트워크 불필요)."""

from app.structuring.enrichment import (
    FACILITY_KEYWORDS,
    classify_issue_type,
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


# ── issue_type 분류 ──────────────────────────────────────────────────────
def test_issue_type_license_dominates():
    res = classify_issue_type("운전면허 적성검사 1종 보통 응시 문의")
    assert res[0]["name"] == "면허/자격"
    assert res[0]["confidence"] > 0.6
    assert res[0]["evidence"]                        # 매칭 근거 포함


def test_issue_type_facility_repair():
    res = classify_issue_type("도로가 파손되어 보수와 정비를 요청합니다")
    assert res[0]["name"] == "시설 개선/보수"


def test_issue_type_confidence_scales_with_matches():
    one = classify_issue_type("보상 문의")          # 1 매칭
    two = classify_issue_type("손해배상 보상 합의금")  # 다수 매칭
    assert two[0]["confidence"] > one[0]["confidence"]


def test_issue_type_empty_when_no_signal():
    assert classify_issue_type("안녕하세요 잘 부탁드립니다") == []


def test_issue_type_top_n_limit():
    text = "면허 허가 갱신 보상 단속 지원금 증빙 예약 보수 법령"
    assert len(classify_issue_type(text, top_n=3)) == 3


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
    it = classify_issue_type(text)
    lr = classify_legal_refs(text)
    kt = build_key_terms(text, et, it, lr)
    assert "지게차" in kt
    assert "적성검사" in kt
    assert 3 <= len(kt) <= 8


def test_key_terms_excludes_generic_words():
    text = "지게차 면허 신청 문의 절차 방법"
    kt = build_key_terms(text, normalize_entity_texts([], text), classify_issue_type(text), classify_legal_refs(text))
    for g in ["신청", "문의", "절차", "방법"]:
        assert g not in kt


def test_key_terms_drops_substring_of_longer_term():
    # 'OBJECT' canonical 과 행정어가 부분문자열 관계일 때 더 긴 표현만 유지
    et = [{"text": "가설건축물", "label": "OBJECT", "confidence": 0.9, "evidence": ["가설건축물"]}]
    kt = build_key_terms("가설건축물 건축물 허가", et, [], classify_legal_refs("가설건축물 건축물 허가"))
    assert "가설건축물" in kt
    assert "건축물" not in kt          # 부분문자열 → 제외


def test_key_terms_respects_limit():
    text = "지게차 굴착기 가로등 면허 허가 등록 갱신 보상 단속 보조금 증명서 예약 보수"
    kt = build_key_terms(text, normalize_entity_texts([], text), classify_issue_type(text), classify_legal_refs(text), limit=8)
    assert len(kt) <= 8
