"""Structured logging for JARVIS.

Secrets are never logged. A small redacting formatter is applied so that any
field whose name looks like a credential is masked before emission.
"""

from __future__ import annotations

import logging
import sys

_SENSITIVE = {"password", "passwd", "api_key", "apikey", "secret", "token", "mt5_password"}


class RedactingFilter(logging.Filter):
    """Mask any sensitive-looking arguments passed to logging calls."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attr in list(record.__dict__):
            if attr.lower() in _SENSITIVE:
                setattr(record, attr, "***REDACTED***")
        # Also redact message content if it literally contains a known marker.
        msg = record.getMessage()
        for marker in ("mt5_password=", "api_key=", "password="):
            if marker in msg:
                msg = msg.split(marker)[0] + marker + "***REDACTED***"
        record.msg = msg
        record.args = ()
        return True


_configured = False


def _configure_once(level: str, log_file: str | None) -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger("jarvis")
    root.setLevel(level)
    root.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    stream.addFilter(RedactingFilter())
    root.addHandler(stream)

    if log_file:
        from pathlib import Path

        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(p, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(RedactingFilter())
        root.addHandler(fh)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger under the ``jarvis`` namespace."""
    from jarvis.core.config import get_settings

    settings = get_settings()
    _configure_once(settings.log_level, settings.log_file)
    if not name.startswith("jarvis"):
        name = f"jarvis.{name}"
    return logging.getLogger(name)
