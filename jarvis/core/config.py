"""Application settings loaded from environment / .env.

Secrets (MT5 credentials, API keys) are read from environment variables only.
They are NEVER hardcoded, NEVER logged, and NEVER exposed to agents.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv optional but recommended
    load_dotenv = None  # type: ignore[assignment]


def _load_env_file() -> None:
    if load_dotenv is not None:
        # Load .env if present; never raises if missing.
        load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings.

    Note on security: ``mt5_password`` and ``macro_news_api_key`` are kept here
    but should never be printed or logged. Brokers receive them by reference
    only, at connection time.
    """

    # MT5 credentials
    mt5_login: int
    mt5_password: str
    mt5_server: str
    mt5_path: str

    # Macro / news
    macro_news_api_key: str
    macro_news_provider: str

    # Trading safety
    live_trading_enabled: bool
    trading_mode: str  # Mode value
    trading_killswitch: bool
    fast_confirmation: bool

    # Paper trading
    paper_initial_capital: float
    paper_base_currency: str

    # Risk defaults
    risk_max_risk_per_trade_pct: float
    risk_max_daily_loss_pct: float
    risk_max_open_positions: int
    risk_max_exposure_pct: float

    # Logging / storage
    log_level: str
    log_file: str
    memory_db: str

    # Internal: project root for resolving relative paths
    project_root: Path = field(default_factory=Path.cwd)

    def resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.project_root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def is_live_allowed(self) -> bool:
        """Live order submission requires BOTH the global flag and LIVE mode."""
        return self.live_trading_enabled and self.trading_mode == Mode.LIVE

    @property
    def mode(self) -> Mode:
        from jarvis.core.enums import Mode

        return Mode(self.trading_mode)

    def masked_summary(self) -> dict[str, str]:
        """Return a secrets-safe summary suitable for logging/dashboard."""
        return {
            "mt5_login": str(self.mt5_login),
            "mt5_server": self.mt5_server,
            "mt5_password": "***" if self.mt5_password else "(unset)",
            "macro_news_api_key": "***" if self.macro_news_api_key else "(unset)",
            "trading_mode": self.trading_mode,
            "live_trading_enabled": str(self.live_trading_enabled),
            "trading_killswitch": str(self.trading_killswitch),
        }


# Avoid importing Mode at module top to prevent a circular import on some paths.
from jarvis.core.enums import Mode  # noqa: E402  (kept after dataclass defs)


def _bool(value: str, default: bool = False) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"} if value else default


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file()
    return Settings(
        mt5_login=_int(os.getenv("MT5_LOGIN", "0"), 0),
        mt5_password=os.getenv("MT5_PASSWORD", ""),
        mt5_server=os.getenv("MT5_SERVER", "Demo"),
        mt5_path=os.getenv("MT5_PATH", ""),
        macro_news_api_key=os.getenv("MACRO_NEWS_API_KEY", ""),
        macro_news_provider=os.getenv("MACRO_NEWS_PROVIDER", ""),
        live_trading_enabled=_bool(os.getenv("LIVE_TRADING_ENABLED", "false"), False),
        trading_mode=os.getenv("TRADING_MODE", Mode.ANALYSIS.value),
        trading_killswitch=_bool(os.getenv("TRADING_KILLSWITCH", "false"), False),
        fast_confirmation=_bool(os.getenv("FAST_CONFIRMATION", "false"), False),
        paper_initial_capital=_float(os.getenv("PAPER_INITIAL_CAPITAL", "500000"), 500000.0),
        paper_base_currency=os.getenv("PAPER_BASE_CURRENCY", "XOF"),
        risk_max_risk_per_trade_pct=_float(
            os.getenv("RISK_MAX_RISK_PER_TRADE_PCT", "1.0"), 1.0
        ),
        risk_max_daily_loss_pct=_float(os.getenv("RISK_MAX_DAILY_LOSS_PCT", "3.0"), 3.0),
        risk_max_open_positions=_int(os.getenv("RISK_MAX_OPEN_POSITIONS", "5"), 5),
        risk_max_exposure_pct=_float(os.getenv("RISK_MAX_EXPOSURE_PCT", "20.0"), 20.0),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", "logs/jarvis.log"),
        memory_db=os.getenv("MEMORY_DB", "jarvis/data/memory.db"),
    )


def reset_settings_cache() -> None:
    """Test helper: reset the cached settings (after monkeypatching env)."""
    get_settings.cache_clear()
