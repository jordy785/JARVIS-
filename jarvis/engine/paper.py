"""Paper trading engine — virtual portfolio, no real money.

Reproduces spread, slippage, execution, liquidity and positions as reasonably
as possible given the available (synthetic or real) market data.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from jarvis.brokers.base import TradingBroker
from jarvis.core.enums import OrderSide, OrderSource
from jarvis.core.logging import get_logger
from jarvis.core.models import Position

_log = get_logger("engine.paper")


@dataclass
class PaperTrade:
    position_id: str
    symbol: str
    side: OrderSide
    volume: float
    entry_price: float
    exit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: str | None = None
    pnl: float | None = None
    status: str = "OPEN"


class PaperTradingEngine:
    """Self-contained paper portfolio. Reads prices from a broker (demo or real)."""

    def __init__(self, broker: TradingBroker, initial_capital: float = 500_000.0,
                 currency: str = "XOF", slippage_pips: float = 0.5) -> None:
        self.broker = broker
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.currency = currency
        self.slippage_pips = slippage_pips
        self.positions: dict[str, PaperTrade] = {}
        self.closed: list[PaperTrade] = []
        self._rng = random.Random(1234)
        self._next_id = 1

    def _pip(self, symbol: str) -> float:
        return 0.01 if "JPY" in symbol.upper() else 0.0001

    def _lot_mult(self, symbol: str) -> float:
        return 1000.0 if "JPY" in symbol.upper() else 100_000.0

    def open_position(self, symbol: str, side: OrderSide, volume: float,
                      stop_loss: float | None = None, take_profit: float | None = None) -> PaperTrade:
        q = self.broker.get_market_price(symbol)
        if q is None:
            raise RuntimeError(f"no price for {symbol}")
        slip = self.slippage_pips * self._pip(symbol) * (1 + abs(self._rng.gauss(0, 0.3)))
        entry = (q.ask + slip) if side is OrderSide.BUY else (q.bid - slip)
        pid = f"paper-{self._next_id}"
        self._next_id += 1
        pt = PaperTrade(
            position_id=pid, symbol=symbol.upper().replace("/", ""), side=side,
            volume=volume, entry_price=entry, stop_loss=stop_loss, take_profit=take_profit,
        )
        self.positions[pid] = pt
        _log.info("paper opened %s %s %.2f @ %.5f", pid, side.value, volume, entry)
        return pt

    def close_position(self, position_id: str) -> PaperTrade | None:
        pt = self.positions.pop(position_id, None)
        if pt is None:
            return None
        q = self.broker.get_market_price(pt.symbol)
        if q is None:
            return None
        slip = self.slippage_pips * self._pip(pt.symbol) * (1 + abs(self._rng.gauss(0, 0.3)))
        exit_px = (q.bid - slip) if pt.side is OrderSide.BUY else (q.ask + slip)
        direction = 1.0 if pt.side is OrderSide.BUY else -1.0
        pnl = (exit_px - pt.entry_price) * direction * pt.volume * self._lot_mult(pt.symbol)
        pt.exit_price = exit_px
        pt.pnl = pnl
        pt.status = "CLOSED"
        pt.closed_at = datetime.now(timezone.utc).isoformat()
        self.balance += pnl
        self.closed.append(pt)
        _log.info("paper closed %s pnl=%.2f", position_id, pnl)
        return pt

    def mark_to_market(self) -> list[Position]:
        out: list[Position] = []
        for pt in self.positions.values():
            q = self.broker.get_market_price(pt.symbol)
            cur = q.bid if (q and pt.side is OrderSide.BUY) else (q.ask if q else None)
            pnl = None
            if cur is not None:
                direction = 1.0 if pt.side is OrderSide.BUY else -1.0
                pnl = (cur - pt.entry_price) * direction * pt.volume * self._lot_mult(pt.symbol)
            out.append(Position(
                position_id=pt.position_id, symbol=pt.symbol, side=pt.side,
                volume_lots=pt.volume, entry_price=pt.entry_price,
                stop_loss=pt.stop_loss, take_profit=pt.take_profit,
                opened_at=pt.opened_at, current_price=cur, unrealized_pnl=pnl,
                source=OrderSource.PAPER_SIMULATION,
            ))
        return out

    def equity(self) -> float:
        eq = self.balance
        for pt in self.positions.values():
            q = self.broker.get_market_price(pt.symbol)
            if q is None:
                continue
            cur = q.bid if pt.side is OrderSide.BUY else q.ask
            direction = 1.0 if pt.side is OrderSide.BUY else -1.0
            eq += (cur - pt.entry_price) * direction * pt.volume * self._lot_mult(pt.symbol)
        return eq

    def stats(self) -> dict:
        wins = [t for t in self.closed if (t.pnl or 0) > 0]
        losses = [t for t in self.closed if (t.pnl or 0) <= 0]
        return {
            "initial_capital": self.initial_capital,
            "balance": self.balance,
            "equity": self.equity(),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed),
            "win_rate": len(wins) / len(self.closed) if self.closed else 0.0,
            "total_pnl": sum(t.pnl or 0 for t in self.closed),
            "wins": len(wins),
            "losses": len(losses),
        }
