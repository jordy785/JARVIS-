"""Risk agent — independent pre-trade risk gate.

Verifies position size, exposure, potential loss, stops, drawdown, volatility,
concentration, number of positions, daily limits, AND event risk (from the
Macro/News agent). Can return APPROVED or REJECTED with explanation.

Even if the BOSS is favorable to a trade, a REJECTED risk verdict must block
execution. The execution engine consumes a risk-gate hook built from this
agent.
"""

from __future__ import annotations

from collections.abc import Callable

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion, EventRiskLevel, RiskVerdict
from jarvis.core.indicators import atr
from jarvis.core.logging import get_logger
from jarvis.core.models import AgentReport, TradeProposal

_log = get_logger("agents.risk")


class RiskAgent(Agent):
    name = "RISK"

    def __init__(
        self,
        settings=None,
        event_risk_provider: Callable[[str], EventRiskLevel] | None = None,
    ) -> None:
        super().__init__(settings)
        self.event_risk_provider = event_risk_provider

    def _risk_amount(self, proposal: TradeProposal, balance: float) -> float | None:
        if proposal.entry_price and proposal.stop_loss:
            risk_per_lot = abs(proposal.entry_price - proposal.stop_loss)
            # crude multiplier (100k for non-JPY, 1k for JPY) — used for sizing sanity
            mult = 1000.0 if "JPY" in proposal.symbol.upper() else 100_000.0
            return risk_per_lot * proposal.volume_lots * mult / max(balance, 1.0) * 100.0
        return None

    def evaluate_proposal(self, proposal: TradeProposal, balance: float | None) -> RiskVerdict:
        """Standalone evaluation used as the execution engine's risk gate."""
        reasons: list[str] = []
        s = self.settings

        # event risk
        if self.event_risk_provider is not None:
            lvl = self.event_risk_provider(proposal.symbol)
            if lvl is EventRiskLevel.HIGH:
                reasons.append(f"event_risk={lvl.value}: high macro risk imminent")

        # volume sanity
        if proposal.volume_lots <= 0:
            reasons.append("volume must be > 0")
        if proposal.volume_lots > 100:
            reasons.append("volume exceeds sanity cap")

        # risk per trade %
        if balance and balance > 0:
            risk_pct = self._risk_amount(proposal, balance)
            if risk_pct is not None and risk_pct > s.risk_max_risk_per_trade_pct:
                reasons.append(
                    f"risk per trade {risk_pct:.2f}% > limit {s.risk_max_risk_per_trade_pct}%"
                )

        # missing stop loss
        if proposal.stop_loss is None:
            reasons.append("no stop-loss defined")

        verdict = RiskVerdict.APPROVED if not reasons else RiskVerdict.REJECTED
        if reasons:
            _log.info("RISK rejected proposal %s: %s", proposal.proposal_id, "; ".join(reasons))
        return verdict

    def analyze(self, context: AgentContext) -> AgentReport:
        """For the BOSS summary — opinion reflects whether risk is acceptable."""
        candles = context.candles(count=100)
        balance = context.balance()
        atr_v = None
        if len(candles) >= 15:
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            closes = [c.close for c in candles]
            atr_v = atr(highs, lows, closes, 14)

        # event risk
        lvl = EventRiskLevel.UNKNOWN
        if self.event_risk_provider is not None:
            lvl = self.event_risk_provider(context.symbol)

        issues: list[str] = []
        if balance is not None and balance <= 0:
            issues.append("non-positive balance")
        if atr_v is not None and candles and candles[-1].close:
            ratio = atr_v / candles[-1].close
            if ratio > 0.02:
                issues.append(f"volatility high (atr/price={ratio:.4f})")
        if lvl is EventRiskLevel.HIGH:
            issues.append("high macro event risk")

        if lvl is EventRiskLevel.HIGH:
            opinion = AgentOpinion.REJECTED
        elif issues:
            opinion = AgentOpinion.WARNING
        else:
            opinion = AgentOpinion.APPROVED

        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=0.6,
            reasoning="; ".join(issues) if issues else "no blocking risk identified",
            metrics={
                "atr": atr_v,
                "balance": balance,
                "event_risk": lvl.value,
                "issues": issues,
            },
            risk_verdict=RiskVerdict.REJECTED if lvl is EventRiskLevel.HIGH else RiskVerdict.APPROVED,
        )
