from __future__ import annotations

from app.api.error_utils import get_retryable, get_status_code


def test_error_policy_parse_retry_exhausted_non_retryable():
    assert get_status_code("PARSE_RETRY_EXHAUSTED") == 500
    assert get_retryable("PARSE_RETRY_EXHAUSTED") is False


def test_error_policy_index_not_ready_retryable():
    assert get_status_code("INDEX_NOT_READY") == 503
    assert get_retryable("INDEX_NOT_READY") is True
