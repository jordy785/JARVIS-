"""Demo / fallback broker used when MT5 is unavailable.

Produces synthetic but realistic-looking market data so that the whole JARVIS
stack (agents, boss, paper trading, backtesting, tests) can run anywhere
without a Windows MT5 terminal. It NEVER sends real orders.

The DemoBroker keeps an in-memory portfolio for paper trading.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone

from jarvis.brokers.base import AccountInfo, BrokerQuote, OrderResult, TradingBroker
from jarvis.core.enums import OrderSide, OrderSource, OrderType
from jarvis.core.logging import get_logger
from jarvis.core.models import MarketCandle, Position

_log = get_logger("brokers.demo")

# Approximate typical forex base prices (for synthetic generation).
_BASE_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2700,
    "USDJPY": 150.20,
    "GBPJPY": 190.50,
    "USDCHF": 0.8800,
    "AUDUSD": 0.6600,
    "USDCAD": 1.3600,
    "NZDUSD": 0.6100,
    "EURJPY": 163.00,
    "EURGBP": 0.8550,
}

_TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440,
}


@dataclass
class _DemoPosition:
    ticket: int
    symbol: str
    side: OrderSide
    volume: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: str
    source: OrderSource = OrderSource.PAPER_SIMULATION


class DemoBroker(TradingBroker):
    """Self-contained broker simulator. No network, no real money."""

    name = "demo"

    def __init__(self, initial_balance: float = 100_000.0, currency: str = "USD") -> None:
        self._connected = False
        self._balance = float(initial_balance)
        self._currency = currency
        self._equity = self._balance
        self._positions: dict[int, _DemoPosition] = {}
        self._pending: dict[int, _DemoPosition] = {}
        self._next_ticket = 1000
        self._rng = random.Random(20240117)
        self._prices: dict[str, float] = {}
        for sym, px in _BASE_PRICES.items():
            self._prices[sym] = px
        # approximate pip size per symbol
        self._pip = {sym: (0.01 if "JPY" in sym else 0.0001) for sym in _BASE_PRICES}

    # ---- connection ----
    def connect(self) -> bool:
        self._connected = True
        _log.info("DemoBroker connected (no real market). balance=%.2f", self._balance)
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False

    # ---- account ----
    def get_account_info(self) -> AccountInfo | None:
        if not self._connected:
            return None
        return AccountInfo(
            login=0,
            server="DEMO",
            balance=self._balance,
            equity=self._equity,
            margin=0.0,
            free_margin=self._equity,
            currency=self._currency,
            leverage=100,
        )

    def get_balance(self) -> float | None:
        return self._balance if self._connected else None

    # ---- market data (synthetic but deterministic-ish) ----
    def _ensure_symbol(self, symbol: str) -> float:
        s = symbol.upper().replace("/", "")
        if s not in self._prices:
            # Default base price for unknown symbols
            self._prices[s] = 1.0000
            self._pip[s] = 0.0001
        self._drift(s)
        return self._prices[s]

    def _drift(self, symbol: str) -> None:
        px = self._prices[symbol]
        pip = self._pip[symbol]
        # small random walk
        change = self._rng.gauss(0, 1) * pip * 5
        self._prices[symbol] = max(pip, px + change)

    def get_market_price(self, symbol: str) -> BrokerQuote | None:
        if not self._connected:
            return None
        s = symbol.upper().replace("/", "")
        px = self._ensure_symbol(s)
        pip = self._pip[s]
        spread = pip * (1 + self._rng.random())
        now = datetime.now(timezone.utc).isoformat()
        return BrokerQuote(symbol=s, bid=px - spread / 2, ask=px + spread / 2, spread=spread, time=now)

    def symbol_valid(self, symbol: str) -> bool:
        s = symbol.upper().replace("/", "")
        return s in _BASE_PRICES or s in self._prices

    def market_open(self) -> bool:
        # Treat as always open for simulation purposes (forex weekend ignored)
        return True

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> list[MarketCandle]:
        if not self._connected:
            return []
        s = symbol.upper().replace("/", "")
        tf_minutes = _TIMEFRAME_MINUTES.get(timeframe, 60)
        px = self._ensure_symbol(s)
        pip = self._pip[s]
        candles: list[MarketCandle] = []
        now = datetime.now(timezone.utc)
        # generate a random-walk history
        price = px
        hist = [price]
        for _ in range(count):
            price = max(pip, price + self._rng.gauss(0, 1) * pip * 10)
            hist.append(price)
        hist = hist[-count:]
        for i, close in enumerate(hist):
            o = hist[i - 1] if i > 0 else close
            h = max(o, close) + abs(self._rng.gauss(0, 1)) * pip * 3
            low = min(o, close) - abs(self._rng.gauss(0, 1)) * pip * 3
            vol = max(1.0, self._rng.gauss(100, 30))
            t = datetime.fromtimestamp(
                now.timestamp() - (count - i) * tf_minutes * 60, tz=timezone.utc
            )
            candles.append(
                MarketCandle(
                    symbol=s, timeframe=timeframe,
                    time=t.isoformat(), open=o, high=h, low=low, close=close, volume=vol,
                )
            )
        return candles

    # ---- orders (paper only) ----
    def _ticket(self) -> int:
        self._next_ticket += 1
        return self._next_ticket

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        order_type: OrderType = OrderType.MARKET,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        if not self._connected:
            return OrderResult(success=False, message="broker not connected")
        s = symbol.upper().replace("/", "")
        if not self.symbol_valid(s):
            return OrderResult(success=False, message=f"invalid symbol {s}")
        quote = self.get_market_price(s)
        if quote is None:
            return OrderResult(success=False, message="no price")
        fill = quote.ask if side is OrderSide.BUY else quote.bid
        if order_type is OrderType.MARKET:
            ticket = self._ticket()
            pos = _DemoPosition(
                ticket=ticket, symbol=s, side=side, volume=volume,
                entry_price=fill, stop_loss=stop_loss, take_profit=take_profit,
                opened_at=datetime.now(timezone.utc).isoformat(),
            )
            self._positions[ticket] = pos
            self._recompute_equity()
            _log.info("DEMO order filled ticket=%s %s %s %.2f @ %.5f", ticket, s, side.value, volume, fill)
            return OrderResult(success=True, ticket=ticket, price=fill, message="filled (demo)")
        # LIMIT/STOP -> pending (simplified: accept as pending)
        ticket = self._ticket()
        return OrderResult(success=True, ticket=ticket, price=price, message="pending (demo)")

    def modify_order(
        self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None,
        price: float | None = None,
    ) -> OrderResult:
        if ticket in self._positions:
            p = self._positions[ticket]
            if stop_loss is not None:
                p.stop_loss = stop_loss
            if take_profit is not None:
                p.take_profit = take_profit
            return OrderResult(success=True, ticket=ticket, message="modified (demo)")
        return OrderResult(success=False, message="position not found")

    def cancel_order(self, ticket: int) -> OrderResult:
        if ticket in self._pending:
            self._pending.pop(ticket)
            return OrderResult(success=True, ticket=ticket, message="cancelled (demo)")
        return OrderResult(success=False, message="order not found")

    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        if ticket not in self._positions:
            return OrderResult(success=False, message="position not found")
        pos = self._positions[ticket]
        quote = self.get_market_price(pos.symbol)
        if quote is None:
            return OrderResult(success=False, message="no price")
        close_px = quote.bid if pos.side is OrderSide.BUY else quote.ask
        # realize PnL
        direction = 1.0 if pos.side is OrderSide.BUY else -1.0
        pnl = (close_px - pos.entry_price) * direction * pos.volume * self._lot_multiplier(pos.symbol)
        self._balance += pnl
        self._positions.pop(ticket)
        self._recompute_equity()
        _log.info("DEMO closed ticket=%s pnl=%.2f", ticket, pnl)
        return OrderResult(success=True, ticket=ticket, price=close_px, message=f"closed pnl={pnl:.2f}")

    def _lot_multiplier(self, symbol: str) -> float:
        # rough contract multiplier for PnL scaling in demo units
        return 100_000.0 if "JPY" not in symbol else 1000.0

    def get_positions(self) -> list[Position]:
        out: list[Position] = []
        for p in self._positions.values():
            quote = self.get_market_price(p.symbol)
            cur = quote.bid if quote else None
            direction = 1.0 if p.side is OrderSide.BUY else -1.0
            pnl = None
            if cur is not None:
                pnl = (cur - p.entry_price) * direction * p.volume * self._lot_multiplier(p.symbol)
            out.append(
                Position(
                    position_id=str(p.ticket), ticket=p.ticket, symbol=p.symbol,
                    side=p.side, volume_lots=p.volume, entry_price=p.entry_price,
                    stop_loss=p.stop_loss, take_profit=p.take_profit,
                    opened_at=p.opened_at, current_price=cur, unrealized_pnl=pnl,
                    source=p.source,
                )
            )
        return out

    def _recompute_equity(self) -> None:
        eq = self._balance
        for p in self._positions.values():
            quote = self.get_market_price(p.symbol)
            if quote is None:
                continue
            direction = 1.0 if p.side is OrderSide.BUY else -1.0
            cur = quote.bid if p.side is OrderSide.BUY else quote.ask
            eq += (cur - p.entry_price) * direction * p.volume * self._lot_multiplier(p.symbol)
        self._equity = eq
