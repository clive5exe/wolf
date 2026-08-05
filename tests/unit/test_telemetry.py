"""Redaction filter: credential shapes never reach log output (THREAT_MODEL T3)."""

from __future__ import annotations

from tradeos.telemetry.logging import redact


def test_api_key_assignments_redacted() -> None:
    assert "[REDACTED]" in redact('api_key = "abcdefghij123456789"')
    assert "abcdefghij123456789" not in redact('token: "abcdefghij123456789"')


def test_key_shapes_redacted() -> None:
    # fixture strings below are fake, shaped only to exercise the redactor
    assert "AKIA" not in redact("creds AKIAABCDEFGHIJKLMNOP end")  # safety-scan-allow
    assert "rh-api" not in redact("using rh-api-abc123def456 now")  # safety-scan-allow
    assert "PRIVATE KEY" not in redact(  # safety-scan-allow
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"  # safety-scan-allow
    )


def test_account_numbers_redacted() -> None:
    out = redact("account: 12345678901")
    assert "12345678901" not in out


def test_ordinary_text_untouched() -> None:
    text = "BUY 5 AAPL @ $200.10 (paper) [cycle 01ABCDEF]"
    assert redact(text) == text
