import sys
from pathlib import Path

import pytest

# Allow direct execution: python app/tests/unit/test_pii_masking.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.service import IngestionService


@pytest.mark.asyncio
async def test_mask_pii_phone_email_ssn():
    service = IngestionService()
    text = "연락처는 010-1234-5678, 이메일 test.user@example.com, 주민번호 900101-1234567입니다."
    masked = await service.mask_pii(text)

    assert "[REDACTED:PHONE]" in masked
    assert "[REDACTED:EMAIL]" in masked
    assert "[REDACTED:SSN]" in masked
    assert "010-1234-5678" not in masked
    assert "test.user@example.com" not in masked
    assert "900101-1234567" not in masked


@pytest.mark.asyncio
async def test_mask_pii_no_pii_keeps_text():
    service = IngestionService()
    text = "이것은 민원 내용입니다."
    masked = await service.mask_pii(text)
    assert masked == text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
