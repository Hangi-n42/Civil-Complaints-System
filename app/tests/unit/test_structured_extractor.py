"""① 제약 디코딩 추출기 — 순수 로직(프롬프트/페이로드/파싱) 테스트 (Ollama 불필요)."""

from app.structuring.structured_extractor import StructuredExtractor, SYSTEM_PROMPT
from app.structuring.schemas import StructuredLLMOutput


def _ext():
    return StructuredExtractor(ollama_url="http://x:11434", model="exaone3.5:7.8b")


def test_payload_uses_schema_format_not_free_json():
    p = _ext().build_payload("민원 본문", temperature=0.1)
    fmt = p["format"]
    assert isinstance(fmt, dict)                      # 자유 "json"이 아니라 스키마 dict
    assert "result_status" in fmt["properties"]
    assert fmt["properties"]["result_status"]["enum"] == ["present", "pending", "insufficient"]
    assert fmt["additionalProperties"] is False
    assert p["options"]["temperature"] == 0.1
    assert p["messages"][0]["role"] == "system" and p["messages"][1]["role"] == "user"


def test_system_prompt_has_guidelines_and_roles():
    for kw in ["observation", "complainant", "respondent", "target_object", "지어내지", "예시"]:
        assert kw in SYSTEM_PROMPT


def test_retry_suffix_added():
    p = _ext().build_payload("t", temperature=0.0, retry=True)
    assert "순수 JSON" in p["messages"][0]["content"]


def test_parse_valid_and_extra_keys_ignored():
    raw = '{"observation":"가로등 고장","result":"","result_status":"pending","request":"교체","context":"","complainant":"주민","respondent":"","target_object":"가로등","junk":"x"}'
    out = StructuredExtractor.parse_content(raw)
    assert isinstance(out, StructuredLLMOutput)
    assert out.observation == "가로등 고장" and out.result_status == "pending"
    assert out.target_object == "가로등"
    assert not hasattr(out, "junk")


def test_parse_empty_returns_none():
    assert StructuredExtractor.parse_content("") is None


def test_parse_missing_keys_default_empty():
    out = StructuredExtractor.parse_content('{"observation":"x"}')
    assert out.request == "" and out.result_status == "insufficient"
