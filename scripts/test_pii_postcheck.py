from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pii.postcheck import postcheck_text, redact_address_and_vehicle


def test_postcheck_detects_residual_core_pii():
    result = postcheck_text("010-1234-5678 test.user@example.com 900101-1234567")

    assert result.passed is False
    assert {finding.label for finding in result.findings} >= {
        "전화번호",
        "이메일",
        "주민등록번호",
    }


def test_supplemental_redaction_removes_detail_address():
    masked = redact_address_and_vehicle("주소는 서울특별시 중구 세종대로 110 101동 202호입니다")

    assert "[상세주소]" in masked
    assert "세종대로 110" not in masked
    assert "101동 202호" not in masked
    assert postcheck_text(masked).passed is True


def test_supplemental_redaction_removes_vehicle_number():
    masked = redact_address_and_vehicle("민원 차량번호는 12가3456입니다")

    assert "[차량번호]" in masked
    assert "12가3456" not in masked
    assert postcheck_text(masked).passed is True


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__]))
