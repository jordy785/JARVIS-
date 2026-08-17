"""Tests for the position monitor (informational only)."""

from jarvis.core.enums import OrderSide
from jarvis.engine.monitor import PositionMonitor


def test_monitor_informational_only(demo_broker):
    """Monitor must not modify positions; it only reports."""
    demo_broker.place_order("EURUSD", OrderSide.BUY, 0.1)
    mon = PositionMonitor(demo_broker)
    snaps = mon.snapshot()
    assert len(snaps) == 1
    s = snaps[0]
    assert s.symbol == "EURUSD"
    assert s.side == "BUY"
    # monitor must not have changed positions
    assert len(demo_broker.get_positions()) == 1
    summary = mon.summarize()
    assert "EURUSD" in summary


def test_monitor_empty_when_no_positions(demo_broker):
    mon = PositionMonitor(demo_broker)
    assert mon.snapshot() == []
    assert "Aucune position" in mon.summarize()
