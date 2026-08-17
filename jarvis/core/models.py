"""Shared data models (lightweight dataclasses) used across JARVIS.

These are deliberately plain dataclasses (not ORM models) for portability and
testability. Persistence is handled by :mod:`jarvis.core.memory`.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.core.enums import (
    AgentOpinion,
    Decision,
    EventRiskLevel,
    MarketRegime,
    OrderSide,
    OrderSource,
    OrderStatus,
    OrderType,
    RiskVerdict,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class MarketCandle:
    """A single OHLCV bar."""

    symbol: str
    timeframe: str  # e.g. "M15", "H1"
    time: str  # ISO timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NewsEvent:
    """A macro/news calendar event relevant to a currency or pair."""

    id: str = field(default_factory=lambda: _uid("news"))
    time: str = field(default_factory=_now)  # event time (ISO)
    currency: str = ""  # e.g. "EUR"
    impact: EventRiskLevel = EventRiskLevel.UNKNOWN
    title: str = ""
    source: str = ""
    forecast: str = ""
    previous: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReport:
    """Structured analysis produced by a sub-agent for the BOSS."""

    agent_name: str
    opinion: AgentOpinion
    confidence: float  # 0.0 - 1.0
    reasoning: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    # Macro/news agent can attach event-risk metadata
    event_risk: EventRiskLevel | None = None
    # Risk agent can attach a formal verdict
    risk_verdict: RiskVerdict | None = None
    # Critic agent can attach a warning level
    warning: bool = False
    timestamp: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # enums -> strings for serialization
        d["opinion"] = self.opinion.value
        if self.event_risk is not None:
            d["event_risk"] = self.event_risk.value
        if self.risk_verdict is not None:
            d["risk_verdict"] = self.risk_verdict.value
        return d


@dataclass
class TradeProposal:
    """A prepared-but-UNEXECUTED trade proposed by the BOSS.

    Creating this object never sends an order. It is purely informational and
    awaits an explicit user command.
    """

    proposal_id: str = field(default_factory=lambda: _uid("prop"))
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    volume_lots: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    confidence: float = 0.0  # BOSS confidence 0..1
    risk_level: str = "UNKNOWN"  # LOW / MODERATE / HIGH / REJECTED
    reasoning: str = ""
    estimated_spread_cost: float | None = None
    estimated_risk_amount: float | None = None
    created_at: str = field(default_factory=_now)

    @property
    def is_rejected(self) -> bool:
        return self.risk_level.upper() == "REJECTED"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        return d


@dataclass
class DecisionPacket:
    """Full decision output of the BOSS for one analysis cycle."""

    decision_id: str = field(default_factory=lambda: _uid("dec"))
    symbol: str = ""
    decision: Decision = Decision.NO_TRADE
    confidence: float = 0.0
    risk_level: str = "UNKNOWN"
    regime: MarketRegime = MarketRegime.RANGE
    agent_reports: list[AgentReport] = field(default_factory=list)
    proposal: TradeProposal | None = None
    reasoning: str = ""
    event_risk: EventRiskLevel = EventRiskLevel.UNKNOWN
    timestamp: str = field(default_factory=_now)

    def agent_opinions_summary(self) -> dict[str, str]:
        return {r.agent_name: r.opinion.value for r in self.agent_reports}

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "risk_level": self.risk_level,
            "regime": self.regime.value,
            "agent_reports": [r.as_dict() for r in self.agent_reports],
            "proposal": self.proposal.as_dict() if self.proposal else None,
            "reasoning": self.reasoning,
            "event_risk": self.event_risk.value,
            "timestamp": self.timestamp,
        }


@dataclass
class Position:
    """An open position (live or paper)."""

    position_id: str
    symbol: str
    side: OrderSide
    volume_lots: float
    entry_price: float
    ticket: int | None = None  # broker ticket for live
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: str = field(default_factory=_now)
    current_price: float | None = None
    unrealized_pnl: float | None = None
    source: OrderSource = OrderSource.PAPER_SIMULATION

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["source"] = self.source.value
        return d


@dataclass
class OrderRecord:
    """Immutable record of an order request (the audit trail)."""

    order_id: str = field(default_factory=lambda: _uid("ord"))
    user: str = "system"
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    volume_lots: float = 0.0
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    spread_cost: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    source: OrderSource = OrderSource.PAPER_SIMULATION
    decision_id: str | None = None  # associated JARVIS decision
    proposal_id: str | None = None
    broker_ticket: int | None = None
    rejection_reason: str | None = None
    timestamp: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["side"] = self.side.value
        d["order_type"] = self.order_type.value
        d["status"] = self.status.value
        d["source"] = self.source.value
        return d
