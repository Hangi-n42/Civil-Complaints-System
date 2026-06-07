"""① 구조화 병합(roles/status) + ② 검증 연동 테스트 (Ollama 불필요)."""

from app.structuring.schemas import RuleBasedNERResult, StructuredLLMOutput
from app.structuring.structured_merge import merge_structured

RAW = "옆집 공장이 새벽마다 소음을 내서 잠을 못 잡니다. 단속해 주세요."


def _structured():
    return StructuredLLMOutput(
        observation="옆집 공장이 새벽마다 소음을 내서",
        result="잠을 못 잡니다",
        result_status="present",
        request="단속해 주세요",
        context="",
        complainant="민원인",
        respondent="옆집 공장",
        target_object="소음",
    )


def test_merge_builds_fields_roles_and_status():
    ner = RuleBasedNERResult(entities=[{"label": "HAZARD", "text": "소음"}], extraction_latency_ms=3)
    frag = merge_structured(RAW, ner, _structured(), llm_latency_ms=10, llm_model="m")
    assert frag["observation"]["text"].startswith("옆집 공장")
    assert frag["observation"]["evidence_span"] != [0, 0]          # grounding
    assert frag["result"]["status"] == "present"
    assert frag["roles"]["respondent"]["text"] == "옆집 공장"
    assert frag["roles"]["target_object"]["text"] == "소음"
    assert frag["structured_by"] == "constrained"
    assert frag["extraction_meta"]["decoding"] == "constrained_schema"
    assert frag["entities"] == [{"label": "HAZARD", "text": "소음"}]


def test_merge_empty_field_and_role():
    frag = merge_structured(RAW, RuleBasedNERResult(), _structured(), 0, "m")
    assert frag["context"]["text"] == "" and frag["context"]["evidence_span"] == [0, 0]


def test_merge_with_verifier_removes_hallucination():
    s = _structured()
    s.result = "지어낸 내용"          # 원문에 없음
    def stub(raw, fname, ftext):
        return {"supported": fname != "result", "quote": ftext if fname != "result" else ""}
    frag = merge_structured(RAW, RuleBasedNERResult(), s, 0, "m", verify_fn=stub)
    assert frag["result"]["text"] == ""                            # 환각 제거
    assert "result" in frag["verification"]["removed"]
    assert frag["observation"]["verified"] is True
