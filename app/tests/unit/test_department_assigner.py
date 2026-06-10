"""DepartmentAssigner 순수 로직 단위 테스트 (모델/네트워크 불필요)."""

import json

from app.structuring.department_assigner import (
    DepartmentAssigner,
    RESPONSIBLE_UNIT_SOURCE_BE1,
    aggregate_candidates,
    build_query_text,
    expand_department_task_text,
    extract_key_terms,
    query_department_prior_hits,
    rrf_similarity,
    sigmoid_similarity,
    validate_llm_units,
)


# ── extract_key_terms ────────────────────────────────────────────────────
def test_expand_department_task_text_adds_department_and_domain_terms():
    text = expand_department_task_text("건설행정과", "건설기계 위임 사무 총괄")

    assert text.startswith("건설행정과 건설기계 위임 사무 총괄")
    assert "건설기계관리법" in text
    assert "지게차" in text
    assert "굴착기" in text
    assert "기중기" in text
    assert "조종사면허" in text


def test_expand_department_task_text_keeps_expansion_trigger_limited():
    text = expand_department_task_text("택시운수과", "법인택시 면허 관리")

    assert "법인택시 면허 관리" in text
    assert "건설기계관리법" not in text
    assert "지게차" not in text


def test_expand_department_task_text_reuses_waste_lexicon_terms():
    text = expand_department_task_text("자원순환과", "폐기물 관련 주민지원기금 운용 및 관리")

    assert "폐기물관리법" in text
    assert "쓰레기" in text
    assert "생활폐기물" in text
    assert "무단투기" in text


def test_expand_department_task_text_adds_task_triggered_terms_only():
    text = expand_department_task_text(
        "건축정책과",
        "건축관련 협의사항 및 민원처리(연제구,금정구,부산진구,동래구)",
    )

    assert "건축관련 협의사항 및 민원처리" in text
    assert "방화유리창" in text
    assert "내진설계" in text
    assert "조경면적" in text
    assert "열관류율" in text


def test_expand_department_task_text_keeps_alias_noise_out_of_urban_vitality():
    text = expand_department_task_text("도시공간활력과", "도시재생사업(선정, 위원회, 컨설팅, 공모)")

    assert "도시재생사업" in text
    assert "도시재생전략계획" in text
    assert "개발행위허가" not in text
    assert "도시계획시설" not in text
    assert "지구단위계획" not in text


def test_task_corpus_preserves_original_task_metadata_with_expanded_text(tmp_path):
    master_path = tmp_path / "departments.json"
    task = "종합건설업 행정처분(총괄)"
    master_path.write_text(
        json.dumps([
            {"department": "건설행정과", "url": "", "tasks": [task]},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    assigner = DepartmentAssigner(master_path=str(master_path), persist_directory=str(tmp_path / "chroma"))

    record = assigner._task_corpus()[0]

    assert record["task"] == task
    assert record["text"] != task
    assert "건설업등록" in record["text"]
    assert "표준시장단가" in record["text"]


def test_expand_department_task_text_does_not_spread_to_irrelevant_department():
    text = expand_department_task_text("택시운수과", "법인택시 면허 관리")

    assert "방화유리창" not in text
    assert "표준시장단가" not in text
    assert "장기수선충당금" not in text


def test_bm25_uses_task_expansion_for_sparse_only_department_match(tmp_path):
    master_path = tmp_path / "departments.json"
    master_path.write_text(
        json.dumps([
            {"department": "도로안전과", "url": "", "tasks": ["도로시설물 관리 업무"]},
            {"department": "건축정책과", "url": "", "tasks": ["건축관련 협의사항 및 민원처리"]},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    assigner = DepartmentAssigner(master_path=str(master_path), persist_directory=str(tmp_path / "chroma"))

    ranked = assigner._bm25_ranked_task_ids("방화유리창 설치 기준", ["방화유리창", "설치", "기준"], fetch_k=2)

    assert ranked[0] == "1_0"


def test_department_bm25_uses_expanded_task_text(tmp_path):
    master_path = tmp_path / "departments.json"
    master_path.write_text(
        json.dumps([
            {"department": "택시운수과", "url": "", "tasks": ["법인택시 면허 관리"]},
            {"department": "건설행정과", "url": "", "tasks": ["건설기계 위임 사무 총괄"]},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    assigner = DepartmentAssigner(master_path=str(master_path), persist_directory=str(tmp_path / "chroma"))

    ranked = assigner._bm25_ranked_task_ids("지게차 조종사면허 갱신", ["지게차", "조종사면허"], fetch_k=2)

    assert ranked[0] == "1_0"


def test_hybrid_task_hits_keeps_sparse_only_records(tmp_path):
    master_path = tmp_path / "departments.json"
    master_path.write_text(
        json.dumps([
            {"department": "택시운수과", "url": "", "tasks": ["법인택시 면허 관리"]},
            {"department": "건설행정과", "url": "", "tasks": ["건설기계 위임 사무 총괄"]},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    assigner = DepartmentAssigner(master_path=str(master_path), persist_directory=str(tmp_path / "chroma"))
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "택시운수과", "task": "법인택시 면허 관리", "similarity": 0.9}
    ]

    hits = assigner._hybrid_task_hits("지게차 조종사면허 갱신", 5, ["지게차", "조종사면허"])

    assert any(h["doc_id"] == "1_0" and h["department"] == "건설행정과" for h in hits)
    assert all(0.0 <= h["similarity"] <= 1.0 for h in hits)
    assert next(h for h in hits if h["doc_id"] == "1_0")["similarity"] < hits[0]["similarity"]


def test_query_department_prior_hits_match_high_precision_terms():
    hits = query_department_prior_hits(
        "7호선 지하철 출구 위치 조정을 요청합니다",
        allowed_departments={"철도시설과", "도로안전과"},
    )

    assert hits[0]["department"] == "철도시설과"
    assert hits[0]["similarity"] >= 0.74


def test_query_department_prior_hits_respects_allowed_departments():
    hits = query_department_prior_hits(
        "음식물처리기 지원사업을 문의합니다",
        allowed_departments={"도로안전과"},
    )

    assert hits == []


def test_query_department_prior_hits_cover_holdout_weak_domains():
    cases = [
        ("마을버스 배차와 대중교통 개선을 요청합니다", "대중교통과"),
        ("건축물관리법 정기점검 대상과 건축물 용도를 문의합니다", "건축정책과"),
        ("지구단위계획 변경과 도시계획시설 관련 민원입니다", "도시계획과"),
        ("인공조명 빛공해로 생활이 어렵습니다", "환경정책과"),
        ("야생동물 너구리와 까마귀 개체수 관리가 필요합니다", "환경정책과"),
        ("가족센터 다문화가정 지원 정책을 문의합니다", "여성가족과"),
        ("가족돌봄수당과 출산 보조 정책을 문의합니다", "여성가족과"),
        ("국가유공자 보훈 명예수당 기준을 문의합니다", "복지정책과"),
        ("전문건설업 기재사항 변경신청 과태료 기준을 문의합니다", "건설행정과"),
        ("임대사업자 표준임대차 계약서 위반 과태료가 궁금합니다", "주택정책과"),
        ("개발제한구역 토지형질변경과 개발행위허가 기준을 문의합니다", "도시계획과"),
        ("용도변경을 위한 방화창 설치 기준을 문의합니다", "건축정책과"),
        ("어린이공원 벌집 제거와 공원관리 요청을 드립니다", "공원여가정책과"),
        ("산지전용과 보전산지 내 등산로 공사 기준을 문의합니다", "푸른숲도시과"),
        ("금연구역 흡연 단속과 고령산모 의료비지원 일정을 문의합니다", "건강정책과"),
        ("철도교통 지하철 역 출구 위치 조정을 요청합니다", "철도시설과"),
    ]

    for query, department in cases:
        hits = query_department_prior_hits(query, allowed_departments={department})

        assert hits
        assert hits[0]["department"] == department
        assert hits[0]["similarity"] >= 0.74


def test_assign_merges_query_department_prior_hits(tmp_path):
    master_path = tmp_path / "departments.json"
    master_path.write_text(
        json.dumps([
            {"department": "대중교통과", "url": "", "tasks": ["시내버스 노선 조정"]},
            {"department": "철도시설과", "url": "", "tasks": ["도시철도 시설 확충"]},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    assigner = DepartmentAssigner(master_path=str(master_path), persist_directory=str(tmp_path / "chroma"))
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "대중교통과", "task": "시내버스 노선 조정", "similarity": 0.6}
    ]

    out = assigner.assign("7호선 지하철 출구를 개선해주세요", top_n_units=1)

    assert out[0]["name"] == "철도시설과"
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_assign_defaults_to_dense_hits(tmp_path):
    assigner = DepartmentAssigner(master_path=str(tmp_path / "missing.json"), persist_directory=str(tmp_path / "chroma"))
    assigner.use_hybrid = False
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "도로안전과", "task": "도로 안전시설 관리", "similarity": 0.7}
    ]
    assigner._hybrid_task_hits = lambda query, fetch_k, query_terms: [
        {"doc_id": "1_0", "department": "자원순환과", "task": "폐기물 관리", "similarity": 0.9}
    ]

    out = assigner.assign("도로 안전", top_n_units=1)

    assert out[0]["name"] == "도로안전과"
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_assign_can_opt_into_hybrid_hits(tmp_path):
    assigner = DepartmentAssigner(master_path=str(tmp_path / "missing.json"), persist_directory=str(tmp_path / "chroma"))
    assigner.use_hybrid = False
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "도로안전과", "task": "도로 안전시설 관리", "similarity": 0.7}
    ]
    assigner._hybrid_task_hits = lambda query, fetch_k, query_terms: [
        {"doc_id": "1_0", "department": "자원순환과", "task": "폐기물 관리", "similarity": 0.9}
    ]

    out = assigner.assign("폐기물 관리", top_n_units=1, use_hybrid=True)

    assert out[0]["name"] == "자원순환과"
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_assign_can_opt_into_reranker_hits(tmp_path):
    class FakeReranker:
        def predict(self, pairs, batch_size):
            assert batch_size == 16
            assert pairs[0][0] == "공원 풋살장 관리"
            return [-3.0, 3.0]

    assigner = DepartmentAssigner(master_path=str(tmp_path / "missing.json"), persist_directory=str(tmp_path / "chroma"))
    assigner._reranker_model = FakeReranker()
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "공원여가정책과", "task": "공원 조성 관리", "similarity": 0.9},
        {"doc_id": "1_0", "department": "생활체육과", "task": "체육시설 관리", "similarity": 0.6},
    ]

    out = assigner.assign("공원 풋살장 관리", top_n_units=1, use_reranker=True)

    assert out[0]["name"] == "생활체육과"
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_assign_reranker_falls_back_when_model_unavailable(tmp_path):
    assigner = DepartmentAssigner(master_path=str(tmp_path / "missing.json"), persist_directory=str(tmp_path / "chroma"))
    assigner._reranker_unavailable = True
    assigner._dense_task_hits = lambda query, fetch_k: [
        {"doc_id": "0_0", "department": "공원여가정책과", "task": "공원 조성 관리", "similarity": 0.9},
        {"doc_id": "1_0", "department": "생활체육과", "task": "체육시설 관리", "similarity": 0.6},
    ]

    out = assigner.assign("공원 관리", top_n_units=1, use_reranker=True)

    assert out[0]["name"] == "공원여가정책과"
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_rrf_similarity_scales_by_active_rankings():
    assert rrf_similarity(1 / 61, ranking_count=1) == 1.0
    assert rrf_similarity(1 / 61, ranking_count=2) == 0.5


def test_sigmoid_similarity_maps_reranker_logit_to_unit_range():
    assert sigmoid_similarity(0.0) == 0.5
    assert sigmoid_similarity(4.0) > 0.98
    assert sigmoid_similarity(-4.0) < 0.02


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
    assert abs(top["_rank_score"] - 0.83) < 1e-6
    assert res[1]["name"] == "대중교통과"
    assert res[0]["_rank_score"] > res[1]["_rank_score"]  # 순위 점수 내림차순
    assert res[0]["confidence"] >= res[1]["confidence"]   # 상대 신뢰도도 top이 높음


def test_aggregate_evidence_contains_task_and_overlapping_terms():
    res = aggregate_candidates(_hits(), query_terms=["포트홀", "도로", "파손"], top_n=1)
    ev = res[0]["evidence"]
    assert "포트홀 보수 도로 파손 정비" in ev      # 최상위 업무 문구
    assert "포트홀" in ev and "도로" in ev          # 질의 겹침 키워드


def test_aggregate_top_n_and_min_confidence():
    res = aggregate_candidates(_hits(), top_n=1)
    assert len(res) == 1
    res2 = aggregate_candidates(_hits(), query_terms=["포트홀", "도로", "파손"], min_confidence=0.7)
    assert all(c["confidence"] >= 0.7 for c in res2)
    assert "대중교통과" not in [c["name"] for c in res2]  # 상대 confidence 하한으로 제외


def test_aggregate_clamps_similarity_range():
    hits = [{"department": "X과", "task": "t", "similarity": 1.5}]
    res = aggregate_candidates(hits)
    assert res[0]["confidence"] <= 0.99


def test_aggregate_relative_confidence_drops_flat_margin():
    hits = [
        {"department": "A과", "task": "업무 A", "similarity": 0.63},
        {"department": "B과", "task": "업무 B", "similarity": 0.62},
        {"department": "C과", "task": "업무 C", "similarity": 0.61},
    ]

    res = aggregate_candidates(hits)

    assert [c["name"] for c in res] == ["A과", "B과", "C과"]
    assert res[0]["confidence"] < 0.4


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
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


def test_validate_llm_clamps_confidence_and_normalizes_evidence():
    allowed = {"건축정책과"}
    out = validate_llm_units(
        [{"name": "건축정책과", "confidence": 1.7, "evidence": "가설건축물"}], allowed
    )
    assert out[0]["confidence"] == 1.0
    assert out[0]["evidence"] == ["가설건축물"]
    assert out[0]["source"] == RESPONSIBLE_UNIT_SOURCE_BE1


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


# ── min_confidence 하한 (자신 없는 후보 억제, #346 B) ──────────────────────
def test_aggregate_min_confidence_abstains():
    hits = [
        {"department": "택시운수과", "task": "법인택시 면허 관리", "similarity": 0.63},
        {"department": "도로계획과", "task": "황령3터널 관련 업무", "similarity": 0.57},
    ]
    # 하한 0.7 이면 둘 다 미달 → 빈 배열(폐기)
    assert aggregate_candidates(hits, min_confidence=0.7) == []
    # 하한 0.2 이면 마진상 top 후보만 통과
    out = aggregate_candidates(hits, min_confidence=0.2)
    assert [c["name"] for c in out] == ["택시운수과"]
