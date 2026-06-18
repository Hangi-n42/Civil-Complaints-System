from __future__ import annotations

from app.structuring.civil_category import classify_civil_category, civil_category_label


def test_civil_category_prefers_be1_responsible_unit_for_primary_and_secondary():
    result = classify_civil_category(
        text="버스 배차 간격 조정을 요청합니다.",
        category="기타",
        responsible_unit=[
            {
                "name": "대중교통과",
                "confidence": 0.82,
                "source": "be1_structured",
            }
        ],
        key_terms=["버스", "배차"],
    )

    assert result["primary"] == "교통·물류"
    assert result["secondary"] == "버스"
    assert "대중교통과" in result["evidence"]
    assert result["source"].startswith("responsible_unit")


def test_civil_category_keeps_department_specific_primary_when_keyword_is_cross_domain():
    result = classify_civil_category(
        text="근린공원 산책로 조명 고장과 임시 안전 조치를 요청합니다.",
        category="도로안전",
        responsible_unit=[{"name": "공원여가정책과", "confidence": 0.7, "source": "be1_structured"}],
        key_terms=["공원", "조명", "안전"],
    )

    assert result["primary"] == "공원녹지·환경"
    assert result["secondary"] == "공원"
    assert "공원여가정책과" in result["evidence"]


def test_civil_category_uses_keywords_when_department_is_missing():
    result = classify_civil_category(
        text="하천 산책로에 쓰레기와 악취가 심해 정기 청소를 요청합니다.",
        category="기타",
        responsible_unit=[],
        entity_texts=[{"text": "하천 산책로"}],
        key_terms=["하천", "쓰레기", "악취"],
    )

    assert result["primary"] == "공원녹지·환경"
    assert result["secondary"] in {"하천", "폐기물", "생활환경"}
    assert result["confidence"] > 0.4


def test_civil_category_alias_falls_back_without_overwriting_unknown():
    result = classify_civil_category(text="일반 문의입니다.", category="문화관광")

    assert result["primary"] == "문화체육관광"
    assert result["secondary"] == "관광"
    assert civil_category_label(result) == "문화체육관광 > 관광"


def test_civil_category_defaults_to_administration_for_no_signal():
    result = classify_civil_category(text="안녕하세요 문의드립니다.", category="기타")

    assert result["primary"] == "행정"
    assert result["secondary"] == "일반민원"
    assert result["source"] == "default"
