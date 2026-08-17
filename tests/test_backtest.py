"""Tests for the backtesting engine."""

from jarvis.engine.backtest import Backtester, Signal, split_train_val_test, walk_forward
from jarvis.engine.strategies import ema_cross_strategy


def _make_candles(n=300, start=1.0):
    import random
    from datetime import datetime, timezone

    from jarvis.core.models import MarketCandle
    rng = random.Random(42)
    px = start
    out = []
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        # gentle uptrend with noise
        px = max(0.0001, px + rng.gauss(0.0005, 0.002))
        o = px
        h = px + abs(rng.gauss(0, 0.001))
        low = px - abs(rng.gauss(0, 0.001))
        c = px
        t = base.timestamp() + i * 3600
        out.append(MarketCandle(symbol="EURUSD", timeframe="H1",
                                time=datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                                open=o, high=h, low=low, close=c, volume=100))
    return out


def test_backtest_runs_and_reports_metrics():
    candles = _make_candles(300)
    bt = Backtester(initial_capital=100_000)
    result = bt.run(candles, ema_cross_strategy())
    assert result.n_trades >= 0
    assert result.final_capital is not None
    assert -1.0 <= result.max_drawdown <= 1.0
    assert 0.0 <= result.win_rate <= 1.0


def test_split_train_val_test():
    candles = _make_candles(100)
    tr, va, te = split_train_val_test(candles, 0.6, 0.2)
    assert len(tr) + len(va) + len(te) == 100
    assert len(te) > 0  # out-of-sample exists


def test_walk_forward():
    candles = _make_candles(700)
    results = walk_forward(candles, lambda: ema_cross_strategy(), train_window=300, test_window=100)
    assert len(results) >= 1


def test_no_lookahead_strategy_only_sees_prefix():
    """Strategy function must only receive candles[:i+1]."""
    seen = []

    def strat(candles, i):
        seen.append(len(candles))
        assert len(candles) == i + 1, "look-ahead bias: strategy saw future bars"
        return Signal(action="HOLD")

    candles = _make_candles(50)
    Backtester().run(candles, strat)
    assert len(seen) > 0
