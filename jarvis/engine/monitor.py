"""Position monitor — real-time tracking of open positions.

Reports price, position, P&L, stop, target, drawdown, spread, order status.

IMPORTANT: this is purely INFORMATIONAL. An alert (e.g., price near stop, or a
fresh macro news item) is NEVER interpreted as authorization to modify or close
a position. Any real action still requires a new explicit user authorization,
unless a protection order (SL/TP) was already placed with the broker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jarvis.brokers.base import TradingBroker
from jarvis.core.logging import get_logger

_log = get_logger("engine.monitor")


@dataclass
class PositionStatus:
    position_id: str
    symbol: str
    side: str
    volume: float
    entry_price: float
    current_price: float | None
    unrealized_pnl: float | None
    unrealized_pnl_pct: float | None
    stop_loss: float | None
    take_profit: float | None
    spread: float | None
    near_stop: bool = False
    near_target: bool = False
    drawdown: float | None = None
    notes: list[str] = None  # type: ignore[assignment]


class PositionMonitor:
    """Reads open positions from the broker and produces status snapshots."""

    def __init__(self, broker: TradingBroker,
                 near_stop_factor: float = 0.2,
                 macro_alert_provider: Callable[[str], str | None] | None = None) -> None:
        self.broker = broker
        self.near_stop_factor = near_stop_factor
        self.macro_alert_provider = macro_alert_provider

    def snapshot(self) -> list[PositionStatus]:
        positions = self.broker.get_positions()
        out: list[PositionStatus] = []
        for p in positions:
            q = self.broker.get_market_price(p.symbol)
            cur = q.bid if (q and p.side.value == "BUY") else (q.ask if q else None)
            pnl = None
            pnl_pct = None
            if cur is not None:
                direction = 1.0 if p.side.value == "BUY" else -1.0
                pnl = (cur - p.entry_price) * direction * p.volume_lots
                pnl_pct = (cur / p.entry_price - 1.0) * direction * 100.0
            near_stop = near_target = False
            notes: list[str] = []
            if p.stop_loss is not None and cur is not None:
                dist = abs(cur - p.stop_loss)
                ref = abs(p.entry_price - p.stop_loss) or 1e-9
                if dist < self.near_stop_factor * ref:
                    near_stop = True
                    notes.append("Le prix s'est rapproche du stop-loss.")
            if p.take_profit is not None and cur is not None:
                dist = abs(cur - p.take_profit)
                ref = abs(p.take_profit - p.entry_price) or 1e-9
                if dist < self.near_stop_factor * ref:
                    near_target = True
                    notes.append("Le prix s'est rapproche du take-profit.")
            # drawdown from peak pnl (very rough)
            dd = None
            if self.macro_alert_provider is not None:
                alert = self.macro_alert_provider(p.symbol)
                if alert:
                    notes.append(f"Alerte macro: {alert}")
            out.append(PositionStatus(
                position_id=p.position_id, symbol=p.symbol, side=p.side.value,
                volume=p.volume_lots, entry_price=p.entry_price, current_price=cur,
                unrealized_pnl=pnl, unrealized_pnl_pct=pnl_pct,
                stop_loss=p.stop_loss, take_profit=p.take_profit,
                spread=(q.spread if q else None), near_stop=near_stop,
                near_target=near_target, drawdown=dd, notes=notes,
            ))
        return out

    def summarize(self) -> str:
        snaps = self.snapshot()
        if not snaps:
            return "Aucune position ouverte."
        lines = []
        for s in snaps:
            pnl_str = f"{s.unrealized_pnl:+.2f}" if s.unrealized_pnl is not None else "n/a"
            pct_str = f"{s.unrealized_pnl_pct:+.2f}%" if s.unrealized_pnl_pct is not None else ""
            line = (
                f"Position {s.symbol} {s.side} {s.volume} lots | "
                f"entree={s.entry_price} actuel={s.current_price} | "
                f"P&L={pnl_str} ({pct_str})"
            )
            if s.near_stop:
                line += " | ⚠️ PRES DU STOP"
            for n in (s.notes or []):
                line += f" | {n}"
            lines.append(line)
        return "\n".join(lines)
