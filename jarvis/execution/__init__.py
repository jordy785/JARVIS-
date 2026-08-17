"""Execution layer.

This package is the SINGLE authorized path to submit orders to a broker.
No agent, no analyst, and no chat handler may call ``broker.place_order``
directly — they must go through :class:`jarvis.execution.ExecutionEngine`.

The flow is:

    TradeProposal  --prepare_order-->  OrderRecord(PENDING)
    user confirms  --confirm_and_submit--> broker.place_order

A ``TradeProposal`` produced from an analysis is NEVER auto-submitted.
"""

from jarvis.execution.engine import ExecutionBlocked, ExecutionEngine, SafetyCheckResult

__all__ = ["ExecutionEngine", "ExecutionBlocked", "SafetyCheckResult"]
