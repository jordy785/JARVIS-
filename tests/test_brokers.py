"""Tests for the broker abstraction (demo + factory)."""

from jarvis.brokers import build_broker
from jarvis.brokers.demo import DemoBroker as DB


def test_demo_broker_connect_and_quote():
    b = DB(initial_balance=100_000)
    assert b.connect() is True
    q = b.get_market_price("EURUSD")
    assert q is not None
    assert q.ask >= q.bid
    assert q.spread > 0


def test_demo_candles():
    b = DB()
    b.connect()
    candles = b.get_candles("EURUSD", "H1", 100)
    assert len(candles) == 100
    for c in candles:
        assert c.high >= max(c.open, c.close)
        assert c.low <= min(c.open, c.close)


def test_demo_place_and_close_position():
    from jarvis.core.enums import OrderSide
    b = DB(initial_balance=100_000)
    b.connect()
    res = b.place_order("EURUSD", OrderSide.BUY, 0.1)
    assert res.success
    assert res.ticket is not None
    assert len(b.get_positions()) == 1
    close = b.close_position(res.ticket)
    assert close.success


def test_factory_returns_demo_in_paper(monkeypatch):
    from jarvis.core.config import reset_settings_cache
    monkeypatch.setenv("TRADING_MODE", "PAPER")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    reset_settings_cache()
    b = build_broker()
    assert b.name == "demo"


def test_factory_never_returns_mt5_without_credentials(monkeypatch):
    """Even if LIVE is requested, no MT5 creds/connection -> demo fallback."""
    from jarvis.core.config import reset_settings_cache
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    monkeypatch.setenv("MT5_LOGIN", "0")
    monkeypatch.setenv("MT5_PASSWORD", "")
    reset_settings_cache()
    b = build_broker()
    # MT5 cannot connect in this env -> falls back to demo
    assert b.name == "demo"
