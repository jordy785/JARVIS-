"""Abstract broker interface (adapter pattern).

This interface is intentionally broker-agnostic. Only the
:mod:`jarvis.execution` engine is permitted to call mutating methods
(``place_order``, ``modify_order``, ``cancel_order``, ``close_position``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from jarvis.core.enums import OrderSide, OrderType
from jarvis.core.models import MarketCandle, Position


@dataclass
class BrokerQuote:
    symbol: str
    bid: float
    ask: float
    spread: float
    time: str

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0


@dataclass
class AccountInfo:
    login: int
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str
    leverage: int = 1


@dataclass
class OrderResult:
    success: bool
    ticket: int | None = None
    price: float | None = None
    message: str = ""
    raw: dict[str, Any] | None = None


class TradingBroker(ABC):
    """Abstract trading broker. Implementations talk to real or simulated APIs."""

    #: Name used in logs/order records.
    name: str = "abstract"

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker. Returns True on success."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the broker is currently connected."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection."""

    @abstractmethod
    def get_account_info(self) -> AccountInfo | None:
        ...

    @abstractmethod
    def get_balance(self) -> float | None:
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_market_price(self, symbol: str) -> BrokerQuote | None:
        ...

    @abstractmethod
    def get_candles(
        self, symbol: str, timeframe: str, count: int = 200
    ) -> list[MarketCandle]:
        ...

    @abstractmethod
    def symbol_valid(self, symbol: str) -> bool:
        ...

    @abstractmethod
    def market_open(self) -> bool:
        """Whether the forex market is currently open (not weekend/holiday)."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        ...

    @abstractmethod
    def modify_order(
        self,
        ticket: int,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        price: float | None = None,
    ) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, ticket: int) -> OrderResult:
        ...

    @abstractmethod
    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        ...
