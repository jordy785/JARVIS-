"""Base agent class and shared agent context (read-only market data view).

The :class:`AgentContext` exposes ONLY read methods of the broker
(``get_candles``, ``get_market_price``, ``get_positions``, ``get_balance``).
It deliberately does NOT expose ``place_order`` / ``modify_order`` /
``close_position``, so agents physically cannot submit orders even by
mistake.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from jarvis.brokers.base import TradingBroker
from jarvis.core.models import AgentReport, MarketCandle


@dataclass
class AgentContext:
    """Read-only market context handed to each agent."""

    symbol: str
    timeframe: str = "H1"
    broker: TradingBroker | None = None
    # cached candles per timeframe
    _candles: dict[str, list[MarketCandle]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def _norm_symbol(self) -> str:
        return self.symbol.upper().replace("/", "")

    def candles(self, timeframe: str | None = None, count: int = 200) -> list[MarketCandle]:
        tf = timeframe or self.timeframe
        if tf in self._candles:
            return self._candles[tf]
        if self.broker is None:
            return []
        out = self.broker.get_candles(self._norm_symbol(), tf, count)
        self._candles[tf] = out
        return out

    def price(self) -> float | None:
        if self.broker is None:
            return None
        q = self.broker.get_market_price(self._norm_symbol())
        return q.mid if q else None

    def quote(self):
        if self.broker is None:
            return None
        return self.broker.get_market_price(self._norm_symbol())

    def positions(self):
        if self.broker is None:
            return []
        return self.broker.get_positions()

    def balance(self) -> float | None:
        if self.broker is None:
            return None
        return self.broker.get_balance()


class Agent(ABC):
    """Abstract sub-agent."""

    name: str = "abstract"

    def __init__(self, settings=None) -> None:
        from jarvis.core.config import get_settings

        self.settings = settings or get_settings()

    @abstractmethod
    def analyze(self, context: AgentContext) -> AgentReport:
        """Produce a structured report for the BOSS. Must NOT submit orders."""

    @staticmethod
    def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, x))
