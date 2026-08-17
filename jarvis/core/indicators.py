"""Pure-Python technical indicators used by the technical/quant agents.

Implemented without external TA libraries to keep dependencies minimal.
All functions accept a sequence (list/tuple/Series-like) of floats and return
floats or lists. NaN-safe where reasonable.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    ema_val = sum(values[:period]) / period  # seed with SMA
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """Return (macd_line, signal_line, histogram)."""
    if len(values) < slow + signal:
        return None, None, None
    ema_fast = _ema_series(values, fast)
    ema_slow = _ema_series(values, slow)
    macd_line = [f - s for f, s in zip(ema_fast[slow - 1 :], ema_slow[slow - 1 :], strict=False)]
    if len(macd_line) < signal:
        return macd_line[-1] if macd_line else None, None, None
    sig = _ema_series(macd_line, signal)
    hist = macd_line[-1] - sig[-1]
    return macd_line[-1], sig[-1], hist


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1.0)
    out: list[float] = []
    ema_val = sum(values[:period]) / period
    out.append(ema_val)
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
        out.append(ema_val)
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float | None:
    if not (len(highs) == len(lows) == len(closes)) or len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    # Wilder's smoothing
    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


def volatility(values: Sequence[float], period: int = 20) -> float | None:
    if len(values) < 2 or period < 2:
        return None
    window = values[-period:]
    if len(window) < 2:
        return None
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
    return math.sqrt(var)


def stdev(values: Sequence[float], period: int) -> float | None:
    return volatility(values, period)


def support_resistance(
    highs: Sequence[float], lows: Sequence[float], lookback: int = 20
) -> tuple[float | None, float | None]:
    if not highs or not lows:
        return None, None
    h = highs[-lookback:] if len(highs) >= lookback else list(highs)
    low_window = lows[-lookback:] if len(lows) >= lookback else list(lows)
    return min(low_window), max(h)
