"""Research agent — proposes hypotheses (strategies/filters) without touching production.

It does not modify the live system. It produces research proposals stored in
memory and surfaced for later backtest/paper evaluation by the Learning agent.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.models import AgentReport


@dataclass
class ResearchHypothesis:
    name: str
    description: str
    parameters: dict[str, Any]


class ResearchAgent(Agent):
    name = "RESEARCH"

    _HYPOTHESES = [
        ResearchHypothesis(
            name="EMA-cross + ATR filter",
            description="Trade EMA20/50 cross only when ATR/volatility is below a threshold.",
            parameters={"ema_fast": 20, "ema_slow": 50, "atr_max_ratio": 0.012},
        ),
        ResearchHypothesis(
            name="RSI mean-reversion in ranges",
            description="Buy RSI<30 / Sell RSI>70 only when regime=RANGE.",
            parameters={"rsi_period": 14, "oversold": 30, "overbought": 70},
        ),
        ResearchHypothesis(
            name="Breakout with volume confirmation",
            description="Enter on resistance break only if recent volume > 110% avg.",
            parameters={"lookback": 20, "volume_ratio_min": 1.1},
        ),
        ResearchHypothesis(
            name="Macro-aware position sizing",
            description="Cut size by 50% when event risk is MODERATE, skip when HIGH.",
            parameters={"moderate_scale": 0.5, "block_on_high": True},
        ),
    ]

    def analyze(self, context: AgentContext) -> AgentReport:
        # Pick a hypothesis deterministically-ish based on a hash of the symbol.
        rng = random.Random(hash(context.symbol) & 0xFFFFFFFF)
        hyp = rng.choice(self._HYPOTHESES)
        return AgentReport(
            agent_name=self.name,
            opinion=AgentOpinion.NEUTRAL,
            confidence=0.3,
            reasoning=(
                f"Proposed hypothesis for evaluation: {hyp.name}. {hyp.description} "
                f"This is a research suggestion — it does NOT change production behavior."
            ),
            metrics={
                "hypothesis": hyp.name,
                "description": hyp.description,
                "parameters": hyp.parameters,
            },
        )
