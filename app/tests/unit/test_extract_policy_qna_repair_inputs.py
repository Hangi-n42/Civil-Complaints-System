from __future__ import annotations

import json

from scripts.extract_policy_qna_repair_inputs import (
    collect_repair_records,
    find_repair_case_ids,
    write_chunks,
)


def test_extract_policy_qna_repair_inputs_selects_invalid_or_fallback(tmp_path):
    structured_path = tmp_path / "structured.json"
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "repair"
    source_dir.mkdir()

    structured_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "CASE-POLICY-1",
                    "structured_by": "constrained",
                    "validation": {"is_valid": True},
                },
                {
                    "case_id": "CASE-POLICY-2",
                    "structured_by": "constrained",
                    "validation": {"is_valid": False, "errors": ["empty_policy_qna_core"]},
                },
                {
                    "case_id": "CASE-POLICY-3",
                    "structured_by": "fallback",
                    "validation": {"is_valid": False},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_dir / "append_input_0001.json").write_text(
        json.dumps(
            [
                {"case_id": "CASE-POLICY-1", "text": "정상"},
                {"case_id": "CASE-POLICY-2", "text": "invalid"},
                {"case_id": "CASE-POLICY-3", "text": "fallback"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    target_ids = find_repair_case_ids(structured_path)
    records, missing = collect_repair_records(source_dir, target_ids)
    written = write_chunks(records, output_dir, records_per_file=1)

    assert target_ids == {"CASE-POLICY-2", "CASE-POLICY-3"}
    assert missing == set()
    assert [record["case_id"] for record in records] == ["CASE-POLICY-2", "CASE-POLICY-3"]
    assert records[0]["force_policy_qna_repair"] is True
    assert records[0]["metadata"]["force_policy_qna_repair"] is True
    assert len(written) == 2
    assert json.loads(written[0].read_text(encoding="utf-8"))[0]["case_id"] == "CASE-POLICY-2"


def test_extract_policy_qna_repair_inputs_reports_missing_case_ids(tmp_path):
    structured_path = tmp_path / "structured.json"
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    structured_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "CASE-POLICY-MISSING",
                    "structured_by": "fallback",
                    "validation": {"is_valid": False},
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_dir / "append_input_0001.json").write_text("[]", encoding="utf-8")

    target_ids = find_repair_case_ids(structured_path)
    records, missing = collect_repair_records(source_dir, target_ids)

    assert records == []
    assert missing == {"CASE-POLICY-MISSING"}
