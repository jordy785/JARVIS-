"""MetaTrader 5 broker implementation.

Wraps the official ``MetaTrader5`` Python package. Because that package only
runs on Windows (with a MT5 terminal installed), this module imports it lazily
and degrades gracefully to :class:`DemoBroker` when unavailable.

Security: credentials come from :class:`Settings` and are passed to MT5 only at
connect time. They are never logged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from jarvis.brokers.base import AccountInfo, BrokerQuote, OrderResult, TradingBroker
from jarvis.core.enums import OrderSide, OrderType
from jarvis.core.logging import get_logger
from jarvis.core.models import MarketCandle, Position

_log = get_logger("brokers.mt5")

_TF_MAP = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


class MetaTrader5Broker(TradingBroker):
    """Real broker backed by the official ``MetaTrader5`` package."""

    name = "mt5"

    def __init__(self, login: int, password: str, server: str, path: str = "") -> None:
        self._login = login
        # password kept private, never logged
        self._password = password
        self._server = server
        self._path = path
        self._mt5: Any = None
        self._connected = False

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - env dependent
            _log.warning("MetaTrader5 package unavailable: %s", exc)
            return False
        self._mt5 = mt5
        kwargs: dict[str, Any] = {
            "login": self._login,
            "password": self._password,
            "server": self._server,
        }
        if self._path:
            kwargs["path"] = self._path
        try:
            authorized = mt5.initialize(**kwargs)
        except Exception as exc:  # pragma: no cover - env dependent
            _log.warning("MT5 initialize failed: %s", exc)
            return False
        if not authorized:
            err = mt5.last_error()
            _log.warning("MT5 authorize failed: %s", err)
            return False
        self._connected = True
        _log.info("MT5 connected login=%s server=%s", self._login, self._server)
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        if self._mt5 is not None:
            try:
                self._mt5.shutdown()
            except Exception:  # pragma: no cover
                pass
        self._connected = False

    def _check(self) -> Any | None:
        if not self._connected or self._mt5 is None:
            return None
        return self._mt5

    def get_account_info(self) -> AccountInfo | None:
        mt5 = self._check()
        if mt5 is None:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return AccountInfo(
            login=info.login,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            currency=info.currency,
            leverage=info.leverage,
        )

    def get_balance(self) -> float | None:
        info = self.get_account_info()
        return info.balance if info else None

    def get_market_price(self, symbol: str) -> BrokerQuote | None:
        mt5 = self._check()
        if mt5 is None:
            return None
        s = symbol.upper().replace("/", "")
        tick = mt5.symbol_info_tick(s)
        if tick is None:
            return None
        return BrokerQuote(
            symbol=s,
            bid=tick.bid,
            ask=tick.ask,
            spread=tick.ask - tick.bid,
            time=datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
        )

    def get_positions(self) -> list[Position]:
        mt5 = self._check()
        if mt5 is None:
            return []
        positions = mt5.positions_get() or []
        out: list[Position] = []
        for p in positions:
            side = OrderSide.BUY if p.type == 0 else OrderSide.SELL
            out.append(
                Position(
                    position_id=str(p.ticket),
                    ticket=p.ticket,
                    symbol=p.symbol,
                    side=side,
                    volume_lots=p.volume,
                    entry_price=p.price_open,
                    stop_loss=p.sl,
                    take_profit=p.tp,
                    opened_at=datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                    current_price=p.price_current,
                    unrealized_pnl=p.profit,
                    source="live",  # serialized as OrderSource via as_dict elsewhere
                )
            )
        return out

    def symbol_valid(self, symbol: str) -> bool:
        mt5 = self._check()
        if mt5 is None:
            return False
        info = mt5.symbol_info(symbol.upper().replace("/", ""))
        return info is not None

    def market_open(self) -> bool:
        # Simple weekday check; real session logic can be refined.
        return datetime.now(timezone.utc).weekday() < 5

    def get_candles(self, symbol: str, timeframe: str, count: int = 200) -> list[MarketCandle]:
        mt5 = self._check()
        if mt5 is None:
            return []
        tf_attr = _TF_MAP.get(timeframe, "TIMEFRAME_H1")
        tf = getattr(mt5, tf_attr, None)
        if tf is None:
            return []
        s = symbol.upper().replace("/", "")
        rates = mt5.copy_rates_from_pos(s, tf, 0, count) or []
        out: list[MarketCandle] = []
        for r in rates:
            out.append(
                MarketCandle(
                    symbol=s, timeframe=timeframe,
                    time=datetime.fromtimestamp(r["time"], tz=timezone.utc).isoformat(),
                    open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                    volume=r.get("tick_volume", r.get("volume", 0)),
                )
            )
        return out

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
        mt5 = self._check()
        if mt5 is None:
            return OrderResult(success=False, message="MT5 not connected")
        s = symbol.upper().replace("/", "")
        # ensure symbol visible
        if not mt5.symbol_select(s, True):
            return OrderResult(success=False, message=f"symbol_select failed for {s}")
        if order_type is OrderType.MARKET:
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": s,
                "volume": float(volume),
                "type": mt5.ORDER_TYPE_BUY if side is OrderSide.BUY else mt5.ORDER_TYPE_SELL,
                "price": price if price is not None else (
                    mt5.symbol_info_tick(s).ask if side is OrderSide.BUY else mt5.symbol_info_tick(s).bid
                ),
                "sl": float(stop_loss) if stop_loss else 0.0,
                "tp": float(take_profit) if take_profit else 0.0,
                "deviation": 20,
                "magic": 0,
                "comment": "JARVIS",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
        elif order_type is OrderType.LIMIT:
            req = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": s,
                "volume": float(volume),
                "type": mt5.ORDER_TYPE_BUY_LIMIT if side is OrderSide.BUY else mt5.ORDER_TYPE_SELL_LIMIT,
                "price": float(price) if price else 0.0,
                "sl": float(stop_loss) if stop_loss else 0.0,
                "tp": float(take_profit) if take_profit else 0.0,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
        else:  # STOP
            req = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": s,
                "volume": float(volume),
                "type": mt5.ORDER_TYPE_BUY_STOP if side is OrderSide.BUY else mt5.ORDER_TYPE_SELL_STOP,
                "price": float(price) if price else 0.0,
                "sl": float(stop_loss) if stop_loss else 0.0,
                "tp": float(take_profit) if take_profit else 0.0,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
        res = mt5.order_send(req)
        if res is None:
            return OrderResult(success=False, message=str(mt5.last_error()))
        ok = res.retcode == 10009  # TRADE_RETCODE_DONE
        return OrderResult(
            success=ok,
            ticket=getattr(res, "order", None),
            price=getattr(res, "price", None),
            message=f"retcode={res.retcode} comment={getattr(res, 'comment', '')}",
            raw={"retcode": res.retcode, "comment": getattr(res, "comment", "")},
        )

    def modify_order(
        self, ticket: int, stop_loss: float | None = None,
        take_profit: float | None = None, price: float | None = None,
    ) -> OrderResult:
        mt5 = self._check()
        if mt5 is None:
            return OrderResult(success=False, message="MT5 not connected")
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return OrderResult(success=False, message="position not found")
        pos = pos[0]
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": float(stop_loss) if stop_loss else pos.sl,
            "tp": float(take_profit) if take_profit else pos.tp,
        }
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == 10009
        return OrderResult(success=ok, ticket=ticket, message=str(res.retcode if res else "no result"))

    def cancel_order(self, ticket: int) -> OrderResult:
        mt5 = self._check()
        if mt5 is None:
            return OrderResult(success=False, message="MT5 not connected")
        order = mt5.orders_get(ticket=ticket)
        if not order:
            return OrderResult(success=False, message="order not found")
        o = order[0]
        opposite = (
            mt5.ORDER_TYPE_SELL if o.type in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP)
            else mt5.ORDER_TYPE_BUY
        )
        req = {
            "action": mt5.TRADE_ACTION_REMOVE if o.type in (
                mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
                mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP,
            ) else mt5.TRADE_ACTION_DEAL,
            "order": ticket,
            "symbol": o.symbol,
            "volume": o.volume_current,
            "type": opposite,
            "price": mt5.symbol_info_tick(o.symbol).bid if opposite == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(o.symbol).ask,
        }
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == 10009
        return OrderResult(success=ok, ticket=ticket, message=str(res.retcode if res else "no result"))

    def close_position(self, ticket: int, volume: float | None = None) -> OrderResult:
        mt5 = self._check()
        if mt5 is None:
            return OrderResult(success=False, message="MT5 not connected")
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return OrderResult(success=False, message="position not found")
        p = pos[0]
        is_buy = p.type == 0
        opposite_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "position": ticket,
            "volume": float(volume if volume else p.volume),
            "type": opposite_type,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": 0,
            "comment": "JARVIS close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == 10009
        return OrderResult(success=ok, ticket=ticket, price=getattr(res, "price", None) if res else None, message=str(res.retcode if res else "no result"))
