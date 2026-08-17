"""Tests for the memory store and the chat/dashboard queries it powers."""



def test_record_and_query(memory):
    memory.record("decision", {"decision_id": "dec-1", "symbol": "EURUSD", "decision": "BUY"})
    rows = memory.query("decision")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "EURUSD"


def test_recent_decisions_and_orders(memory):
    memory.record("decision", {"decision_id": "d1", "symbol": "EURUSD"})
    memory.record("order", {"order_id": "o1", "symbol": "EURUSD", "status": "FILLED"})
    assert len(memory.recent_decisions()) == 1
    assert len(memory.recent_orders()) == 1


def test_model_versions(memory):
    memory.record("model_version", {"version": "V1", "promoted": True})
    memory.record("model_version", {"version": "V2", "promoted": False})
    vs = memory.model_versions()
    assert len(vs) == 2


def test_self_critic_entries(memory):
    memory.record("self_critic", {"id": "c1", "outcome": "WIN"})
    assert len(memory.self_critic_entries()) == 1


def test_stats(memory):
    memory.record("decision", {"decision_id": "d1"})
    memory.record("order", {"order_id": "o1"})
    s = memory.stats()
    assert s.get("decision", 0) >= 1
    assert s.get("order", 0) >= 1
