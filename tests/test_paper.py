"""Tests for the paper trading engine."""

from jarvis.core.enums import OrderSide
from jarvis.engine.paper import PaperTradingEngine


def test_paper_open_and_close(demo_broker):
    eng = PaperTradingEngine(demo_broker, initial_capital=500_000)
    pt = eng.open_position("EURUSD", OrderSide.BUY, 0.1, stop_loss=1.07, take_profit=1.09)
    assert pt.position_id.startswith("paper-")
    assert len(eng.positions) == 1
    closed = eng.close_position(pt.position_id)
    assert closed is not None
    assert closed.status == "CLOSED"
    assert closed.pnl is not None


def test_paper_stats(demo_broker):
    eng = PaperTradingEngine(demo_broker, initial_capital=100_000)
    pt = eng.open_position("EURUSD", OrderSide.BUY, 0.1)
    eng.close_position(pt.position_id)
    s = eng.stats()
    assert s["closed_trades"] == 1
    assert s["balance"] != 100_000  # PnL realized


def test_paper_no_real_money(demo_broker):
    """Paper engine must never touch the real broker's balance."""
    eng = PaperTradingEngine(demo_broker, initial_capital=50_000)
    before = demo_broker.get_balance()
    pt = eng.open_position("EURUSD", OrderSide.SELL, 0.5)
    eng.close_position(pt.position_id)
    after = demo_broker.get_balance()
    assert before == after  # broker balance unchanged
