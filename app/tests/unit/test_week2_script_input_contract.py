from __future__ import annotations

import json

from scripts import generate_week2_delivery_samples as sample_script
from scripts import run_week2_be1_e2e as e2e_script


def test_week2_delivery_sample_uses_structuring_text_without_answer():
    raw = {
        "source_id": "RAW-SAMPLE-001",
        "source": "부산광역시",
        "consulting_date": "20240102",
        "consulting_category": "교통",
        "consulting_content": "제목 : 버스 지연\n\nQ : 출근 시간 버스가 자주 늦습니다.\n\nA : 담당 부서에 전달했습니다.",
        "raw_text": "A : 담당 부서에 전달했습니다.",
    }
    source_file = sample_script.PROJECT_ROOT / "data" / "raw_data" / "sample.json"

    record = sample_script.normalize_record(raw, source_file)

    assert record["case_id"] == "RAW-SAMPLE-001"
    assert record["created_at"] == "2024-01-02"
    assert record["region"] == "부산광역시"
    assert record["raw_text"] == "버스 지연\n출근 시간 버스가 자주 늦습니다."


def test_week2_e2e_collect_raw_samples_uses_structuring_text_without_answer(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    payload = [
        {
            "source_id": "RAW-E2E-001",
            "source": "부산광역시",
            "consulting_date": "20240203",
            "consulting_category": "환경",
            "consulting_content": "제목 : 쓰레기 수거\n\nQ : 골목 쓰레기 수거 기준이 궁금합니다.\n\nA : 안내드리겠습니다.",
        }
    ]
    (raw_dir / "sample.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(e2e_script, "RAW_ROOT", raw_dir)
    monkeypatch.setattr(e2e_script, "PROJECT_ROOT", tmp_path)

    rows = e2e_script._collect_raw_samples(limit=1)

    assert len(rows) == 1
    assert rows[0]["case_id"] == "RAW-E2E-001"
    assert rows[0]["source"] == "부산광역시"
    assert rows[0]["created_at"] == "2024-02-03"
    assert rows[0]["category"] == "환경"
    assert rows[0]["raw_text"] == "쓰레기 수거\n골목 쓰레기 수거 기준이 궁금합니다."
    assert rows[0]["metadata"]["source_id"] == "RAW-E2E-001"
