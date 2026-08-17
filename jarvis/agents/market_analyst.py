"""Market Analyst agent.

General market structure overview: trend, volatility, momentum, volume,
overall pair context. Produces an opinion (BUY/SELL/NEUTRAL) with confidence.
"""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.indicators import ema, sma, volatility
from jarvis.core.models import AgentReport


class MarketAnalystAgent(Agent):
    name = "MARKET ANALYST"

    def analyze(self, context: AgentContext) -> AgentReport:
        candles = context.candles(count=200)
        if len(candles) < 30:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.NEUTRAL,
                confidence=0.0,
                reasoning="insufficient data (<30 candles)",
                metrics={"candles": len(candles)},
            )
        closes = [c.close for c in candles]
        vols = [c.volume for c in candles]

        ema_fast = ema(closes, 20)
        ema_slow = ema(closes, 50)
        sma50 = sma(closes, 50)
        vol = volatility(closes, 20)
        avg_vol = sum(vols[-20:]) / min(20, len(vols))
        recent_vol = sum(vols[-5:]) / min(5, len(vols))

        # trend direction
        bull_signals, bear_signals = 0, 0
        if ema_fast is not None and ema_slow is not None:
            if ema_fast > ema_slow:
                bull_signals += 1
            else:
                bear_signals += 1
        if sma50 is not None:
            if closes[-1] > sma50:
                bull_signals += 1
            else:
                bear_signals += 1
        # momentum (last 5 vs prior 5)
        if len(closes) >= 10:
            recent_avg = sum(closes[-5:]) / 5
            prior_avg = sum(closes[-10:-5]) / 5
            if recent_avg > prior_avg:
                bull_signals += 1
            else:
                bear_signals += 1

        volume_confirmation = "low"
        if avg_vol > 0:
            ratio = recent_vol / avg_vol
            volume_confirmation = "high" if ratio > 1.1 else ("medium" if ratio > 0.85 else "low")

        if bull_signals > bear_signals:
            opinion = AgentOpinion.BUY
        elif bear_signals > bull_signals:
            opinion = AgentOpinion.SELL
        else:
            opinion = AgentOpinion.NEUTRAL

        confidence = self._clamp(0.4 + 0.15 * abs(bull_signals - bear_signals))

        regime = (
            "trending" if abs(bull_signals - bear_signals) >= 2 else "ranging"
        )

        reasoning = (
            f"EMA20={ema_fast}, EMA50={ema_slow}, SMA50={sma50}, "
            f"volatility={vol}, regime={regime}, volume_confirmation={volume_confirmation}"
        )
        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=confidence,
            reasoning=reasoning,
            metrics={
                "ema_fast": ema_fast,
                "ema_slow": ema_slow,
                "sma50": sma50,
                "volatility": vol,
                "volume_confirmation": volume_confirmation,
                "bull_signals": bull_signals,
                "bear_signals": bear_signals,
                "regime_hint": regime,
            },
        )
