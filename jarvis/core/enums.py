"""Enums shared across the JARVIS system."""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    """Operating mode of the JARVIS system."""

    ANALYSIS = "ANALYSIS"
    PAPER = "PAPER"
    LIVE = "LIVE"

    @property
    def indicator(self) -> str:
        return {
            Mode.ANALYSIS: "🟢 ANALYSIS",
            Mode.PAPER: "🟡 PAPER TRADING",
            Mode.LIVE: "🔴 LIVE TRADING",
        }[self]

    def allows_order_submission(self) -> bool:
        return self in (Mode.PAPER, Mode.LIVE)

    def allows_real_orders(self) -> bool:
        return self is Mode.LIVE


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


class OrderSource(str, Enum):
    """What originated the order — used to enforce the explicit-order rule."""

    USER_EXPLICIT = "USER_EXPLICIT"
    PAPER_SIMULATION = "PAPER_SIMULATION"
    BACKTEST = "BACKTEST"
    # NOTE: there is intentionally no "AUTO" / "ANALYSIS" source. An analysis
    # can never become an order by itself.


class AgentOpinion(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"
    WARNING = "WARNING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"
    WAIT = "WAIT"


class MarketRegime(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNUSUAL = "UNUSUAL"


class EventRiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"
