"""Tests for each sub-agent and the BOSS synthesis."""

from jarvis.agents.base import AgentContext
from jarvis.agents.critic import CriticAgent
from jarvis.agents.learning import LearningAgent
from jarvis.agents.macro_news import MacroNewsAgent, symbol_currencies
from jarvis.agents.market_analyst import MarketAnalystAgent
from jarvis.agents.quant import QuantAgent
from jarvis.agents.regime import MarketRegimeAgent
from jarvis.agents.research import ResearchAgent
from jarvis.agents.risk import RiskAgent
from jarvis.agents.technical import TechnicalAnalystAgent
from jarvis.core.enums import AgentOpinion, EventRiskLevel


def test_market_analyst(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = MarketAnalystAgent().analyze(ctx)
    assert r.opinion in (AgentOpinion.BUY, AgentOpinion.SELL, AgentOpinion.NEUTRAL)
    assert 0.0 <= r.confidence <= 1.0


def test_quant(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = QuantAgent().analyze(ctx)
    assert "prob_up" in r.metrics
    assert 0.0 <= r.metrics["prob_up"] <= 1.0


def test_technical_multitimeframe(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = TechnicalAnalystAgent().analyze(ctx)
    assert "timeframes" in r.metrics
    assert set(r.metrics["timeframes"].keys()) == {"M15", "H1", "H4", "D1"}


def test_regime(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = MarketRegimeAgent().analyze(ctx)
    assert r.metrics["regime"]  # some regime reported


def test_macro_news_unknown_by_default(demo_broker):
    """Default provider returns no events -> UNKNOWN risk (prudence)."""
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = MacroNewsAgent().analyze(ctx)
    assert r.event_risk is EventRiskLevel.UNKNOWN
    assert r.opinion is AgentOpinion.WARNING  # prudence


def test_macro_news_high_event_blocks():
    """A high-impact upcoming event must elevate risk and recommend no-trade."""
    from datetime import timedelta

    from jarvis.core.models import NewsEvent

    def provider(now, horizon):
        return [
            NewsEvent(
                currency="EUR", impact=EventRiskLevel.HIGH,
                title="ECB interest rate decision",
                time=(now + timedelta(hours=18)).isoformat(),
            )
        ]

    agent = MacroNewsAgent(calendar_provider=provider)
    risk, events = agent.evaluate_event_risk("EURUSD")
    assert risk is EventRiskLevel.HIGH
    assert len(events) == 1
    r = agent.analyze(__import__("jarvis.agents.base", fromlist=["AgentContext"]).AgentContext(symbol="EURUSD"))
    assert r.opinion is AgentOpinion.NO_TRADE


def test_symbol_currencies():
    assert symbol_currencies("EUR/USD") == ("EUR", "USD")
    assert symbol_currencies("GBPJPY") == ("GBP", "JPY")


def test_risk_rejects_no_stop_loss(demo_broker):
    from jarvis.core.enums import OrderSide, RiskVerdict
    from jarvis.core.models import TradeProposal
    agent = RiskAgent(event_risk_provider=lambda s: EventRiskLevel.LOW)
    p = TradeProposal(symbol="EURUSD", side=OrderSide.BUY, volume_lots=0.1,
                      entry_price=1.08, stop_loss=None)
    assert agent.evaluate_proposal(p, balance=100_000) is RiskVerdict.REJECTED


def test_risk_rejects_high_event_risk(demo_broker):
    from jarvis.core.enums import OrderSide, RiskVerdict
    from jarvis.core.models import TradeProposal
    agent = RiskAgent(event_risk_provider=lambda s: EventRiskLevel.HIGH)
    p = TradeProposal(symbol="EURUSD", side=OrderSide.BUY, volume_lots=0.1,
                      entry_price=1.08, stop_loss=1.07)
    assert agent.evaluate_proposal(p, balance=100_000) is RiskVerdict.REJECTED


def test_critic(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = CriticAgent().analyze(ctx)
    assert r.opinion in (AgentOpinion.WARNING, AgentOpinion.NEUTRAL)


def test_research(demo_broker):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = ResearchAgent().analyze(ctx)
    assert "hypothesis" in r.metrics


def test_learning(demo_broker, memory):
    ctx = AgentContext(symbol="EURUSD", broker=demo_broker)
    r = LearningAgent(memory=memory).analyze(ctx)
    assert r.opinion is AgentOpinion.NEUTRAL


def test_boss_synthesizes_decision(boss):
    d = boss.analyze("EURUSD")
    assert len(d.agent_reports) == 9  # all sub-agents reported
    names = {r.agent_name for r in d.agent_reports}
    assert "MARKET ANALYST" in names
    assert "QUANT" in names
    assert "MACRO/NEWS" in names
    assert "RISK" in names
    assert "CRITIC" in names
    assert "LEARNING" in names


def test_boss_blocks_on_high_event_risk(demo_broker, memory):
    """When macro event risk is HIGH, the BOSS must NOT propose a trade."""
    from jarvis.agents.macro_news import MacroNewsAgent
    from jarvis.boss import JarvisBoss
    from jarvis.core.enums import Decision, EventRiskLevel
    from jarvis.core.models import NewsEvent

    def provider(now, horizon):
        return [NewsEvent(currency="EUR", impact=EventRiskLevel.HIGH,
                          title="ECB rate decision", time=now.isoformat())]

    macro = MacroNewsAgent(calendar_provider=provider)
    boss = JarvisBoss(demo_broker, memory=memory, macro_news_agent=macro)
    d = boss.analyze("EURUSD")
    assert d.decision is Decision.NO_TRADE
    assert d.proposal is None
    assert d.risk_level == "REJECTED"
