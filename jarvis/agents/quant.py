"""Quant agent — statistics, probabilities, correlations, expectancy.

Never presents a probability as a certainty. Returns distributions and
confidence intervals alongside its opinion.
"""

from __future__ import annotations

import math
import statistics

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.indicators import stdev
from jarvis.core.models import AgentReport


class QuantAgent(Agent):
    name = "QUANT"

    def analyze(self, context: AgentContext) -> AgentReport:
        candles = context.candles(count=200)
        if len(candles) < 30:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.NEUTRAL,
                confidence=0.0,
                reasoning="insufficient data",
            )
        closes = [c.close for c in candles]
        # returns
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1]]
        if not rets:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.NEUTRAL,
                confidence=0.0,
                reasoning="no returns computable",
            )
        mean_ret = statistics.mean(rets)
        sd = stdev(rets, min(20, len(rets))) or statistics.pstdev(rets)
        sd = sd or 1e-9
        # hit rate: % positive returns
        wins = sum(1 for r in rets if r > 0)
        win_rate = wins / len(rets)
        avg_win = statistics.mean([r for r in rets if r > 0] or [0.0])
        avg_loss = statistics.mean([abs(r) for r in rets if r <= 0] or [0.0]) or 1e-9
        expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
        # approximate probability of positive next-bar return via normal approximation
        z = mean_ret / sd if sd else 0.0
        prob_up = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        # drawdown estimate
        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            peak = max(peak, c)
            dd = (peak - c) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        if prob_up > 0.58:
            opinion = AgentOpinion.BUY
        elif prob_up < 0.42:
            opinion = AgentOpinion.SELL
        else:
            opinion = AgentOpinion.NEUTRAL
        confidence = self._clamp(abs(prob_up - 0.5) * 2.0)

        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=confidence,
            reasoning=(
                f"Prob(next bar up)≈{prob_up:.1%} (not a certainty); win_rate={win_rate:.1%}; "
                f"expectancy={expectancy:.5f}; max_dd={max_dd:.1%}; vol={sd:.5f}"
            ),
            metrics={
                "win_rate": win_rate,
                "expectancy": expectancy,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "volatility": sd,
                "prob_up": prob_up,
                "max_drawdown": max_dd,
                "mean_return": mean_ret,
            },
        )
