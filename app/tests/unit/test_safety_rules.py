"""B2 안전 규칙 단위 테스트 (순수)."""

from app.structuring.urgency.safety_rules import detect_safety


def test_detects_clear_threats():
    for t in ["가스 냄새가 나서 무섭습니다", "축대가 붕괴될 것 같아요", "감전 위험이 있습니다",
              "보도에서 미끄럽니다", "사람이 넘어지는 걸 봤어요", "도로에 싱크홀이 생겼습니다"]:
        assert detect_safety(t)["safety_flag"] == 1, t


def test_negation_suppresses():
    assert detect_safety("전혀 위험하지 않습니다")["safety_flag"] == 0


def test_non_safety_zero():
    for t in ["취득세 감면 문의드립니다", "분리수거 요일이 궁금합니다", "행사 일정 안내 부탁드려요"]:
        assert detect_safety(t)["safety_flag"] == 0, t


def test_evidence_and_score():
    r = detect_safety("화재 위험이 있고 추락 사고 우려됩니다")
    assert r["score"] >= 2 and r["evidence"]
