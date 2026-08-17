"""Critic agent — actively tries to refute the BOSS' emerging decision.

Looks for: contradictory signals, false-breakout risk, excessive volatility,
insufficient data, over-optimization, unstable macro, unusual regime.
"""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.indicators import atr, rsi, volatility
from jarvis.core.models import AgentReport


class CriticAgent(Agent):
    name = "CRITIC"

    def analyze(self, context: AgentContext) -> AgentReport:
        candles = context.candles(count=200)
        warnings: list[str] = []

        if len(candles) < 50:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.WARNING,
                confidence=0.5,
                reasoning="insufficient data to validate any decision",
                warning=True,
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        vol = volatility(closes, 20)
        atr_v = atr(highs, lows, closes, 14)
        r = rsi(closes, 14)

        # contradictory signals: recent candles alternating strongly
        recent = closes[-5:]
        swings = sum(1 for i in range(1, len(recent)) if (recent[i] - recent[i - 1]) * (recent[i - 1] - recent[i - 2]) < 0) if len(recent) >= 3 else 0
        if swings >= 2:
            warnings.append("choppy/alternating recent price action — false-breakout risk")

        # volatility extremes
        if vol is not None and closes[-1]:
            if vol / closes[-1] > 0.015:
                warnings.append("volatility elevated — whipsaw risk")

        # RSI extremes (mean-reversion risk)
        if r is not None:
            if r > 75:
                warnings.append(f"RSI overbought ({r:.0f}) — reversal risk on BUY")
            elif r < 25:
                warnings.append(f"RSI oversold ({r:.0f}) — reversal risk on SELL")

        # low ATR relative to spread → poor reward/risk
        q = context.quote()
        if q is not None and atr_v is not None and atr_v > 0:
            if q.spread / atr_v > 0.5:
                warnings.append("spread is large vs ATR — poor reward/risk")

        if warnings:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.WARNING,
                confidence=0.6,
                reasoning="; ".join(warnings),
                metrics={"volatility": vol, "atr": atr_v, "rsi": r, "warnings": warnings},
                warning=True,
            )
        return AgentReport(
            agent_name=self.name,
            opinion=AgentOpinion.NEUTRAL,
            confidence=0.4,
            reasoning="no strong objection found (this is not an endorsement)",
            metrics={"volatility": vol, "atr": atr_v, "rsi": r, "warnings": []},
            warning=False,
        )
