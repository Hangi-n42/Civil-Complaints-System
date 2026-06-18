from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.service import IngestionService
from app.retrieval.service import RetrievalService
from src.pii.ko_pii_adapter import KoPiiAdapterResult
from src.pii.postcheck import postcheck_text
from src.structuring.pii.pipeline import PiiSanitizationPipeline
from src.structuring.pii.risk_policy import PiiStatus


class PassthroughAdapter:
    def redact(self, text: str | None) -> KoPiiAdapterResult:
        return KoPiiAdapterResult(ok=True, text="" if text is None else str(text))


class FailingAdapter:
    def redact(self, text: str | None) -> KoPiiAdapterResult:
        return KoPiiAdapterResult(ok=False, text=None, error_code="KO_PII_ERROR")


class FakeStore:
    def __init__(self) -> None:
        self.records = []

    def reset_collection(self, collection_name: str) -> None:
        return None

    def upsert_records(self, collection_name: str, records):
        self.records = list(records)
        return {
            "indexed_count": len(self.records),
            "chunk_count": len(self.records),
            "records": [],
        }


def test_pipeline_masks_core_identifiers():
    pipeline = PiiSanitizationPipeline()
    decision = pipeline.sanitize_for_rag(
        "연락처 010-1234-5678, 이메일 test.user@example.com, 주민번호 900101-1234567"
    )

    assert decision.status == PiiStatus.PASSED
    assert decision.sanitized_text is not None
    assert "[전화번호]" in decision.sanitized_text
    assert "[이메일]" in decision.sanitized_text
    assert "[주민등록번호]" in decision.sanitized_text
    assert postcheck_text(decision.sanitized_text).passed is True


def test_pipeline_removes_detail_address_and_vehicle():
    pipeline = PiiSanitizationPipeline()
    decision = pipeline.sanitize_for_rag(
        "서울특별시 중구 세종대로 110 101동 202호에 12가3456 차량이 방치되어 있습니다"
    )

    assert decision.status == PiiStatus.PASSED
    assert decision.sanitized_text is not None
    assert "세종대로 110" not in decision.sanitized_text
    assert "101동 202호" not in decision.sanitized_text
    assert "12가3456" not in decision.sanitized_text
    assert "[상세주소]" in decision.sanitized_text
    assert "[차량번호]" in decision.sanitized_text


def test_name_school_grade_class_combination_goes_to_review():
    pipeline = PiiSanitizationPipeline()
    decision = pipeline.sanitize_for_rag("홍길동 서울초등학교 3학년 2반 통학로 민원")

    assert decision.status == PiiStatus.REVIEW
    assert decision.needs_review is True
    assert decision.sanitized_text is None


def test_postcheck_residual_core_pii_is_quarantined():
    pipeline = PiiSanitizationPipeline(adapter=PassthroughAdapter())
    decision = pipeline.sanitize_for_rag("연락처 010-1234-5678")

    assert decision.status == PiiStatus.QUARANTINED
    assert decision.needs_review is True
    assert decision.sanitized_text is None
    assert "POSTCHECK_HIGH_RISK_REMAINS" in decision.reasons


def test_ko_pii_error_is_quarantined_without_original_text():
    pipeline = PiiSanitizationPipeline(adapter=FailingAdapter())
    decision = pipeline.sanitize_for_rag("연락처 010-1234-5678")

    assert decision.status == PiiStatus.QUARANTINED
    assert decision.needs_review is True
    assert decision.sanitized_text is None
    assert "KO_PII_ERROR" in decision.reasons


def test_logs_do_not_contain_original_pii(caplog):
    logger = logging.getLogger("pii-fail-closed-test")
    pipeline = PiiSanitizationPipeline(logger=logger)

    with caplog.at_level(logging.DEBUG, logger="pii-fail-closed-test"):
        pipeline.sanitize_for_rag("연락처 010-1234-5678, test.user@example.com")

    assert "010-1234-5678" not in caplog.text
    assert "test.user@example.com" not in caplog.text


@pytest.mark.asyncio
async def test_ingestion_process_quarantines_review_documents():
    service = IngestionService()
    processed = await service.process(
        [
            {
                "case_id": "CASE-PII-REVIEW",
                "text": "학생 홍길동 서울초등학교 3학년 2반 통학로 민원",
                "search_text": "학생 홍길동 서울초등학교 3학년 2반 통학로 민원",
            }
        ]
    )

    row = processed[0]
    assert row["needs_review"] is True
    assert row["pii_status"] == "REVIEW"
    assert row["text"] == ""
    assert row["raw_text"] == ""
    assert row["search_text"] == ""


def test_retrieval_index_skips_quarantined_documents():
    service = RetrievalService()
    store = FakeStore()
    service._vectorstore = store

    result = service._index_documents_internal(
        [
            {
                "case_id": "SAFE-1",
                "source": "test",
                "created_at": "2026-06-18T00:00:00+09:00",
                "text": "도로 보수 요청",
                "structured_text": {"request": "도로 보수 요청"},
            },
            {
                "case_id": "UNSAFE-1",
                "source": "test",
                "created_at": "2026-06-18T00:00:00+09:00",
                "text": "",
                "needs_review": True,
                "pii_status": "QUARANTINED",
            },
        ],
        collection_name="test_collection",
    )

    assert result["indexed_count"] == 1
    assert result["skipped_pii_count"] == 1
    assert len(store.records) == 1
    assert store.records[0]["case_id"] == "CASE-SAFE-1"


def test_ko_pii_before_after_sample_coverage_100_plus():
    pipeline = PiiSanitizationPipeline()
    samples = []
    for idx in range(30):
        samples.extend(
            [
                f"연락처는 010-12{idx:02d}-56{idx:02d}입니다",
                f"이메일은 user{idx}@example.com 입니다",
                f"주민번호 후보 900101-12345{idx % 10}{idx % 10}입니다",
                f"주소 서울특별시 중구 세종대로 {100 + idx} {idx + 1}동 {idx + 2}호",
            ]
        )

    assert len(samples) >= 100
    for sample in samples:
        decision = pipeline.sanitize_for_rag(sample)
        assert decision.status in {PiiStatus.PASSED, PiiStatus.REVIEW, PiiStatus.QUARANTINED}
        if decision.status == PiiStatus.PASSED:
            assert decision.sanitized_text is not None
            assert postcheck_text(decision.sanitized_text).passed is True
        else:
            assert decision.needs_review is True
            assert decision.sanitized_text is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
