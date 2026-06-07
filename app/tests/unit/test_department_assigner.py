"""DepartmentAssigner 순수 로직 단위 테스트 (모델/네트워크 불필요)."""

from app.structuring.department_assigner import (
    aggregate_candidates,
    build_query_text,
    extract_key_terms,
    validate_llm_units,
)


# ── extract_key_terms ────────────────────────────────────────────────────
def test_extract_key_terms_drops_stopwords_and_dedups():
    text = "3톤 미만 지게차 면허 신청 문의 지게차 적성검사"
    terms = extract_key_terms(text)
    assert "지게차" in terms
    assert "적성검사" in terms
    assert "신청" not in terms and "문의" not in terms  # 불용어 제거
    assert terms.count("지게차") == 1                    # 중복 제거


def test_extract_key_terms_limit():
    text = " ".join(f"키워드{i}길이" for i in range(30))
    assert len(extract_key_terms(text, limit=5)) == 5


# ── aggregate_candidates ─────────────────────────────────────────────────
def _hits():
    return [
        {"department": "도로안전과", "task": "포트홀 보수 도로 파손 정비", "similarity": 0.81},
        {"department": "도로안전과", "task": "도로시설물 관리 업무", "similarity": 0.74},
        {"department": "대중교통과", "task": "시내버스 노선 조정", "similarity": 0.40},
    ]


def test_aggregate_uses_max_similarity_and_multihit_bonus():
    res = aggregate_candidates(_hits(), query_terms=["포트홀", "도로", "파손"], top_n=3)
    top = res[0]
    assert top["name"] == "도로안전과"
    # best_sim 0.81 + 보너스(1 extra hit * 0.02) = 0.83
    assert abs(top["confidence"] - 0.83) < 1e-6
    assert res[1]["name"] == "대중교통과"
    assert res[0]["confidence"] > res[1]["confidence"]  # 내림차순


def test_aggregate_evidence_contains_task_and_overlapping_terms():
    res = aggregate_candidates(_hits(), query_terms=["포트홀", "도로", "파손"], top_n=1)
    ev = res[0]["evidence"]
    assert "포트홀 보수 도로 파손 정비" in ev      # 최상위 업무 문구
    assert "포트홀" in ev and "도로" in ev          # 질의 겹침 키워드


def test_aggregate_top_n_and_min_confidence():
    res = aggregate_candidates(_hits(), top_n=1)
    assert len(res) == 1
    res2 = aggregate_candidates(_hits(), min_confidence=0.5)
    assert all(c["confidence"] >= 0.5 for c in res2)
    assert "대중교통과" not in [c["name"] for c in res2]  # 0.40 < 0.5 제외


def test_aggregate_clamps_similarity_range():
    hits = [{"department": "X과", "task": "t", "similarity": 1.5}]
    res = aggregate_candidates(hits)
    assert res[0]["confidence"] <= 0.99


# ── validate_llm_units (환각 방어) ────────────────────────────────────────
def test_validate_llm_drops_hallucinated_names():
    allowed = {"도로안전과", "대중교통과"}
    llm = [
        {"name": "도로안전과", "confidence": 0.9, "evidence": ["포트홀"]},
        {"name": "도로관리 부서", "confidence": 0.8, "evidence": ["도로"]},  # 후보 밖 → 폐기
    ]
    out = validate_llm_units(llm, allowed)
    names = [u["name"] for u in out]
    assert names == ["도로안전과"]


def test_validate_llm_clamps_confidence_and_normalizes_evidence():
    allowed = {"건축정책과"}
    out = validate_llm_units(
        [{"name": "건축정책과", "confidence": 1.7, "evidence": "가설건축물"}], allowed
    )
    assert out[0]["confidence"] == 1.0
    assert out[0]["evidence"] == ["가설건축물"]


def test_validate_llm_handles_bad_input():
    assert validate_llm_units(None, {"A"}) == []
    assert validate_llm_units("oops", {"A"}) == []


# ── build_query_text ─────────────────────────────────────────────────────
def test_build_query_text_orders_keyterms_first():
    q = build_query_text(
        raw_text="긴 민원 원문",
        entity_texts=["지게차"],
        key_terms=["3톤 미만 지게차", "면허"],
    )
    assert q.index("3톤 미만 지게차") < q.index("긴 민원 원문")
