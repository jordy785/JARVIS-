"""Broker factory.

Builds the appropriate broker based on settings. Falls back to the demo broker
when:
- the MetaTrader5 package is not importable, or
- MT5 connection fails, or
- the system is not in LIVE mode.

The demo broker is ALWAYS used for PAPER and ANALYSIS modes so that no real
money is ever at risk outside LIVE mode.
"""

from __future__ import annotations

from jarvis.brokers.base import TradingBroker
from jarvis.brokers.demo import DemoBroker
from jarvis.core.config import Settings, get_settings
from jarvis.core.enums import Mode
from jarvis.core.logging import get_logger

_log = get_logger("brokers.factory")


def build_broker(settings: Settings | None = None) -> TradingBroker:
    s = settings or get_settings()

    if s.mode is Mode.LIVE and s.is_live_allowed():
        from jarvis.brokers.mt5 import MetaTrader5Broker

        broker = MetaTrader5Broker(
            login=s.mt5_login,
            password=s.mt5_password,
            server=s.mt5_server,
            path=s.mt5_path,
        )
        if broker.connect():
            _log.info("Live MT5 broker connected")
            return broker
        _log.warning("Live MT5 connection failed — falling back to DEMO broker")

    # PAPER, ANALYSIS, or LIVE-not-enabled → demo broker
    broker = DemoBroker(initial_balance=s.paper_initial_capital, currency=s.paper_base_currency)
    broker.connect()
    _log.info("Using DEMO broker (mode=%s, live_enabled=%s)", s.mode, s.live_trading_enabled)
    return broker
