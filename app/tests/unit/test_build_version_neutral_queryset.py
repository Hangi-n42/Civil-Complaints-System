"""버전 중립 평가 쿼리셋 생성기 단위 테스트.

검증 핵심:
- source_id 역참조 매핑이 정상 동작
- 중립 쿼리 텍스트에 v1 구조화 4요소 마커가 포함되지 않음(raw 보장)
- query_id <-> source_id 매핑 유지
- 원문 누락 시 조용히 폴백하지 않고 명시적으로 보고
"""

from __future__ import annotations

import json

from scripts.build_version_neutral_queryset import (
    STRUCT_MARKERS,
    build_neutral_queries,
    build_source_map,
)

# Q/A 마커를 쓰는 일반 지역 원천 1건(고용노동부 형식)
RAW_RECORD = {
    "source_id": "S1",
    "source": "고용노동부",
    "consulting_content": (
        "Q : 1년 미만 근로자의 잔존 연차 미사용 수당 지급을 문의합니다.\n\n"
        "A : 근로기준법 제60조에 따라 1년 미만 근로자도 개근 시 연차가 발생합니다."
    ),
}


def test_build_source_map_indexes_by_source_id(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.json").write_text(json.dumps([RAW_RECORD], ensure_ascii=False), encoding="utf-8")
    mapping = build_source_map(src)
    assert "S1" in mapping
    assert mapping["S1"]["source"] == "고용노동부"


def test_neutral_query_has_no_structuring_markers():
    queries = [{"query_id": "Q-1", "source_id": "S1", "source": "고용노동부", "category": "-"}]
    rows, missing, marker_hit = build_neutral_queries(queries, {"S1": RAW_RECORD})

    assert len(rows) == 1 and not missing and not marker_hit
    row = rows[0]
    assert row["query_id"] == "Q-1"
    assert row["source_id"] == "S1"
    assert row["query_type"] == "raw_citizen_text"
    assert row["query"]  # 비어 있지 않음
    for marker in STRUCT_MARKERS:
        assert marker not in row["query"]  # 구조화본이 아님


def test_consultant_answer_is_excluded():
    # civil_text 는 민원인 질문만 사용하므로 상담사 답변(A) 본문은 제외되어야 한다.
    queries = [{"query_id": "Q-1", "source_id": "S1"}]
    rows, _, _ = build_neutral_queries(queries, {"S1": RAW_RECORD})
    assert "근로기준법 제60조" not in rows[0]["query"]


def test_missing_source_is_reported_not_silently_dropped():
    queries = [{"query_id": "Q-2", "source_id": "GONE"}]
    rows, missing, _ = build_neutral_queries(queries, {})
    assert rows == []
    assert missing == [("Q-2", "GONE")]


def test_query_id_source_id_mapping_preserved():
    queries = [
        {"query_id": "Q-1", "source_id": "S1"},
        {"query_id": "Q-2", "source_id": "GONE"},
    ]
    rows, missing, _ = build_neutral_queries(queries, {"S1": RAW_RECORD})
    assert {r["query_id"]: r["source_id"] for r in rows} == {"Q-1": "S1"}
    assert ("Q-2", "GONE") in missing
