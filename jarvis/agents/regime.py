"""Market Regime agent — classifies the market state.

Adapts strategy context: trend up/down, range, high/low volatility, unusual.
"""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion, MarketRegime
from jarvis.core.indicators import atr, ema, volatility
from jarvis.core.models import AgentReport


class MarketRegimeAgent(Agent):
    name = "MARKET REGIME"

    def analyze(self, context: AgentContext) -> AgentReport:
        candles = context.candles(count=200)
        if len(candles) < 50:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.NEUTRAL,
                confidence=0.0,
                reasoning="insufficient data",
                metrics={"regime": MarketRegime.RANGE.value},
            )
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        ema200 = ema(closes, 200) if len(closes) >= 200 else None
        vol = volatility(closes, 20)
        atr_v = atr(highs, lows, closes, 14)
        price = closes[-1]
        avg_price = sum(closes) / len(closes)

        # volatility relative to price
        vol_ratio = (vol / price) if price else 0.0
        high_vol = vol_ratio > 0.015
        low_vol = vol_ratio < 0.003

        # trend strength
        trending_up = (
            ema20 is not None and ema50 is not None and ema20 > ema50
            and (ema200 is None or price > ema200)
        )
        trending_down = (
            ema20 is not None and ema50 is not None and ema20 < ema50
            and (ema200 is None or price < ema200)
        )

        # ADX-like slope proxy: how far price is from its mean
        deviation = abs(price - avg_price) / price if price else 0.0
        unusual = deviation > 0.03 or (atr_v is not None and price and atr_v / price > 0.02)

        if unusual:
            regime = MarketRegime.UNUSUAL
        elif trending_up and not high_vol:
            regime = MarketRegime.TREND_UP
        elif trending_down and not high_vol:
            regime = MarketRegime.TREND_DOWN
        elif high_vol:
            regime = MarketRegime.HIGH_VOLATILITY
        elif low_vol:
            regime = MarketRegime.LOW_VOLATILITY
        else:
            regime = MarketRegime.RANGE

        # opinion: in trend, follow trend; in range/vol/unusual → neutral/cautious
        if regime is MarketRegime.TREND_UP:
            opinion = AgentOpinion.BUY
        elif regime is MarketRegime.TREND_DOWN:
            opinion = AgentOpinion.SELL
        else:
            opinion = AgentOpinion.NEUTRAL
        confidence = self._clamp(0.5 if regime in (MarketRegime.TREND_UP, MarketRegime.TREND_DOWN) else 0.35)

        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=confidence,
            reasoning=f"regime={regime.value} vol_ratio={vol_ratio:.4f} deviation={deviation:.4f}",
            metrics={
                "regime": regime.value,
                "volatility_ratio": vol_ratio,
                "atr": atr_v,
                "deviation": deviation,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
            },
        )
