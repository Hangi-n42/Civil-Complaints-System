"""B5 UrgencyScorer 테스트 — 규칙 폴백(모델 부재)으로 결정적 검증."""

from app.structuring.urgency.scorer import UrgencyScorer, _max_level


def _rule_scorer(tmp_path):
    # 존재하지 않는 모델 경로 → 규칙 폴백
    return UrgencyScorer(model_path=str(tmp_path / "no_model.joblib"))


def test_max_level():
    assert _max_level("보통", "높음") == "높음"
    assert _max_level("긴급", "낮음") == "긴급"


def test_safety_override_to_emergency(tmp_path):
    sc = _rule_scorer(tmp_path)
    r = sc.score("가스 냄새가 나고 붕괴 위험이 있습니다", "안전총괄과")
    assert r["level"] == "긴급" and r["override"] == "safety"
    assert r["method"] == "rule" and r["factors"]["safety"] >= 2


def test_simple_inquiry_low(tmp_path):
    r = _rule_scorer(tmp_path).score("취득세 감면 가능한지 문의드립니다", "세정과")
    assert r["level"] == "낮음" and r["override"] is None


def test_hazard_medium(tmp_path):
    r = _rule_scorer(tmp_path).score("도로에 소음과 파손이 있습니다", "구조물관리과")
    assert r["level"] == "보통"


def test_category_floor_applied(tmp_path):
    r = _rule_scorer(tmp_path).score("단순 문의입니다", "", category_floor="높음")
    assert r["level"] == "높음"


def test_markers_in_factors(tmp_path):
    r = _rule_scorer(tmp_path).score("매일 반복되고 지금도 진행 중이며 모레까지 처리 바랍니다", "")
    f = r["factors"]
    assert f["recurring"] and f["ongoing"] and f["explicit_deadline"]
