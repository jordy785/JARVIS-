"""Sub-agents of the JARVIS system.

Each agent is a small, focused analyzer that produces an :class:`AgentReport`
for the JARVIS BOSS. Agents never send orders and never talk to the broker
mutating API; they only read market data (via the read-only broker quote /
candle methods) and produce structured opinions.
"""

from jarvis.agents.base import Agent, AgentContext
from jarvis.agents.critic import CriticAgent
from jarvis.agents.learning import LearningAgent
from jarvis.agents.macro_news import MacroNewsAgent
from jarvis.agents.market_analyst import MarketAnalystAgent
from jarvis.agents.quant import QuantAgent
from jarvis.agents.regime import MarketRegimeAgent
from jarvis.agents.research import ResearchAgent
from jarvis.agents.risk import RiskAgent
from jarvis.agents.technical import TechnicalAnalystAgent

__all__ = [
    "Agent",
    "AgentContext",
    "CriticAgent",
    "LearningAgent",
    "MacroNewsAgent",
    "MarketAnalystAgent",
    "QuantAgent",
    "MarketRegimeAgent",
    "ResearchAgent",
    "RiskAgent",
    "TechnicalAnalystAgent",
]
