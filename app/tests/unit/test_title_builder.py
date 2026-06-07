"""공용 제목 생성: '고객:' 제거 + 빈 title 자동 보정."""
from app.core.title_builder import build_case_title


def test_strips_leading_customer_label():
    assert build_case_title(explicit_title="고객: 도로가 파손됐어요") == "도로가 파손됐어요"


def test_strips_label_with_space_variant():
    assert build_case_title(raw_text="고객 :  가로등이 안 켜져요") == "가로등이 안 켜져요"


def test_label_only_in_lead_position():
    # 본문 중간의 '고객'은 보존
    assert build_case_title(explicit_title="고객센터 운영 문의") == "고객센터 운영 문의"


def test_empty_title_falls_back_to_category():
    assert build_case_title(explicit_title="", raw_text="", category="교통행정") == "교통행정 관련 민원"


def test_whitespace_title_falls_back():
    assert build_case_title(explicit_title="   ", category="환경위생") == "환경위생 관련 민원"


def test_normal_title_unchanged():
    assert build_case_title(explicit_title="BRT 언제 생기나요") == "BRT 언제 생기나요"
