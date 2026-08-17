"""JARVIS command-line interface — interactive conversational REPL.

Usage:
    python -m jarvis.cli            # interactive chat
    python -m jarvis.cli --dashboard
    python -m jarvis.cli --once "Analyse EUR/USD"
"""

from __future__ import annotations

import argparse
import sys

from jarvis.boss import JarvisBoss
from jarvis.brokers import build_broker
from jarvis.chat.handler import JarvisChat
from jarvis.core.config import get_settings
from jarvis.core.logging import get_logger
from jarvis.core.memory import get_memory
from jarvis.execution import ExecutionEngine

_log = get_logger("cli")


def build_components():
    settings = get_settings()
    broker = build_broker(settings)
    memory = get_memory()
    boss = JarvisBoss(broker, settings=settings, memory=memory)
    execution = ExecutionEngine(
        broker, settings=settings, memory=memory,
        event_risk_provider=boss._event_risk_provider,
        risk_gate=lambda p: boss.risk_agent.evaluate_proposal(p, broker.get_balance()),
    )
    chat = JarvisChat(boss, execution, memory=memory)
    return settings, broker, boss, execution, chat, memory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS AI Forex Trading OS")
    parser.add_argument("--once", help="Run a single command and exit", default=None)
    parser.add_argument("--dashboard", action="store_true", help="Print the dashboard and exit")
    args = parser.parse_args(argv)

    settings, broker, boss, execution, chat, memory = build_components()
    print("=" * 60)
    print("  JARVIS — AI Forex Trading Operating System  v0.1")
    print(f"  Mode: {settings.mode.indicator}")
    print(f"  Broker: {broker.name} | Live enabled: {settings.is_live_allowed()}")
    print("=" * 60)
    print("Rappel: JARVIS n'execute JAMAIS d'ordre reel sans votre instruction explicite.")
    print()

    if args.dashboard:
        from jarvis.dashboard.render import Dashboard

        Dashboard(boss, execution, memory).print()
        return 0

    if args.once:
        resp = chat.handle(args.once)
        print(resp.text)
        return 0

    # interactive REPL
    while True:
        try:
            line = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit", ":q"}:
            print("Au revoir.")
            break
        if line.lower() in {"dashboard", ":d"}:
            from jarvis.dashboard.render import Dashboard

            Dashboard(boss, execution, memory).print()
            continue
        if line.lower() in {"positions", ":p"}:
            from jarvis.engine.monitor import PositionMonitor

            mon = PositionMonitor(broker)
            print(mon.summarize())
            continue
        resp = chat.handle(line)
        print()
        print(resp.text)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
