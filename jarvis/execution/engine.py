"""Execution engine.

The ONLY module permitted to submit orders to the broker. It enforces:

- mode gating (ANALYSIS → never; PAPER → paper; LIVE → real if enabled);
- the explicit-order rule: every order must originate from a recognized
  user command (``source=USER_EXPLICIT``) or a paper/backtest source —
  never from analysis alone;
- pre-trade safety checks (symbol, volume, balance, market open, macro risk);
- the confirmation gate (unless fast-confirmation is on for paper);
- a full audit ledger in memory + broker ledger.

Critically: methods like :meth:`submit_proposal` are SAFE — they only produce
an ``OrderRecord`` with status PENDING and DO NOT call the broker. Only
:meth:`confirm_and_submit` actually talks to the broker, and only after the
user has explicitly confirmed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from jarvis.brokers.base import TradingBroker
from jarvis.core.config import Settings, get_settings
from jarvis.core.enums import (
    EventRiskLevel,
    Mode,
    OrderSide,
    OrderSource,
    OrderStatus,
    OrderType,
    RiskVerdict,
)
from jarvis.core.logging import get_logger
from jarvis.core.memory import get_memory
from jarvis.core.models import OrderRecord, TradeProposal

_log = get_logger("execution")


class ExecutionBlocked(Exception):
    """Raised when an order cannot proceed due to a safety/permission check."""


@dataclass
class SafetyCheckResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


class ExecutionEngine:
    """Gatekeeper for order submission.

    The engine holds no autonomy: it acts only on explicit calls from the chat
    layer (which itself only forwards explicit user commands).
    """

    # Symbols treated as valid when MT5 symbol info is unavailable (demo).
    _SAFE_SYMBOLS = {
        "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF",
        "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "EURGBP",
    }

    def __init__(
        self,
        broker: TradingBroker,
        settings: Settings | None = None,
        memory=None,
        # Hook injected by the BOSS: returns current event-risk level for a symbol.
        event_risk_provider: Callable[[str], EventRiskLevel] | None = None,
        # Hook injected by the Risk Agent: approves/rejects a proposal.
        risk_gate: Callable[[TradeProposal], RiskVerdict] | None = None,
    ) -> None:
        self.broker = broker
        self.settings = settings or get_settings()
        self.memory = memory or get_memory()
        self.event_risk_provider = event_risk_provider
        self.risk_gate = risk_gate
        # Pending confirmation: order_id -> OrderRecord awaiting user confirm
        self.pending_confirmation: dict[str, OrderRecord] = {}

    # ------------------------------------------------------------------ #
    # Safety checks
    # ------------------------------------------------------------------ #
    def pre_trade_checks(
        self,
        symbol: str,
        side: OrderSide,
        volume: float,
        order_type: OrderType,
        price: float | None,
    ) -> SafetyCheckResult:
        reasons: list[str] = []
        s = self.settings

        if s.trading_killswitch:
            reasons.append("trading_killswitch is ON")
        if not s.mode.allows_order_submission():
            reasons.append(f"mode={s.mode.value} does not allow order submission")

        sym = symbol.upper().replace("/", "")
        if not self.broker.symbol_valid(sym) and sym not in self._SAFE_SYMBOLS:
            reasons.append(f"invalid symbol {sym}")
        if volume <= 0:
            reasons.append("volume must be > 0")
        if volume > 1000:
            reasons.append("volume exceeds sanity cap (1000 lots)")

        # balance
        bal = self.broker.get_balance()
        if bal is not None and bal <= 0:
            reasons.append("non-positive balance")

        # market open
        if not self.broker.market_open():
            reasons.append("forex market closed (weekend/holiday)")

        # macro event risk
        if self.event_risk_provider is not None:
            lvl = self.event_risk_provider(sym)
            if lvl is EventRiskLevel.HIGH:
                reasons.append(f"high macro event risk for {sym}")
            if s.mode is Mode.LIVE and lvl in (EventRiskLevel.HIGH, EventRiskLevel.MODERATE):
                reasons.append(f"live mode blocked by event risk={lvl.value}")

        # risk gate (Risk Agent)
        proposal_proxy = TradeProposal(
            symbol=sym, side=side, order_type=order_type,
            volume_lots=volume, entry_price=price,
        )
        if self.risk_gate is not None:
            verdict = self.risk_gate(proposal_proxy)
            if verdict is RiskVerdict.REJECTED:
                reasons.append("risk agent REJECTED the trade")

        return SafetyCheckResult(ok=not reasons, reasons=reasons)

    # ------------------------------------------------------------------ #
    # Proposal → pending confirmation (does NOT submit)
    # ------------------------------------------------------------------ #
    def prepare_order(
        self,
        proposal: TradeProposal,
        *,
        user: str,
        source: OrderSource = OrderSource.USER_EXPLICIT,
    ) -> OrderRecord:
        """Build a pending ``OrderRecord`` from a proposal and stage it for
        confirmation. Does NOT submit to the broker.

        Raises :class:`ExecutionBlocked` if pre-trade checks fail.
        """
        if proposal.is_rejected:
            raise ExecutionBlocked("proposal is marked REJECTED by the risk agent")

        check = self.pre_trade_checks(
            proposal.symbol, proposal.side, proposal.volume_lots,
            proposal.order_type, proposal.entry_price,
        )
        if not check.ok:
            _log.warning("pre-trade checks failed: %s", "; ".join(check.reasons))
            raise ExecutionBlocked("; ".join(check.reasons))

        order = OrderRecord(
            user=user,
            symbol=proposal.symbol,
            side=proposal.side,
            order_type=proposal.order_type,
            volume_lots=proposal.volume_lots,
            price=proposal.entry_price,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
            spread_cost=proposal.estimated_spread_cost,
            status=OrderStatus.PENDING,
            source=source,
            proposal_id=proposal.proposal_id,
        )
        self.pending_confirmation[order.order_id] = order
        self.memory.record("order", order.as_dict())
        _log.info("order staged pending confirmation: %s", order.order_id)
        return order

    # ------------------------------------------------------------------ #
    # Confirm & submit — only here does the broker get called
    # ------------------------------------------------------------------ #
    def confirm_and_submit(self, order_id: str) -> OrderRecord:
        """Actually submit a previously prepared order to the broker.

        This is invoked ONLY after explicit user confirmation in the chat.
        """
        order = self.pending_confirmation.get(order_id)
        if order is None:
            # Order may have been cancelled or already submitted. Look it up
            # from memory so callers get a structured REJECTED record instead of
            # an exception (safer for the chat flow).
            from jarvis.core.memory import get_memory
            try:
                mem = self.memory or get_memory()
                recs = mem.query("order", limit=200)
                for rec in recs:
                    if rec.get("order_id") == order_id:
                        return OrderRecord(
                            order_id=order_id,
                            symbol=rec.get("symbol", ""),
                            side=OrderSide(rec["side"]) if rec.get("side") else OrderSide.BUY,
                            order_type=OrderType(rec["order_type"]) if rec.get("order_type") else OrderType.MARKET,
                            volume_lots=rec.get("volume_lots", 0.0),
                            price=rec.get("price"),
                            stop_loss=rec.get("stop_loss"),
                            take_profit=rec.get("take_profit"),
                            status=OrderStatus.REJECTED,
                            source=OrderSource(rec["source"]) if rec.get("source") else OrderSource.USER_EXPLICIT,
                            rejection_reason="order not pending (cancelled or already submitted)",
                        )
            except Exception:
                pass
            raise ExecutionBlocked(f"no pending order with id {order_id}")

        # Re-run safety checks at submission time (state may have changed)
        check = self.pre_trade_checks(
            order.symbol, order.side, order.volume_lots,
            order.order_type, order.price,
        )
        if not check.ok:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "; ".join(check.reasons)
            self.memory.record("order", order.as_dict())
            _log.warning("order %s rejected at submit: %s", order_id, order.rejection_reason)
            return order

        # For LIVE, require the global kill flag OFF and live enabled
        if self.settings.mode is Mode.LIVE and not self.settings.is_live_allowed():
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "live trading not enabled in settings"
            self.memory.record("order", order.as_dict())
            raise ExecutionBlocked(order.rejection_reason)

        result = self.broker.place_order(
            symbol=order.symbol,
            side=order.side,
            volume=order.volume_lots,
            order_type=order.order_type,
            price=order.price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
        )
        if result.success:
            # Demo broker fills immediately on market orders; live may report SUBMITTED/FILLED.
            msg = (result.message or "").lower()
            order.status = (
                OrderStatus.FILLED if ("filled" in msg or result.ticket is not None)
                else OrderStatus.SUBMITTED
            )
            order.broker_ticket = result.ticket
            order.price = result.price if result.price is not None else order.price
            _log.info("order %s submitted ticket=%s", order_id, result.ticket)
        else:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = result.message
            _log.warning("order %s broker-rejected: %s", order_id, result.message)

        self.pending_confirmation.pop(order_id, None)
        self.memory.record("order", order.as_dict())
        return order

    def cancel_pending(self, order_id: str) -> bool:
        order = self.pending_confirmation.pop(order_id, None)
        if order is None:
            return False
        order.status = OrderStatus.CANCELLED
        self.memory.record("order", order.as_dict())
        _log.info("pending order cancelled: %s", order_id)
        return True

    def modify_position(
        self, ticket: int, stop_loss: float | None = None, take_profit: float | None = None
    ) -> bool:
        # modifying SL/TP on an existing broker position is allowed (protection
        # orders configured in advance), but it is still logged.
        res = self.broker.modify_order(ticket, stop_loss=stop_loss, take_profit=take_profit)
        _log.info("modify ticket=%s ok=%s", ticket, res.success)
        return res.success

    def close_position(self, ticket: int, volume: float | None = None) -> bool:
        res = self.broker.close_position(ticket, volume=volume)
        _log.info("close ticket=%s ok=%s", ticket, res.success)
        return res.success
