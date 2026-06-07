"""LegalRefMatcher / merge 로직 단위 테스트 (네트워크·API 불필요)."""

import json

from app.structuring.legal_dictionary import LegalRefMatcher, merge_legal_candidates


# ── merge_legal_candidates ────────────────────────────────────────────────
def test_merge_takes_max_confidence_and_unions_evidence():
    a = [{"name": "건축법", "confidence": 0.6, "evidence": ["건축물"], "source": "domain"}]
    b = [{"name": "건축법", "confidence": 0.95, "evidence": ["건축법"], "law_id": "001", "source": "name_match"}]
    out = merge_legal_candidates(a, b)
    assert len(out) == 1
    assert out[0]["confidence"] == 0.95
    assert out[0]["law_id"] == "001"
    assert set(out[0]["evidence"]) >= {"건축법", "건축물"}


def test_merge_sorts_and_limits():
    lst = [
        {"name": "A법", "confidence": 0.5, "evidence": []},
        {"name": "B법", "confidence": 0.9, "evidence": []},
        {"name": "C법", "confidence": 0.7, "evidence": []},
    ]
    out = merge_legal_candidates(lst, top_n=2)
    assert [c["name"] for c in out] == ["B법", "C법"]


# ── Matcher: 사전 기반 직접 매칭 ──────────────────────────────────────────
def _write(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_matcher_name_and_abbr_and_ordinance(tmp_path):
    dic = tmp_path / "law.json"
    ordin = tmp_path / "ordin.json"
    _write(dic, [
        {"name": "건축법", "abbr": "", "law_id": "001"},
        {"name": "개인정보 보호법", "abbr": "개보법", "law_id": "002"},
    ])
    _write(ordin, [{"name": "부산광역시 주차장 조례", "law_id": "B01"}])
    m = LegalRefMatcher(dictionary_path=str(dic), ordinance_path=str(ordin))

    r = m.match("건축법 위반 여부와 개보법 적용, 부산광역시 주차장 조례도 궁금합니다")
    by = {c["name"]: c for c in r}
    assert by["건축법"]["confidence"] == 0.95 and by["건축법"]["law_id"] == "001"
    assert by["건축법"]["source"] == "name_match"
    assert by["개인정보 보호법"]["source"] == "abbr_match"      # 약칭(개보법)으로 매칭 → 정식명 후보
    assert by["부산광역시 주차장 조례"]["source"] == "ordinance"


def test_matcher_longest_match_skips_substring(tmp_path):
    dic = tmp_path / "law.json"
    _write(dic, [{"name": "형법", "law_id": "1"}, {"name": "군형법", "law_id": "2"}])
    m = LegalRefMatcher(dictionary_path=str(dic), ordinance_path=str(tmp_path / "none.json"))
    names = [c["name"] for c in m.match("군형법 위반 신고")]
    assert "군형법" in names
    assert "형법" not in names                                  # 부분문자열(군형법) → 제외


def test_matcher_falls_back_to_domain_lexicon_without_dict(tmp_path):
    # 사전 파일이 없으면 기존 도메인 lexicon 동작(하위호환)
    m = LegalRefMatcher(dictionary_path=str(tmp_path / "no.json"), ordinance_path=str(tmp_path / "no2.json"))
    r = m.match("3톤 미만 지게차 면허 문의")
    assert any(c["name"] == "건설기계관리법" for c in r)
    assert all(c.get("source") == "domain" for c in r)
    for c in r:
        assert "confidence" in c and c["evidence"]


def test_matcher_merges_dict_and_domain(tmp_path):
    dic = tmp_path / "law.json"
    _write(dic, [{"name": "건설기계관리법", "law_id": "777"}])
    m = LegalRefMatcher(dictionary_path=str(dic), ordinance_path=str(tmp_path / "none.json"))
    r = m.match("건설기계관리법상 3톤 미만 지게차 면허")
    cm = next(c for c in r if c["name"] == "건설기계관리법")
    # 사전 직접매칭(0.95)이 도메인(0.6)을 이기고 law_id 부여
    assert cm["confidence"] == 0.95 and cm["law_id"] == "777"
