"""CRITICAL TESTS: an analysis / info / opportunity command must NEVER trigger
an order (real or paper). Only an explicit order command + explicit confirmation
may submit an order.

These are the guarantee tests required by the JARVIS specification (section 28).
"""

import pytest


def _count_positions(broker):
    return len(broker.get_positions())


@pytest.mark.parametrize(
    "message",
    [
        "Analyse EUR/USD",
        "Cherche une opportunite",
        "Cherche les meilleures opportunites",
        "Quel serait ton trade ?",
        "Que penses-tu de GBP/USD ?",
        "Y a-t-il une news importante aujourd'hui ?",
        "Montre-moi les signaux actuels",
        "Pourquoi tu ne trades pas ?",
        "Analyse GBP/JPY",
    ],
)
def test_analysis_commands_never_place_orders(chat, demo_broker, message):
    before = _count_positions(demo_broker)
    resp = chat.handle(message)
    after = _count_positions(demo_broker)
    assert after == before, (
        f"VIOLATION: command {message!r} triggered an order "
        f"(positions {before} -> {after}). Response: {resp.text[:200]}"
    )
    # The response must not claim an order was sent
    assert "Ordre envoye" not in resp.text, f"command {message!r} claimed an order was sent"
    assert "order_submitted" not in resp.actions, f"command {message!r} produced order_submitted action"


def test_analysis_then_implicit_confirmation_does_not_submit(chat, demo_broker):
    """An analysis cannot create a pending order, so an immediate 'oui' must do nothing."""
    chat.handle("Analyse EUR/USD")
    before = _count_positions(demo_broker)
    # user says 'oui' but there was NO pending order (analysis never stages one)
    resp = chat.handle("oui")
    after = _count_positions(demo_broker)
    assert after == before
    # 'oui' without pending order is treated as unknown/no-op
    assert "order_submitted" not in resp.actions


def test_explicit_order_requires_confirmation(chat, demo_broker):
    """'Execute le trade propose' must stage a pending order, NOT submit it."""
    chat.handle("Analyse EUR/USD")
    before = _count_positions(demo_broker)
    resp = chat.handle("Execute le trade propose")
    after_stage = _count_positions(demo_broker)
    # staging must NOT place a position
    assert after_stage == before, "staging an order placed a position"
    assert resp.awaiting_confirmation is True
    assert "live_prepare" in resp.actions or "paper_prepare" in resp.actions


def test_explicit_order_ambiguous_confirmation_not_submitted(chat, demo_broker):
    chat.handle("Analyse EUR/USD")
    r1 = chat.handle("Execute le trade propose")
    assert r1.awaiting_confirmation
    before = _count_positions(demo_broker)
    # ambiguous — must NOT submit
    r2 = chat.handle("peut-etre plus tard")
    after = _count_positions(demo_broker)
    assert after == before
    assert "order_submitted" not in r2.actions
    assert r2.awaiting_confirmation is True  # still waiting


def test_explicit_order_cancel_does_not_submit(chat, demo_broker):
    chat.handle("Analyse EUR/USD")
    r1 = chat.handle("Execute le trade propose")
    assert r1.awaiting_confirmation
    before = _count_positions(demo_broker)
    r2 = chat.handle("non, annule")
    after = _count_positions(demo_broker)
    assert after == before
    assert "order_cancelled" in r2.actions or "order_submitted" not in r2.actions


def test_explicit_order_confirmed_submits_position(chat, demo_broker):
    chat.handle("Analyse EUR/USD")
    r1 = chat.handle("Execute le trade propose")
    assert r1.awaiting_confirmation
    before = _count_positions(demo_broker)
    r2 = chat.handle("oui")
    after = _count_positions(demo_broker)
    # now the order MUST have been submitted
    assert after == before + 1, f"expected 1 new position, got {after - before}"
    assert "order_submitted" in r2.actions


def test_analysis_mode_blocks_orders(monkeypatch, demo_broker, memory, boss):
    """In ANALYSIS mode, even an explicit order command must be blocked."""
    from jarvis.core.config import reset_settings_cache
    monkeypatch.setenv("TRADING_MODE", "ANALYSIS")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    reset_settings_cache()
    from jarvis.chat.handler import JarvisChat
    from jarvis.core.config import get_settings
    from jarvis.core.enums import RiskVerdict
    from jarvis.execution import ExecutionEngine
    s = get_settings()
    # rebuild boss with new settings
    from jarvis.boss import JarvisBoss
    boss2 = JarvisBoss(demo_broker, settings=s, memory=memory)
    exec_eng = ExecutionEngine(
        demo_broker, settings=s, memory=memory,
        event_risk_provider=boss2._event_risk_provider,
        risk_gate=lambda p: RiskVerdict.APPROVED,
    )
    chat2 = JarvisChat(boss2, exec_eng, memory=memory)
    chat2.handle("Analyse EUR/USD")
    before = _count_positions(demo_broker)
    resp = chat2.handle("Execute le trade propose")
    after = _count_positions(demo_broker)
    assert after == before
    assert "mode_block" in resp.actions
