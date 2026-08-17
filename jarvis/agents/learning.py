"""Learning agent — tracks model versions and feeds self-critic back into decisions.

This agent surfaces the latest learned context (e.g., "the active model has
underperformed on EUR/USD lately, suggesting reduced confidence"). It does not
retrain online; instead it reports performance metadata from memory and a
suggested model version to use.
"""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.logging import get_logger
from jarvis.core.models import AgentReport

_log = get_logger("agents.learning")


class LearningAgent(Agent):
    name = "LEARNING"

    def __init__(self, settings=None, memory=None) -> None:
        super().__init__(settings)
        self._memory = memory

    @property
    def memory(self):
        if self._memory is None:
            try:
                from jarvis.core.memory import get_memory

                self._memory = get_memory()
            except Exception:
                self._memory = None
        return self._memory

    def latest_model_version(self) -> dict | None:
        mem = self.memory
        if not mem:
            return None
        versions = mem.model_versions()
        return versions[0] if versions else None

    def analyze(self, context: AgentContext) -> AgentReport:
        mv = self.latest_model_version()
        if not mv:
            return AgentReport(
                agent_name=self.name,
                opinion=AgentOpinion.NEUTRAL,
                confidence=0.2,
                reasoning="no model version available yet — learning not started",
                metrics={"model_version": None},
            )
        perf = mv.get("performance", {})
        win_rate = perf.get("win_rate")
        note = ""
        if win_rate is not None and win_rate < 0.4:
            note = f"recent win_rate {win_rate:.0%} below threshold — lower confidence warranted"
        return AgentReport(
            agent_name=self.name,
            opinion=AgentOpinion.NEUTRAL,
            confidence=0.5,
            reasoning=(
                f"active model: {mv.get('version', '?')} ; "
                f"win_rate={win_rate if win_rate is not None else 'n/a'}. {note}"
            ).strip(),
            metrics={"model_version": mv.get("version"), "performance": perf},
        )
