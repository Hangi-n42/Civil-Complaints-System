"""② 자기검증 + 근거 grounding — 순수 로직 테스트 (Ollama 불필요)."""

from app.structuring.verifier import calibrated_confidence, verify_candidate


def _candidate():
    return {
        "observation": {"text": "연산교차로 도로가 파였다", "confidence": 0.7, "evidence_span": [0, 0]},
        "result": {"text": "지어낸 피해 내용", "confidence": 0.7, "evidence_span": [0, 0], "status": "present"},
        "request": {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
        "context": {"text": "한 달 전부터", "confidence": 0.7, "evidence_span": [0, 0]},
    }


RAW = "연산교차로 도로가 파였다. 한 달 전부터 그렇다. 보수해 주세요."


def _stub_verify(raw, fname, ftext):
    # observation/context 는 근거 있음, result 는 환각(미지원)
    if fname in ("observation", "context"):
        return {"supported": True, "quote": ftext}
    return {"supported": False, "quote": ""}


def test_calibrated_confidence_mapping():
    assert calibrated_confidence(True, "exact") == 0.95
    assert calibrated_confidence(True, "partial") == 0.85
    assert calibrated_confidence(True, "inferred") == 0.80
    assert calibrated_confidence(False, "exact") == 0.20


def test_verify_grounds_supported_and_removes_hallucination():
    c = _candidate()
    verify_candidate(RAW, c, _stub_verify)
    # observation: 근거 있음 → exact span + 높은 confidence + verified
    assert c["observation"]["verified"] is True
    assert c["observation"]["confidence"] >= 0.85
    assert c["observation"]["evidence_span"] != [0, 0]
    # result: 환각 → 텍스트 제거, confidence 낮음, status insufficient
    assert c["result"]["text"] == "" and c["result"]["verified"] is False
    assert c["result"]["confidence"] == 0.20 and c["result"]["status"] == "insufficient"
    # 메타
    assert "observation" in c["verification"]["checked"]
    assert "result" in c["verification"]["removed"]


def test_verify_skips_empty_field():
    c = _candidate()
    verify_candidate(RAW, c, _stub_verify)
    assert "request" not in c["verification"]["checked"]   # 빈 필드는 검증 안 함


def test_verify_keep_unsupported_when_drop_disabled():
    c = _candidate()
    verify_candidate(RAW, c, _stub_verify, drop_unsupported=False)
    assert c["result"]["text"] == "지어낸 피해 내용"       # 제거 안 함
    assert c["result"]["verified"] is False


def test_verify_skips_already_grounded_field():
    # observation 이 이미 grounding(span != [0,0]) → 검증 LLM 호출 없이 verified
    calls = []
    def counting_verify(raw, fname, ftext):
        calls.append(fname)
        return {"supported": True, "quote": ftext}
    c = {
        "observation": {"text": "도로 파손", "confidence": 0.8, "evidence_span": [3, 8]},  # grounded
        "result": {"text": "환각", "confidence": 0.7, "evidence_span": [0, 0], "status": "present"},  # inferred
        "request": {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
        "context": {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
    }
    from app.structuring.verifier import verify_candidate
    verify_candidate("도로 파손 보수 요청", c, counting_verify)
    assert calls == ["result"]                       # grounded observation 은 호출 안 함
    assert c["observation"]["verified"] is True
    assert "observation" in c["verification"]["skipped_grounded"]
    assert "result" in c["verification"]["checked"]
