"""Section 8: "Explicitly never log: raw passwords, password hashes, full
JWTs, or verification/reset tokens." This is the one place that guarantee
is actually enforced, so it's worth a direct test rather than trusting
every call site to remember."""

import logging

import pytest

from app.core.logging import RedactingJsonFormatter

pytestmark = pytest.mark.unit


def test_sensitive_fields_are_redacted_in_log_output():
    formatter = RedactingJsonFormatter("%(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="user_logged_in",
        args=(),
        exc_info=None,
    )
    record.password = "hunter2"
    record.token = "abc.def.ghi"
    record.refresh_token = "some-refresh-token"
    record.user_id = "keep-me"

    output = formatter.format(record)

    assert "hunter2" not in output
    assert "abc.def.ghi" not in output
    assert "some-refresh-token" not in output
    assert "keep-me" in output
    assert "[REDACTED]" in output
