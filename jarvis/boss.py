"""JARVIS BOSS — central orchestrator.

Receives analyses from all sub-agents, detects contradictions, evaluates
confidence, consults the macro/news + risk + critic agents, and produces a
:class:`DecisionPacket` containing a final theoretical decision AND an optional
:class:`TradeProposal`.

CRITICAL INVARIANT: producing a ``TradeProposal`` does NOT execute anything.
The BOSS only ever RETURNS proposals. Execution requires the chat layer to
forward an explicit user command and the user to confirm. The BOSS has no
handle to the execution engine's submit path.
"""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.agents.critic import CriticAgent
from jarvis.agents.learning import LearningAgent
from jarvis.agents.macro_news import MacroNewsAgent
from jarvis.agents.market_analyst import MarketAnalystAgent
from jarvis.agents.quant import QuantAgent
from jarvis.agents.regime import MarketRegimeAgent
from jarvis.agents.research import ResearchAgent
from jarvis.agents.risk import RiskAgent
from jarvis.agents.technical import TechnicalAnalystAgent
from jarvis.brokers.base import TradingBroker
from jarvis.core.config import Settings, get_settings
from jarvis.core.enums import (
    AgentOpinion,
    Decision,
    EventRiskLevel,
    MarketRegime,
    OrderSide,
    OrderType,
    RiskVerdict,
)
from jarvis.core.logging import get_logger
from jarvis.core.models import AgentReport, DecisionPacket, TradeProposal

_log = get_logger("boss")


class JarvisBoss:
    """Central decision brain. Stateless per analysis (uses memory for history)."""

    def __init__(
        self,
        broker: TradingBroker,
        settings: Settings | None = None,
        macro_news_agent: MacroNewsAgent | None = None,
        risk_agent: RiskAgent | None = None,
        memory=None,
    ) -> None:
        self.broker = broker
        self.settings = settings or get_settings()
        self.memory = memory

        # Build agents. The Macro/News agent provides the event-risk hook that
        # the Risk agent and the ExecutionEngine consume.
        self.macro_news = macro_news_agent or MacroNewsAgent(self.settings)
        self.risk_agent = risk_agent or RiskAgent(
            self.settings, event_risk_provider=self.macro_news.evaluate_event_risk_with_symbol
            if hasattr(self.macro_news, "evaluate_event_risk_with_symbol")
            else self._event_risk_provider
        )

        self.agents: list[Agent] = [
            MarketAnalystAgent(self.settings),
            QuantAgent(self.settings),
            TechnicalAnalystAgent(self.settings),
            MarketRegimeAgent(self.settings),
            self.macro_news,
            ResearchAgent(self.settings),
            self.risk_agent,
            CriticAgent(self.settings),
            LearningAgent(self.settings, memory=self.memory),
        ]

    def _event_risk_provider(self, symbol: str) -> EventRiskLevel:
        risk, _ = self.macro_news.evaluate_event_risk(symbol)
        return risk

    def analyze(self, symbol: str, timeframe: str = "H1") -> DecisionPacket:
        """Run all sub-agents and synthesize a decision.

        Returns a :class:`DecisionPacket`. NEVER submits an order.
        """
        sym = symbol.upper().replace("/", "")
        ctx = AgentContext(symbol=sym, timeframe=timeframe, broker=self.broker)

        reports: list[AgentReport] = []
        for agent in self.agents:
            try:
                reports.append(agent.analyze(ctx))
            except Exception as exc:  # agents must never break the BOSS
                _log.warning("agent %s failed: %s", agent.name, exc)
                reports.append(
                    AgentReport(
                        agent_name=agent.name,
                        opinion=AgentOpinion.NEUTRAL,
                        confidence=0.0,
                        reasoning=f"agent error: {exc}",
                        warning=True,
                    )
                )

        decision = self._synthesize(sym, reports, ctx)
        # persist decision
        try:
            from jarvis.core.memory import get_memory

            mem = self.memory or get_memory()
            mem.record("decision", decision.as_dict())
        except Exception:  # pragma: no cover
            pass
        _log.info(
            "decision %s for %s: %s confidence=%.0f%%",
            decision.decision_id, sym, decision.decision.value, decision.confidence * 100,
        )
        return decision

    # ------------------------------------------------------------------ #
    def _synthesize(self, symbol: str, reports: list[AgentReport], ctx: AgentContext) -> DecisionPacket:
        by_name = {r.agent_name: r for r in reports}
        macro = by_name.get("MACRO/NEWS")
        risk = by_name.get("RISK")
        critic = by_name.get("CRITIC")
        regime_report = by_name.get("MARKET REGIME")

        event_risk = macro.event_risk if (macro and macro.event_risk) else EventRiskLevel.UNKNOWN

        # Count directional votes among "directional" agents
        directional = [
            by_name.get("MARKET ANALYST"),
            by_name.get("QUANT"),
            by_name.get("TECHNICAL ANALYST"),
            by_name.get("MARKET REGIME"),
        ]
        buys = sum(1 for r in directional if r and r.opinion is AgentOpinion.BUY)
        sells = sum(1 for r in directional if r and r.opinion is AgentOpinion.SELL)
        neutrals = sum(1 for r in directional if r and r.opinion is AgentOpinion.NEUTRAL)

        aligned = max(buys, sells)
        total = len([r for r in directional if r])
        alignment_ratio = aligned / total if total else 0.0

        # Hard blocks:
        blocked = False
        block_reasons: list[str] = []
        if risk and risk.risk_verdict is RiskVerdict.REJECTED:
            blocked = True
            block_reasons.append("RISK REJECTED")
        if event_risk is EventRiskLevel.HIGH:
            blocked = True
            block_reasons.append("high macro event risk")
        if critic and critic.warning and alignment_ratio < 0.75:
            block_reasons.append("critic warning + weak alignment")

        # Determine regime from regime report metrics if available
        regime = MarketRegime.RANGE
        if regime_report and regime_report.metrics.get("regime"):
            try:
                regime = MarketRegime(regime_report.metrics["regime"])
            except ValueError:
                pass

        # Direction
        if blocked:
            decision = Decision.NO_TRADE
            side = None
        elif alignment_ratio >= 0.75 and buys > sells:
            decision = Decision.BUY
            side = OrderSide.BUY
        elif alignment_ratio >= 0.75 and sells > buys:
            decision = Decision.SELL
            side = OrderSide.SELL
        else:
            decision = Decision.WAIT if not blocked else Decision.NO_TRADE
            side = None

        # Confidence: blend alignment + average directional confidence, penalized by macro/critic
        avg_conf = (
            sum(r.confidence for r in directional if r) / total if total else 0.0
        )
        confidence = self._clamp(avg_conf * alignment_ratio)
        if event_risk in (EventRiskLevel.HIGH, EventRiskLevel.UNKNOWN):
            confidence *= 0.7
        if critic and critic.warning:
            confidence *= 0.85

        # Risk level
        if blocked:
            risk_level = "REJECTED"
        elif event_risk is EventRiskLevel.HIGH:
            risk_level = "HIGH"
        elif event_risk is EventRiskLevel.MODERATE:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW" if decision in (Decision.BUY, Decision.SELL) else "UNKNOWN"

        # Build proposal ONLY if we have a direction and not blocked
        proposal = None
        if side is not None and not blocked:
            proposal = self._build_proposal(symbol, side, ctx, confidence, event_risk, regime)

        reasoning = self._reasoning_text(
            reports, buys, sells, neutrals, alignment_ratio, block_reasons, event_risk
        )

        return DecisionPacket(
            symbol=symbol,
            decision=decision,
            confidence=confidence,
            risk_level=risk_level,
            regime=regime,
            agent_reports=reports,
            proposal=proposal,
            reasoning=reasoning,
            event_risk=event_risk,
        )

    def _build_proposal(
        self,
        symbol: str,
        side: OrderSide,
        ctx: AgentContext,
        confidence: float,
        event_risk: EventRiskLevel,
        regime: MarketRegime,
    ) -> TradeProposal:
        q = ctx.quote()
        price = q.ask if (q and side is OrderSide.BUY) else (q.bid if q else None)
        # crude SL/TP using ATR
        candles = ctx.candles(count=100)
        atr_v = None
        if len(candles) >= 15:
            from jarvis.core.indicators import atr

            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            closes = [c.close for c in candles]
            atr_v = atr(highs, lows, closes, 14)
        if atr_v is None or price is None:
            atr_v = atr_v or (price * 0.002 if price else 0.0)
            if price is None:
                price = 0.0

        sl_dist = atr_v * 1.5
        tp_dist = atr_v * 3.0
        if side is OrderSide.BUY:
            sl = price - sl_dist
            tp = price + tp_dist
        else:
            sl = price + sl_dist
            tp = price - tp_dist

        # volume: simple risk-based sizing using 1% of balance
        bal = ctx.balance() or 0.0
        mult = 1000.0 if "JPY" in symbol else 100_000.0
        risk_amount = bal * (self.settings.risk_max_risk_per_trade_pct / 100.0)
        volume = (risk_amount / (sl_dist * mult)) if (sl_dist > 0 and mult) else 0.0
        # clamp to reasonable min
        volume = max(0.01, round(volume, 2))

        spread_cost = q.spread * volume * mult if q else None
        return TradeProposal(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            volume_lots=volume,
            entry_price=price,
            stop_loss=sl,
            take_profit=tp,
            confidence=confidence,
            risk_level="MODERATE" if event_risk is EventRiskLevel.MODERATE else "LOW",
            reasoning=f"directional alignment supports {side.value}; SL/TP from ATR*1.5/3.0",
            estimated_spread_cost=spread_cost,
            estimated_risk_amount=risk_amount,
        )

    def _reasoning_text(
        self, reports, buys, sells, neutrals, alignment_ratio, block_reasons, event_risk
    ) -> str:
        parts = [f"directional votes: BUY={buys} SELL={sells} NEUTRAL={neutrals}"]
        parts.append(f"alignment_ratio={alignment_ratio:.0%}")
        if block_reasons:
            parts.append("BLOCKED: " + "; ".join(block_reasons))
        if event_risk in (EventRiskLevel.HIGH, EventRiskLevel.MODERATE, EventRiskLevel.UNKNOWN):
            parts.append(f"event_risk={event_risk.value}")
        # one-liners per agent
        for r in reports:
            parts.append(f"[{r.agent_name}] {r.opinion.value} (conf {r.confidence:.0%})")
        return " | ".join(parts)

    @staticmethod
    def _clamp(x: float) -> float:
        return max(0.0, min(1.0, x))
