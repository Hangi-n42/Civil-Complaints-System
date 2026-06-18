from __future__ import annotations

import pytest

from app.ingestion.service import IngestionService


def test_normalize_aihub_record_separates_structuring_text_and_search_text():
    service = IngestionService()
    record = {
        "source": "부산광역시",
        "source_id": "1001",
        "consulting_date": "20260617",
        "consulting_category": "도로",
        "consulting_content": "제목 : 도로 파손\n\nQ : 도로에 포트홀이 있습니다.\n\nA : 담당 부서에 전달했습니다.",
    }

    normalized = service.normalize_aihub_record(record)

    assert normalized["text"] == "도로 파손\n도로에 포트홀이 있습니다."
    assert normalized["raw_text"] == normalized["text"]
    assert normalized["search_text"] == "도로 파손\n도로에 포트홀이 있습니다.\n담당 부서에 전달했습니다."


@pytest.mark.asyncio
async def test_process_masks_search_text_with_structuring_text():
    service = IngestionService()
    processed = await service.process(
        [
            {
                "case_id": "CASE-PII-SEARCH",
                "text": "연락처는 010-1111-2222 입니다.",
                "search_text": "연락처는 010-1111-2222 입니다.\n담당자 이메일 test@example.com",
            }
        ]
    )

    row = processed[0]
    assert "010-1111-2222" not in row["text"]
    assert "010-1111-2222" not in row["search_text"]
    assert "test@example.com" not in row["search_text"]
    assert "[전화번호]" in row["search_text"]
    assert "[이메일]" in row["search_text"]
