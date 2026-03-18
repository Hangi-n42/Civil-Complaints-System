import pytest

from app.ingestion.service import IngestionService


@pytest.mark.asyncio
async def test_mask_pii_phone_email_ssn():
    service = IngestionService()
    text = "연락처는 010-1234-5678, 이메일 test.user@example.com, 주민번호 900101-1234567입니다."
    masked = await service.mask_pii(text)

    assert "[PHONE]" in masked
    assert "[EMAIL]" in masked
    assert "[SSN]" in masked
    assert "010-1234-5678" not in masked
    assert "test.user@example.com" not in masked
    assert "900101-1234567" not in masked


@pytest.mark.asyncio
async def test_mask_pii_no_pii_keeps_text():
    service = IngestionService()
    text = "이것은 민원 내용입니다."
    masked = await service.mask_pii(text)
    assert masked == text
