"""admin 카테고리 통계 집계(순수 함수) 단위 테스트."""

from app.api.routers.admin import (
    _count_values,
    _split_pipe,
    aggregate_categories,
    aggregate_overview,
)


def test_split_pipe():
    assert _split_pipe("대중교통과|도로안전과|환경정책과") == ["대중교통과", "도로안전과", "환경정책과"]
    assert _split_pipe(" A | B ") == ["A", "B"]
    assert _split_pipe("") == []
    assert _split_pipe(None) == []


def _idx():
    return [
        {"primary": "교통·물류", "year": "2024"},
        {"primary": "교통·물류", "year": "2023"},
        {"primary": "사회복지", "year": "2024"},
        {"primary": None, "year": "2024"},
    ]


def test_aggregate_all_counts_and_years():
    out = aggregate_categories(_idx(), "all")
    assert out["year"] == "all"
    assert out["total"] == 4
    assert out["available_years"] == ["2024", "2023"]  # 내림차순
    counts = {c["name"]: c["count"] for c in out["categories"]}
    assert counts["교통·물류"] == 2
    assert counts["사회복지"] == 1
    assert counts["미분류"] == 1  # primary None → 미분류 버킷


def test_aggregate_year_filter():
    out = aggregate_categories(_idx(), "2024")
    assert out["year"] == "2024"
    assert out["total"] == 3
    counts = {c["name"]: c["count"] for c in out["categories"]}
    assert counts["교통·물류"] == 1
    assert counts["사회복지"] == 1
    assert "교통·물류" in counts and counts.get("미분류") == 1


def test_aggregate_sorted_desc():
    index = [{"primary": "A", "year": "2024"}] * 2 + [{"primary": "B", "year": "2024"}] * 5
    out = aggregate_categories(index, "all")
    assert [c["name"] for c in out["categories"]] == ["B", "A"]  # 건수 내림차순


def test_aggregate_none_year_means_all():
    out = aggregate_categories(_idx(), None)
    assert out["year"] == "all"
    assert out["total"] == 4


def test_count_values_scalar_and_list():
    rows = [
        {"r": "서울", "i": ["a", "b"]},
        {"r": "서울", "i": ["a"]},
        {"r": "경기", "i": []},
    ]
    assert dict(_count_values(rows, lambda d: d["r"])) == {"서울": 2, "경기": 1}
    assert dict(_count_values(rows, lambda d: d["i"])) == {"a": 2, "b": 1}


def _ov_idx():
    return [
        {"primary": "교통·물류", "year": "2024", "region": "서울", "issues": ["단속/점검", "허가/등록"]},
        {"primary": "교통·물류", "year": "2023", "region": "경기", "issues": ["단속/점검"]},
        {"primary": "사회복지", "year": "2024", "region": "서울", "issues": []},
    ]


def test_aggregate_overview_all():
    out = aggregate_overview(_ov_idx(), "all")
    assert out["total"] == 3
    assert {c["name"]: c["count"] for c in out["categories"]}["교통·물류"] == 2
    assert {r["name"]: r["count"] for r in out["regions"]} == {"서울": 2, "경기": 1}
    assert {i["name"]: i["count"] for i in out["issues"]}["단속/점검"] == 2
    # 연도별 추이: 전체, 오름차순
    assert out["trend"] == [{"year": "2023", "count": 1}, {"year": "2024", "count": 2}]


def test_aggregate_overview_year_filter_keeps_full_trend():
    out = aggregate_overview(_ov_idx(), "2024")
    assert out["total"] == 2  # 2024만
    assert {r["name"] for r in out["regions"]} == {"서울"}
    # trend는 연도 필터와 무관하게 전체
    assert out["trend"] == [{"year": "2023", "count": 1}, {"year": "2024", "count": 2}]


def test_aggregate_overview_category_drilldown():
    out = aggregate_overview(_ov_idx(), "all", ["교통·물류"])
    assert out["category"] == ["교통·물류"]
    assert out["total"] == 2  # 교통·물류 2건(2024 서울, 2023 경기)
    assert {r["name"]: r["count"] for r in out["regions"]} == {"서울": 1, "경기": 1}
    assert {i["name"]: i["count"] for i in out["issues"]} == {"단속/점검": 2, "허가/등록": 1}
    # 추이는 카테고리 드릴다운을 반영(해당 분야의 연도별 분포)
    assert out["trend"] == [{"year": "2023", "count": 1}, {"year": "2024", "count": 1}]
    # 카테고리 목록은 셀렉터라 그대로 전체 유지
    assert {c["name"]: c["count"] for c in out["categories"]} == {"교통·물류": 2, "사회복지": 1}


def test_aggregate_overview_category_and_year_combined():
    out = aggregate_overview(_ov_idx(), "2024", ["교통·물류"])
    assert out["total"] == 1  # 2024 ∩ 교통·물류
    assert {r["name"] for r in out["regions"]} == {"서울"}
    # trend는 연도와 무관하게 카테고리 전체 연도 축
    assert out["trend"] == [{"year": "2023", "count": 1}, {"year": "2024", "count": 1}]


def test_aggregate_overview_multi_category_union():
    out = aggregate_overview(_ov_idx(), "all", ["교통·물류", "사회복지"])
    assert sorted(out["category"]) == ["교통·물류", "사회복지"]
    assert out["total"] == 3  # 두 분야 합집합 = 전체 3건
    assert {r["name"]: r["count"] for r in out["regions"]} == {"서울": 2, "경기": 1}
    assert {i["name"]: i["count"] for i in out["issues"]} == {"단속/점검": 2, "허가/등록": 1}


def test_aggregate_overview_string_category_is_coerced():
    # 단일 문자열도 1-요소 리스트로 허용된다.
    out = aggregate_overview(_ov_idx(), "all", "사회복지")
    assert out["category"] == ["사회복지"]
    assert out["total"] == 1
