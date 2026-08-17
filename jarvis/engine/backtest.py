"""Backtesting engine.

Runs a strategy against historical candles (train / validation / test /
walk-forward / out-of-sample) and reports standard performance metrics:
win rate, profit factor, expectancy, max drawdown, Sharpe, avg win/loss,
consecutive wins/losses, return, volatility, #trades.

Avoids look-ahead bias by processing bars strictly sequentially and only
using information available up to bar i when deciding on bar i.

A "strategy" is any callable: (candles_up_to_index, context) -> Signal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis.core.logging import get_logger
from jarvis.core.models import MarketCandle

_log = get_logger("engine.backtest")


@dataclass
class BacktestTrade:
    side: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    pnl: float
    pnl_pct: float
    bars_held: int


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    initial_capital: float = 0.0
    final_capital: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    total_return_pct: float = 0.0
    volatility: float = 0.0
    n_trades: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "max_drawdown": self.max_drawdown,
            "sharpe": self.sharpe,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "consecutive_wins": self.consecutive_wins,
            "consecutive_losses": self.consecutive_losses,
            "total_return_pct": self.total_return_pct,
            "volatility": self.volatility,
            "n_trades": self.n_trades,
        }


@dataclass
class Signal:
    action: str  # "BUY" | "SELL" | "EXIT" | "HOLD"
    stop_loss: float | None = None
    take_profit: float | None = None


Strategy = Callable[[list[MarketCandle], int], Signal]


class Backtester:
    """Event-driven backtester. No look-ahead: strategy sees only bars[:i+1]."""

    def __init__(self, initial_capital: float = 100_000.0, lot_size: float = 1.0) -> None:
        self.initial_capital = initial_capital
        self.lot_size = lot_size

    def run(self, candles: list[MarketCandle], strategy: Strategy) -> BacktestResult:
        if len(candles) < 30:
            return BacktestResult(initial_capital=self.initial_capital, final_capital=self.initial_capital)
        capital = self.initial_capital
        position_side: str | None = None
        entry_price = 0.0
        entry_idx = 0
        sl: float | None = None
        tp: float | None = None
        trades: list[BacktestTrade] = []
        equity_curve: list[float] = [capital]

        def _close(side, eprice, exit_px, bar_idx, exit_time):
            nonlocal capital, position_side, entry_price, sl, tp
            direction = 1.0 if side == "BUY" else -1.0
            pnl = (exit_px - eprice) * direction * self.lot_size * 100_000.0
            capital += pnl
            trades.append(BacktestTrade(
                side=side, entry_time=candles[entry_idx].time,
                entry_price=eprice, exit_time=exit_time, exit_price=exit_px,
                pnl=pnl, pnl_pct=pnl / max(capital, 1.0), bars_held=bar_idx - entry_idx,
            ))
            position_side = None
            sl = tp = None

        for i in range(1, len(candles)):
            c = candles[i]
            # 1. manage open position (check SL/TP) — uses only current bar's high/low
            if position_side is not None:
                exit_px = None
                if position_side == "BUY":
                    if sl is not None and c.low <= sl:
                        exit_px = sl
                    elif tp is not None and c.high >= tp:
                        exit_px = tp
                else:  # SELL
                    if sl is not None and c.high >= sl:
                        exit_px = sl
                    elif tp is not None and c.low <= tp:
                        exit_px = tp
                if exit_px is not None:
                    _close(position_side, entry_price, exit_px, i, c.time)

            # 2. ask strategy what to do, using ONLY bars up to and including i
            sig = strategy(candles[: i + 1], i)
            if position_side is None:
                if sig.action in ("BUY", "SELL"):
                    position_side = sig.action
                    entry_price = c.close
                    entry_idx = i
                    sl = sig.stop_loss
                    tp = sig.take_profit
            else:
                if sig.action == "EXIT":
                    _close(position_side, entry_price, c.close, i, c.time)
            equity_curve.append(capital)

        # close any open position at the end
        if position_side is not None:
            _close(position_side, entry_price, candles[-1].close, len(candles) - 1, candles[-1].time)
            equity_curve.append(capital)

        return self._metrics(trades, capital, equity_curve)

    def _metrics(self, trades: list[BacktestTrade], final_capital: float, equity: list[float]) -> BacktestResult:
        n = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = -sum(t.pnl for t in losses)
        win_rate = len(wins) / n if n else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        avg_win = (gross_profit / len(wins)) if wins else 0.0
        avg_loss = (gross_loss / len(losses)) if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss) if n else 0.0

        peak = equity[0] if equity else final_capital
        max_dd = 0.0
        for e in equity:
            peak = max(peak, e)
            dd = (peak - e) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        rets = [t.pnl_pct for t in trades] if trades else [0.0]
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / max(len(rets) - 1, 1)
        sd = var ** 0.5
        sharpe = (mean_r / sd) * (len(rets) ** 0.5) if sd else 0.0

        cur_w = cur_l = 0
        max_w = max_l = 0
        for t in trades:
            if t.pnl > 0:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
            else:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)

        total_return_pct = (final_capital - self.initial_capital) / self.initial_capital * 100.0

        return BacktestResult(
            trades=trades, initial_capital=self.initial_capital,
            final_capital=final_capital, win_rate=win_rate,
            profit_factor=profit_factor, expectancy=expectancy,
            max_drawdown=max_dd, sharpe=sharpe, avg_win=avg_win, avg_loss=avg_loss,
            consecutive_wins=max_w, consecutive_losses=max_l,
            total_return_pct=total_return_pct, volatility=sd, n_trades=n,
        )


def split_train_val_test(candles: list[MarketCandle], train: float = 0.6, val: float = 0.2):
    """Split candles into train / validation / test (out-of-sample) sets."""
    n = len(candles)
    i1 = int(n * train)
    i2 = int(n * (train + val))
    return candles[:i1], candles[i1:i2], candles[i2:]


def walk_forward(candles: list[MarketCandle], strategy_factory: Callable[[], Strategy],
                 train_window: int = 500, test_window: int = 100) -> list[BacktestResult]:
    """Walk-forward analysis: train on window, test on next window, roll forward."""
    results: list[BacktestResult] = []
    bt = Backtester()
    i = 0
    while i + train_window + test_window <= len(candles):
        test = candles[i + train_window : i + train_window + test_window]
        strat = strategy_factory()
        results.append(bt.run(test, strat))
        i += test_window
    return results
