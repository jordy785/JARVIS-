"""Dashboard renderer.

Pure rendering (no side effects beyond printing). Pulls data from the broker,
boss (agents), memory, and execution engine.
"""

from __future__ import annotations

from jarvis.boss import JarvisBoss
from jarvis.core.memory import Memory
from jarvis.execution.engine import ExecutionEngine

try:
    from rich.console import Console

    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False


class Dashboard:
    def __init__(self, boss: JarvisBoss, execution: ExecutionEngine, memory: Memory) -> None:
        self.boss = boss
        self.execution = execution
        self.memory = memory
        self.console = Console() if _HAS_RICH else None

    def render(self) -> str:
        sections = [
            self._render_portfolio(),
            self._render_jarvis(),
            self._render_agents(),
            self._render_macro(),
            self._render_trades(),
        ]
        return "\n\n".join(sections)

    def print(self) -> None:
        if self.console:
            self.console.print(self.render())
        else:
            print(self.render())

    # ------------------------------------------------------------------ #
    def _render_portfolio(self) -> str:
        b = self.boss.broker
        info = b.get_account_info()
        positions = b.get_positions()
        if info is None:
            return "PORTFOLIO: broker non connecte"
        equity = info.equity
        pnl = equity - info.balance
        exposure = sum(abs(p.volume_lots) for p in positions)
        lines = [
            "PORTFOLIO",
            f"  Balance    : {info.balance:.2f} {info.currency}",
            f"  Equity     : {equity:.2f} {info.currency}",
            f"  P&L       : {pnl:+.2f}",
            f"  P&L %     : {(pnl / info.balance * 100):+.2f}%" if info.balance else "  P&L %     : n/a",
            f"  Positions : {len(positions)}",
            f"  Exposure  : {exposure:.2f} lots",
            f"  Mode      : {self.boss.settings.mode.indicator}",
        ]
        return "\n".join(lines)

    def _render_jarvis(self) -> str:
        from jarvis.learning.model_versioning import active_version

        av = active_version(self.memory)
        stats = self.memory.stats() if self.memory else {}
        lines = [
            "JARVIS",
            f"  Active model   : {av.get('version') if av else 'none'}",
            f"  Stage          : {av.get('evaluation_stage') if av else 'n/a'}",
            f"  Decisions      : {stats.get('decision', 0)}",
            f"  Orders         : {stats.get('order', 0)}",
            f"  Self-critiques : {stats.get('self_critic', 0)}",
            f"  Model versions : {stats.get('model_version', 0)}",
        ]
        return "\n".join(lines)

    def _render_agents(self) -> str:
        # Use the latest decision's agent opinions if available
        decisions = self.memory.recent_decisions(limit=1) if self.memory else []
        if not decisions:
            return "AGENTS: aucune analyse recente. Lancez « Analyse EUR/USD »."
        d = decisions[0]
        lines = [f"AGENTS — dernieres opinions ({d.get('symbol')})", "─" * 40]
        for r in d.get("agent_reports", []):
            lines.append(f"  {r.get('agent_name','?'):<16}: {r.get('opinion','?')}")
        lines.append("─" * 40)
        lines.append(f"  BOSS            : {d.get('decision','?')} (conf {d.get('confidence',0):.0%})")
        return "\n".join(lines)

    def _render_macro(self) -> str:
        events = self.memory.macro_events(limit=10) if self.memory else []
        if not events:
            return "CALENDRIER MACRO: aucun evenement enregistre."
        lines = ["CALENDRIER MACRO — derniers evenements"]
        for e in events:
            lines.append(
                f"  {e.get('currency','?')} | {e.get('impact','?')} | {e.get('title','?')}"
            )
        return "\n".join(lines)

    def _render_trades(self) -> str:
        orders = self.memory.recent_orders(limit=10) if self.memory else []
        if not orders:
            return "TRADES: aucun ordre enregistre."
        lines = ["TRADES — derniers ordres"]
        for o in orders:
            lines.append(
                f"  {o.get('symbol','?')} {o.get('side','?')} {o.get('volume_lots',0)} "
                f"lots | {o.get('status','?')} | src={o.get('source','?')} | {o.get('timestamp','')}"
            )
        return "\n".join(lines)
