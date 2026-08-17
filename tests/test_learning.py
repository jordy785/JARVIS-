"""Tests for self-critic and model versioning."""

from jarvis.learning import active_version, promote_version, record_critique, register_version


def test_self_critic_win(memory):
    decision = {"proposal": {"estimated_risk_amount": 1000},
                "agent_reports": [{"opinion": "BUY"}, {"opinion": "BUY"}],
                "confidence": 0.8, "event_risk": "LOW"}
    trade = {"order_id": "ord-1", "symbol": "EURUSD", "side": "BUY"}
    entry = record_critique(memory, decision, trade, pnl=500)
    assert entry.outcome == "WIN"
    assert "Direction BUY was correct" in entry.correct_hypotheses


def test_self_critic_loss_with_macro(memory):
    decision = {"proposal": {"estimated_risk_amount": 1000},
                "agent_reports": [{"opinion": "BUY"}],
                "confidence": 0.8, "event_risk": "HIGH"}
    trade = {"order_id": "ord-2", "symbol": "EURUSD", "side": "BUY"}
    entry = record_critique(memory, decision, trade, pnl=-500)
    assert entry.outcome == "LOSS"
    assert entry.macro_unanticipated is True
    assert any("overconfident" in w.lower() for w in entry.wrong_hypotheses)


def test_model_version_register_and_promote(memory):
    v1 = register_version(memory, "baseline", {"fast": 20, "slow": 50}, {"win_rate": 0.5}, stage="backtest")
    assert v1.version == "V1"
    ok = promote_version(memory, "V1", {"win_rate": 0.55, "sharpe": 1.2})
    assert ok is True
    av = active_version(memory)
    assert av["version"] == "V1"
    assert av["promoted"] is True


def test_model_version_progression(memory):
    register_version(memory, "v1", {}, {"win_rate": 0.4})
    register_version(memory, "v2", {}, {"win_rate": 0.5})
    vs = memory.model_versions()
    assert len(vs) == 2
    versions = [v["version"] for v in vs]
    assert "V1" in versions and "V2" in versions
