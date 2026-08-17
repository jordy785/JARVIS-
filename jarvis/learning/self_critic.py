"""Self-critic — post-trade analysis journal.

After each trade (real or simulated), JARVIS analyzes:
- why the trade was proposed
- which hypotheses were correct / wrong
- whether timing was right
- whether risk was appropriate
- whether an unanticipated macro event played a role
- whether the market had changed
- whether agents were overconfident

Entries are stored in memory (kind="self_critic") so JARVIS can answer questions
like "Quelle est ta principale erreur cette semaine ?".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.core.logging import get_logger

_log = get_logger("learning.self_critic")


@dataclass
class CritiqueEntry:
    id: str
    trade_id: str
    symbol: str
    side: str
    outcome: str  # "WIN" | "LOSS" | "BREAKEVEN"
    pnl: float
    correct_hypotheses: list[str] = field(default_factory=list)
    wrong_hypotheses: list[str] = field(default_factory=list)
    timing_ok: bool = True
    risk_appropriate: bool = True
    macro_unanticipated: bool = False
    market_changed: bool = False
    agents_overconfident: bool = False
    lessons: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "trade_id": self.trade_id, "symbol": self.symbol,
            "side": self.side, "outcome": self.outcome, "pnl": self.pnl,
            "correct_hypotheses": self.correct_hypotheses,
            "wrong_hypotheses": self.wrong_hypotheses,
            "timing_ok": self.timing_ok, "risk_appropriate": self.risk_appropriate,
            "macro_unanticipated": self.macro_unanticipated,
            "market_changed": self.market_changed,
            "agents_overconfident": self.agents_overconfident,
            "lessons": self.lessons, "created_at": self.created_at,
        }


class SelfCritic:
    """Produces structured post-trade critiques."""

    def critique(self, decision: dict, trade: dict, pnl: float) -> CritiqueEntry:
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        proposal = decision.get("proposal") or {}
        agent_reports = decision.get("agent_reports") or []
        bull_count = sum(1 for r in agent_reports if r.get("opinion") == "BUY")
        bear_count = sum(1 for r in agent_reports if r.get("opinion") == "SELL")
        conf = decision.get("confidence", 0.0)
        event_risk = (decision.get("event_risk") or "UNKNOWN")

        correct: list[str] = []
        wrong: list[str] = []
        # Direction hypothesis
        side = (trade.get("side") or "").upper()
        if outcome == "WIN":
            correct.append(f"Direction {side} was correct")
        else:
            wrong.append(f"Direction {side} was incorrect")
        # Confidence hypothesis
        if conf > 0.7 and outcome != "WIN":
            wrong.append("Agents were overconfident (confidence >70%)")
        elif conf < 0.4 and outcome == "WIN":
            correct.append("Trade succeeded despite low confidence")
        # Macro hypothesis
        if event_risk in ("HIGH", "MODERATE") and pnl < 0:
            wrong.append("Event risk was elevated — caution was warranted")
        # alignment
        if (side == "BUY" and bull_count < bear_count) or (side == "SELL" and bear_count < bull_count):
            wrong.append("Trade went against majority of directional agents")

        lessons: list[str] = []
        if outcome == "LOSS":
            lessons.append("Review entry timing and confirmation strength before next similar setup.")
        if conf > 0.7 and outcome != "WIN":
            lessons.append("Cap confidence in overconfident setups.")

        return CritiqueEntry(
            id=f"critique-{trade.get('order_id', datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))}",
            trade_id=trade.get("order_id", ""), symbol=trade.get("symbol", ""),
            side=side, outcome=outcome, pnl=pnl,
            correct_hypotheses=correct, wrong_hypotheses=wrong,
            timing_ok=(outcome == "WIN"),
            risk_appropriate=(abs(pnl) < (proposal.get("estimated_risk_amount") or 0) * 3),
            macro_unanticipated=(event_risk in ("HIGH", "MODERATE") and pnl < 0),
            market_changed=False,
            agents_overconfident=(conf > 0.7 and outcome != "WIN"),
            lessons=lessons,
        )


def record_critique(memory, decision: dict, trade: dict, pnl: float) -> CritiqueEntry:
    critic = SelfCritic()
    entry = critic.critique(decision, trade, pnl)
    try:
        memory.record("self_critic", entry.as_dict(), ref_id=entry.trade_id)
        _log.info("recorded critique for trade %s outcome=%s", entry.trade_id, entry.outcome)
    except Exception as exc:  # pragma: no cover
        _log.warning("failed to record critique: %s", exc)
    return entry
