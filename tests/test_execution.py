"""Tests for the execution engine safety checks and gating."""

import pytest

from jarvis.core.enums import OrderSide, OrderStatus, OrderType, RiskVerdict
from jarvis.core.models import TradeProposal
from jarvis.execution import ExecutionBlocked, ExecutionEngine


def _proposal(symbol="EURUSD", side=OrderSide.BUY, vol=0.1, sl=1.07, tp=1.09):
    return TradeProposal(symbol=symbol, side=side, order_type=OrderType.MARKET,
                         volume_lots=vol, entry_price=1.08, stop_loss=sl, take_profit=tp,
                         risk_level="LOW")


def test_prepare_order_does_not_submit(demo_broker, memory):
    eng = ExecutionEngine(demo_broker, memory=memory,
                          event_risk_provider=lambda s: __import__("jarvis.core.enums", fromlist=["EventRiskLevel"]).EventRiskLevel.LOW,
                          risk_gate=lambda p: RiskVerdict.APPROVED)
    before = len(demo_broker.get_positions())
    order = eng.prepare_order(_proposal(), user="u")
    assert order.status is OrderStatus.PENDING
    after = len(demo_broker.get_positions())
    assert after == before  # nothing submitted yet


def test_confirm_submits_order(demo_broker, memory):
    eng = ExecutionEngine(demo_broker, memory=memory,
                          event_risk_provider=lambda s: __import__("jarvis.core.enums", fromlist=["EventRiskLevel"]).EventRiskLevel.LOW,
                          risk_gate=lambda p: RiskVerdict.APPROVED)
    order = eng.prepare_order(_proposal(), user="u")
    before = len(demo_broker.get_positions())
    final = eng.confirm_and_submit(order.order_id)
    assert final.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED)
    assert len(demo_broker.get_positions()) == before + 1


def test_rejected_proposal_blocked(demo_broker, memory):
    eng = ExecutionEngine(demo_broker, memory=memory,
                          risk_gate=lambda p: RiskVerdict.REJECTED)
    with pytest.raises(ExecutionBlocked):
        eng.prepare_order(_proposal(), user="u")


def test_killswitch_blocks(demo_broker, memory, monkeypatch):
    from jarvis.core.config import reset_settings_cache
    monkeypatch.setenv("TRADING_KILLSWITCH", "true")
    reset_settings_cache()
    eng = ExecutionEngine(demo_broker, memory=memory,
                          risk_gate=lambda p: RiskVerdict.APPROVED)
    with pytest.raises(ExecutionBlocked):
        eng.prepare_order(_proposal(), user="u")


def test_invalid_volume_blocked(demo_broker, memory):
    eng = ExecutionEngine(demo_broker, memory=memory,
                          risk_gate=lambda p: RiskVerdict.APPROVED)
    with pytest.raises(ExecutionBlocked):
        eng.prepare_order(_proposal(vol=0.0), user="u")


def test_cancel_pending(demo_broker, memory):
    eng = ExecutionEngine(demo_broker, memory=memory,
                          risk_gate=lambda p: RiskVerdict.APPROVED,
                          event_risk_provider=lambda s: __import__("jarvis.core.enums", fromlist=["EventRiskLevel"]).EventRiskLevel.LOW)
    order = eng.prepare_order(_proposal(), user="u")
    assert eng.cancel_pending(order.order_id) is True
    # confirming a cancelled order must fail
    final = eng.confirm_and_submit(order.order_id)
    assert final.status is OrderStatus.REJECTED


def test_high_event_risk_blocks_live(monkeypatch, demo_broker, memory):
    from jarvis.core.config import get_settings, reset_settings_cache
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    reset_settings_cache()
    from jarvis.core.enums import EventRiskLevel
    eng = ExecutionEngine(demo_broker, settings=get_settings(), memory=memory,
                          event_risk_provider=lambda s: EventRiskLevel.HIGH,
                          risk_gate=lambda p: RiskVerdict.APPROVED)
    with pytest.raises(ExecutionBlocked):
        eng.prepare_order(_proposal(), user="u")
