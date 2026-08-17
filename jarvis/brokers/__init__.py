"""Broker abstraction layer.

The :class:`TradingBroker` abstract interface is the single contract between
JARVIS and any trading venue. The initial implementation targets MetaTrader 5
via the official ``MetaTrader5`` Python package, with a ``DemoBroker`` fallback
for environments where MT5 is unavailable (CI, tests, dev machines).
"""

from jarvis.brokers.base import TradingBroker
from jarvis.brokers.demo import DemoBroker
from jarvis.brokers.factory import build_broker

__all__ = ["TradingBroker", "DemoBroker", "build_broker"]
