from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.service import IngestionService
from app.core.config import settings
from app.structuring.schemas import FourElementsLLMOutput
from app.structuring.service import StructuringService
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
            "validation": {"is_valid": True, "errors": []},
        },
        {
            "case_id": "CASE-2",
            "observation": {"text": "소음 민원이 있습니다."},
            "result": {"text": ""},
            "request": {"text": "조치 바랍니다."},
            "context": {"text": "23시"},
            "validation": {"is_valid": False, "errors": ["invalid_confidence:result"]},
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


@pytest.mark.asyncio
async def test_validate_schema_normalizes_nonstandard_entity_labels():
    service = StructuringService()
    payload = {
        "case_id": "CASE-ENTITY-001",
        "source": "aihub_71852",
        "created_at": "2026-03-22T10:00:00+09:00",
        "admin_unit": "서울특별시",
        "priority": "보통",
        "raw_text": "소음과 위험이 있습니다.",
        "observation": {"text": "소음 민원", "confidence": 0.9, "evidence_span": [0, 4]},
        "result": {"text": "생활 불편", "confidence": 0.9, "evidence_span": [5, 9]},
        "request": {"text": "점검 요청", "confidence": 0.9, "evidence_span": [10, 14]},
        "context": {"text": "서울시", "confidence": 0.9, "evidence_span": [15, 18]},
        "entities": [
            {"label": "TYPE", "text": "소음"},
            {"label": "DATE", "text": "2026-03-22"},
        ],
    }

    validation = await service.validate_schema(payload)
    print("Validation result:", validation)
    assert validation["is_valid"] is True
    assert "invalid_entity_label:TYPE" not in validation["errors"]
    assert payload["entities"][0]["label"] == "HAZARD"
    assert payload["entities"][1]["label"] == "TIME"


@pytest.mark.asyncio
async def test_validate_schema_blocks_unknown_entity_labels():
    service = StructuringService()
    payload = {
        "case_id": "CASE-ENTITY-002",
        "source": "aihub_71852",
        "created_at": "2026-03-22T10:00:00+09:00",
        "admin_unit": "서울특별시",
        "priority": "보통",
        "raw_text": "내용",
        "observation": {"text": "관찰", "confidence": 0.9, "evidence_span": [0, 2]},
        "result": {"text": "결과", "confidence": 0.9, "evidence_span": [3, 5]},
        "request": {"text": "요청", "confidence": 0.9, "evidence_span": [6, 8]},
        "context": {"text": "맥락", "confidence": 0.9, "evidence_span": [9, 11]},
        "entities": [{"label": "FOO", "text": "임의"}],
    }

    validation = await service.validate_schema(payload)

    assert validation["is_valid"] is False
    assert "invalid_entity_label:FOO" in validation["errors"]


@pytest.mark.asyncio
async def test_structure_reads_raw_text_when_text_missing():
    service = StructuringService()
    result = await service.structure(
        {
            "case_id": "CASE-RAW-001",
            "source": "aihub_71852",
            "created_at": "2026-03-22",
            "raw_text": "서울시 가로등 소음 개선 요청",
        }
    )

    assert result["raw_text"] == "서울시 가로등 소음 개선 요청"
    assert isinstance(result.get("entities"), list)
    assert any(entity.get("label") == "FACILITY" for entity in result["entities"])


@pytest.mark.asyncio
async def test_structure_masks_pii_before_structuring(monkeypatch):
    service = StructuringService()
    monkeypatch.setattr(settings, "STRUCTURING_CONSTRAINED", False)

    async def fake_extract(text: str):
        assert "010-1234-5678" not in text
        assert "test.user@example.com" not in text
        return FourElementsLLMOutput(), 0

    monkeypatch.setattr(service._llm_extractor, "extract", fake_extract)

    result = await service.structure(
        {
            "case_id": "CASE-PII-001",
            "source": "test",
            "created_at": "2026-06-17",
            "raw_text": "연락처 010-1234-5678, 이메일 test.user@example.com 입니다.",
        }
    )

    assert "[전화번호]" in result["raw_text"]
    assert "[이메일]" in result["raw_text"]
    assert "010-1234-5678" not in result["raw_text"]
    assert "test.user@example.com" not in result["raw_text"]


@pytest.mark.asyncio
async def test_structure_parses_raw_consulting_content_without_answer_or_supervision():
    service = StructuringService()
    result = await service.structure(
        {
            "source_id": "RAW-001",
            "source": "서울시",
            "consulting_date": "20240102",
            "consulting_category": "도로",
            "consulting_content": "제목 : 보안등 고장\n\nQ : 골목 보안등이 꺼졌습니다.\n\nA : 접수했습니다.",
            "instructions": [
                {
                    "tuning_type": "질의응답",
                    "data": [{"instruction": "라벨 질문", "output": "라벨 답변"}],
                }
            ],
        }
    )

    assert result["raw_text"] == "보안등 고장\n골목 보안등이 꺼졌습니다."
    assert "supervision" not in result


@pytest.mark.asyncio
async def test_validate_schema_accepts_constrained_structured_by():
    service = StructuringService()
    payload = {
        "case_id": "CASE-CONSTRAINED-001",
        "source": "aihub",
        "created_at": "2026-03-22T10:00:00+09:00",
        "admin_unit": "서울특별시",
        "priority": "보통",
        "raw_text": "가로등이 고장났습니다. 교체해 주세요.",
        "observation": {"text": "가로등이 고장났습니다", "confidence": 0.9, "evidence_span": [0, 11]},
        "result": {"text": "", "confidence": 0.0, "evidence_span": [0, 0], "status": "pending"},
        "request": {"text": "교체해 주세요", "confidence": 0.9, "evidence_span": [13, 20]},
        "context": {"text": "", "confidence": 0.0, "evidence_span": [0, 0]},
        "entities": [{"label": "FACILITY", "text": "가로등"}],
        "structured_by": "constrained",
        "extraction_meta": {"llm_latency_ms": 1, "llm_non_null_count": 2},
    }

    validation = await service.validate_schema(payload)

    assert "invalid_structured_by_value" not in validation["errors"]


@pytest.mark.asyncio
async def test_extract_entities_filters_admin_unit_false_positives():
    service = StructuringService()
    text = (
        "안타깝게도 단체이셔도 예매도 어렵습니다. "
        "서울특별시 강남구는 10시부터 접수합니다. "
        "현장도 10시부터입니다."
    )

    entities = await service.extract_entities(text)

    admin_units = [e["text"] for e in entities if e["label"] == "ADMIN_UNIT"]
    times = [e["text"] for e in entities if e["label"] == "TIME"]

    assert "안타깝게도" not in admin_units
    assert "예매도" not in admin_units
    assert "서울특별시" in admin_units
    assert "10시" in times
