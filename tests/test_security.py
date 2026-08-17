"""Tests for security: secrets never logged, LIVE disabled by default, masking."""

import io
import logging

from jarvis.core.config import get_settings
from jarvis.core.logging import get_logger


def test_live_disabled_by_default(monkeypatch):
    from jarvis.core.config import reset_settings_cache
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    monkeypatch.delenv("TRADING_MODE", raising=False)
    reset_settings_cache()
    s = get_settings()
    assert s.live_trading_enabled is False
    assert s.is_live_allowed() is False


def test_password_never_logged(monkeypatch):
    """Logging a sensitive kwarg must be redacted."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FILE", "")
    # reset the configured flag so it reconfigures with a new stream
    import jarvis.core.logging as L
    L._configured = False
    stream = io.StringIO()
    root = logging.getLogger("jarvis")
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(stream)
    h.setFormatter(logging.Formatter("%(message)s"))
    h.addFilter(L.RedactingFilter())
    root.addHandler(h)
    root.setLevel(logging.DEBUG)
    root.propagate = False
    L._configured = True
    log = get_logger("sec.test")
    log.info("connecting with password=supersecret and api_key=abc123")
    out = stream.getvalue()
    assert "supersecret" not in out
    assert "abc123" not in out
    assert "REDACTED" in out


def test_masked_summary_does_not_expose_secrets(monkeypatch):
    from jarvis.core.config import reset_settings_cache
    monkeypatch.setenv("MT5_PASSWORD", "topsecret")
    monkeypatch.setenv("MACRO_NEWS_API_KEY", "key123")
    reset_settings_cache()
    s = get_settings()
    summary = s.masked_summary()
    assert "topsecret" not in str(summary)
    assert "key123" not in str(summary)
    assert summary["mt5_password"] == "***"
    assert summary["macro_news_api_key"] == "***"
