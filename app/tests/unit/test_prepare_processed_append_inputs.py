from __future__ import annotations

from pathlib import Path

from scripts.prepare_processed_append_inputs import _build_append_record


def test_build_append_record_preserves_processed_policy_qna_identity():
    raw = {
        "source_id": "175436",
        "source": "국토교통부",
        "consulting_date": "2019-01-02",
        "consulting_category": "교통·물류 > 도로시설물",
        "title": "제한차량 운행허가 신청 방법",
        "client_question": "제한차량 운행허가 신청 방법을 알려주세요.",
        "consultant_answer": "온라인 신청 방법을 안내합니다.",
        "consulting_turns": 1,
    }

    record = _build_append_record(
        raw,
        Path("data/processed/civil_policy_qna_processed.json"),
        "POLICY",
    )

    assert record["case_id"] == "CASE-POLICY-175436"
    assert record["source_id"] == "175436"
    assert record["content_type"] == "policy_qna"
    assert record["document_type"] == "policy_qna"
    assert record["created_at"] == "2019-01-02T00:00:00+09:00"
    assert record["submitted_at"] == "2019-01-02T00:00:00+09:00"
    assert "제한차량 운행허가 신청 방법" in record["search_text"]
    assert "온라인 신청 방법을 안내합니다." in record["search_text"]
    assert "consulting_date" not in record
    assert "consulting_content" not in record
    assert record["metadata"]["adapter"] == "prepare_processed_append_inputs"
    assert record["metadata"]["content_type"] == "policy_qna"
