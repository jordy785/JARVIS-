"""Shared pytest fixtures for JARVIS tests."""

import os
import tempfile

import pytest

# Force safe defaults BEFORE importing jarvis
os.environ.pop("MT5_PASSWORD", None)
os.environ.pop("MACRO_NEWS_API_KEY", None)
os.environ.setdefault("TRADING_MODE", "PAPER")
os.environ.setdefault("LIVE_TRADING_ENABLED", "false")
os.environ.setdefault("TRADING_KILLSWITCH", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_FILE", "")


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # let Memory create it
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def settings():
    from jarvis.core.config import get_settings, reset_settings_cache
    reset_settings_cache()
    return get_settings()


@pytest.fixture
def demo_broker():
    from jarvis.brokers.demo import DemoBroker
    b = DemoBroker(initial_balance=500_000.0)
    b.connect()
    return b


@pytest.fixture
def memory(tmp_db):
    from jarvis.core.memory import reset_memory_for_tests
    return reset_memory_for_tests(tmp_db)


@pytest.fixture
def boss(demo_broker, memory):
    from jarvis.boss import JarvisBoss
    return JarvisBoss(demo_broker, memory=memory)


@pytest.fixture
def execution(demo_broker, memory, boss):
    from jarvis.core.enums import RiskVerdict
    from jarvis.execution import ExecutionEngine
    return ExecutionEngine(
        demo_broker, memory=memory,
        event_risk_provider=boss._event_risk_provider,
        risk_gate=lambda p: RiskVerdict.APPROVED,
    )


@pytest.fixture
def chat(boss, execution, memory):
    from jarvis.chat.handler import JarvisChat
    return JarvisChat(boss, execution, memory=memory)


@pytest.fixture(autouse=True)
def _reset_settings():
    from jarvis.core.config import reset_settings_cache
    reset_settings_cache()
    yield
    reset_settings_cache()
