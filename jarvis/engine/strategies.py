"""Reference strategies used by the Research / Learning agents and tests."""

from __future__ import annotations

from jarvis.core.indicators import ema, rsi
from jarvis.core.models import MarketCandle
from jarvis.engine.backtest import Signal, Strategy


def ema_cross_strategy(fast: int = 20, slow: int = 50) -> Strategy:
    """Long when EMA(fast) crosses above EMA(slow), short on bearish cross."""

    def strat(candles: list[MarketCandle], i: int) -> Signal:
        if i < slow + 1:
            return Signal(action="HOLD")
        closes = [c.close for c in candles[: i + 1]]
        ef = ema(closes, fast)
        es = ema(closes, slow)
        prev_closes = [c.close for c in candles[:i]]
        ef_prev = ema(prev_closes, fast) if len(prev_closes) > slow else None
        es_prev = ema(prev_closes, slow) if len(prev_closes) > slow else None
        if ef is None or es is None or ef_prev is None or es_prev is None:
            return Signal(action="HOLD")
        if ef_prev <= es_prev and ef > es:
            atr_proxy = abs(closes[i] - closes[i - 1]) * 10 or 0.001
            return Signal(action="BUY", stop_loss=closes[i] - atr_proxy,
                          take_profit=closes[i] + atr_proxy * 2)
        if ef_prev >= es_prev and ef < es:
            atr_proxy = abs(closes[i] - closes[i - 1]) * 10 or 0.001
            return Signal(action="SELL", stop_loss=closes[i] + atr_proxy,
                          take_profit=closes[i] - atr_proxy * 2)
        return Signal(action="HOLD")

    return strat


def rsi_mean_reversion_strategy(period: int = 14, oversold: float = 30, overbought: float = 70) -> Strategy:
    """Buy RSI<oversold, exit when RSI reverts to 50; short RSI>overbought."""

    def strat(candles: list[MarketCandle], i: int) -> Signal:
        if i < period + 1:
            return Signal(action="HOLD")
        closes = [c.close for c in candles[: i + 1]]
        r = rsi(closes, period)
        if r is None:
            return Signal(action="HOLD")
        price = closes[-1]
        atr_proxy = abs(price - closes[-2]) * 10 if len(closes) >= 2 else 0.001
        atr_proxy = atr_proxy or 0.001
        if r < oversold:
            return Signal(action="BUY", stop_loss=price - atr_proxy, take_profit=price + atr_proxy * 2)
        if r > overbought:
            return Signal(action="SELL", stop_loss=price + atr_proxy, take_profit=price - atr_proxy * 2)
        if 45 <= r <= 55:
            return Signal(action="EXIT")
        return Signal(action="HOLD")

    return strat
