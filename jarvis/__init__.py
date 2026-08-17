"""JARVIS — AI Forex Trading Operating System.

A multi-agent forex trading intelligence system with real execution capability
that is strictly gated by explicit user orders. The system connects to
MetaTrader 5 for market data and order routing.

Fundamental invariant (enforced throughout the codebase):

    JARVIS MAY ANALYZE AND PREPARE A TRADE.
    JARVIS MAY BE CONNECTED TO THE REAL MARKET VIA METATRADER 5.
    JARVIS MAY EXECUTE A REAL TRADE.
    BUT JARVIS MAY ONLY EXECUTE A REAL TRADE ON EXPLICIT USER ORDER.

A market analysis, an opportunity alert, or a recommended trade proposal must
NEVER trigger a real (or paper) order. Only an explicitly recognized LIVE/PAPER
order command from the user, followed by an explicit confirmation, may result
in order submission to the broker.
"""

__version__ = "0.1.0"
