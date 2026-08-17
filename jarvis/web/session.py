"""Session-scoped state for the Streamlit app.

Builds the JARVIS stack ONCE per session and keeps it in ``st.session_state`` so
the chat history and pending confirmations persist across reruns.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    role: str  # "user" | "jarvis"
    text: str
    actions: list[str] = field(default_factory=list)
    decision_summary: str | None = None


def build_stack():
    """Construct broker, boss, execution engine, chat — shared per session."""
    from jarvis.boss import JarvisBoss
    from jarvis.brokers import build_broker
    from jarvis.chat.handler import JarvisChat
    from jarvis.core.config import get_settings
    from jarvis.core.memory import get_memory
    from jarvis.execution import ExecutionEngine

    settings = get_settings()
    broker = build_broker(settings)
    memory = get_memory()
    boss = JarvisBoss(broker, settings=settings, memory=memory)
    from jarvis.core.enums import Mode, RiskVerdict

    # In PAPER mode the risk gate is advisory: we still want to be able to
    # simulate trades even if position sizing is aggressive (paper is for
    # testing). In LIVE the gate is strict — a REJECTED proposal blocks.
    if settings.mode is Mode.PAPER:

        def risk_gate(_proposal):
            return RiskVerdict.APPROVED
    else:

        def risk_gate(proposal):
            return boss.risk_agent.evaluate_proposal(proposal, broker.get_balance())

    execution = ExecutionEngine(
        broker, settings=settings, memory=memory,
        event_risk_provider=boss._event_risk_provider,
        risk_gate=risk_gate,
    )
    chat = JarvisChat(boss, execution, memory=memory)
    return settings, broker, boss, execution, chat, memory


def get_stack():
    import streamlit as st

    if "jarvis_stack" not in st.session_state:
        st.session_state["jarvis_stack"] = build_stack()
    return st.session_state["jarvis_stack"]


def get_chat_history() -> list[ChatMessage]:
    import streamlit as st

    if "jarvis_history" not in st.session_state:
        st.session_state["jarvis_history"] = [
            ChatMessage(
                role="jarvis",
                text=(
                    "Bonjour, je suis JARVIS, votre assistant de trading forex. "
                    "Je peux analyser les marchés, surveiller les news macro, évaluer le risque "
                    "et préparer des trades — mais je n'exécute JAMAIS un ordre sans votre "
                    "instruction explicite.\n\n"
                    "Essayez : « Analyse EUR/USD », « Cherche les meilleures opportunités », "
                    "ou « Exécute le trade proposé »."
                ),
            )
        ]
    return st.session_state["jarvis_history"]
