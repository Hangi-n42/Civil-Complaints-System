"""admin 카테고리 통계 집계(순수 함수) 단위 테스트."""

from app.api.routers.admin import _split_pipe, aggregate_categories


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
