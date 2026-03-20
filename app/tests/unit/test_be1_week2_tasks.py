from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.service import IngestionService
from scripts.evaluate_structuring import main as run_structuring_eval


@pytest.mark.asyncio
async def test_deduplicate_hash_and_near_duplicate():
    service = IngestionService()
    docs = [
        {"case_id": "1", "text": "가로등 점검이 필요합니다."},
        {"case_id": "2", "text": "가로등 점검이 필요합니다."},
        {"case_id": "3", "text": "가로등 점검이 필요합니다!"},
        {"case_id": "4", "text": "하수구 누수 점검이 필요합니다."},
    ]

    deduped = await service.deduplicate(docs)
    kept_texts = [row["text"] for row in deduped]

    assert len(deduped) == 2
    assert "가로등 점검이 필요합니다." in kept_texts
    assert "하수구 누수 점검이 필요합니다." in kept_texts


def test_evaluate_structuring_outputs_metrics(tmp_path: Path):
    gold = [
        {
            "case_id": "CASE-1",
            "observation": {"text": "가로등이 고장났습니다."},
            "result": {"text": "야간 통행이 위험합니다."},
            "request": {"text": "수리를 요청합니다."},
            "context": {"text": "서울시 강남구"},
        },
        {
            "case_id": "CASE-2",
            "observation": {"text": "소음이 심합니다."},
            "result": {"text": "수면 방해가 발생합니다."},
            "request": {"text": "단속 바랍니다."},
            "context": {"text": "야간 23시"},
        },
    ]
    pred = [
        {
            "case_id": "CASE-1",
            "observation": {"text": "가로등이 고장났습니다."},
            "result": {"text": "야간 통행이 위험합니다."},
            "request": {"text": "수리를 요청합니다."},
            "context": {"text": "서울시 강남구"},
            "validation": {"is_valid": True, "errors": [], "warnings": []},
        },
        {
            "case_id": "CASE-2",
            "observation": {"text": "소음 민원이 있습니다."},
            "result": {"text": ""},
            "request": {"text": "조치 바랍니다."},
            "context": {"text": "23시"},
            "validation": {"is_valid": False, "errors": ["invalid_confidence:result"], "warnings": []},
        },
    ]

    gold_path = tmp_path / "gold.json"
    pred_path = tmp_path / "pred.json"
    out_path = tmp_path / "report.json"

    gold_path.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    pred_path.write_text(json.dumps(pred, ensure_ascii=False), encoding="utf-8")

    run_structuring_eval(str(gold_path), str(pred_path), str(out_path))

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["gold_count"] == 2
    assert report["pred_count"] == 2
    assert "metrics" in report
    assert "quality" in report
    assert report["quality"]["schema_pass_rate"] == 0.5
