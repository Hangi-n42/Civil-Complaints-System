from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pii.ko_pii_adapter import KoPiiAdapter


class BrokenEngine:
    def process(self, text: str):
        raise RuntimeError("engine failed")


def test_ko_pii_adapter_redacts_core_identifiers():
    adapter = KoPiiAdapter()
    result = adapter.redact(
        "연락처 010-1234-5678, 이메일 test.user@example.com, 주민번호 900101-1234567"
    )

    assert result.ok is True
    assert result.text is not None
    assert "[전화번호]" in result.text
    assert "[이메일]" in result.text
    assert "[주민등록번호]" in result.text
    assert "010-1234-5678" not in result.text
    assert "test.user@example.com" not in result.text
    assert "900101-1234567" not in result.text
    assert {"PHONE", "EMAIL", "RRN"}.issubset(set(result.labels))


@pytest.mark.parametrize(
    ("mode", "strategy"),
    [
        ("PERMISSIVE", "redact"),
        ("AUDIT", "redact"),
        ("PARANOID", "partial"),
        ("PARANOID", "fpe"),
        ("PARANOID", "tokenize"),
    ],
)
def test_ko_pii_adapter_rejects_unsafe_rag_settings(mode: str, strategy: str):
    with pytest.raises(ValueError):
        KoPiiAdapter(mode=mode, strategy=strategy)


def test_ko_pii_adapter_fail_closed_on_engine_error():
    adapter = KoPiiAdapter(engine=BrokenEngine())
    result = adapter.redact("연락처 010-1234-5678")

    assert result.ok is False
    assert result.text is None
    assert result.error_code == "KO_PII_ERROR"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
