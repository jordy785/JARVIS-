"""JARVIS conversation handler.

This is the bridge between the user's natural language and the system.
It enforces the **explicit-order rule**: an analysis/opportunity/info response
never results in an order. A LIVE_ORDER intent first prepares a pending order,
shows a LIVE ORDER CONFIRMATION block, and only when the user explicitly
confirms does it call ``ExecutionEngine.confirm_and_submit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.boss import JarvisBoss
from jarvis.chat.classifier import Intent, classify
from jarvis.core.enums import Mode, OrderSide, OrderSource, OrderStatus, OrderType
from jarvis.core.logging import get_logger
from jarvis.core.models import DecisionPacket, TradeProposal
from jarvis.execution.engine import ExecutionBlocked, ExecutionEngine

_log = get_logger("chat.handler")


@dataclass
class ChatResponse:
    text: str
    decision: DecisionPacket | None = None
    pending_order_id: str | None = None
    awaiting_confirmation: bool = False
    actions: list[str] = field(default_factory=list)
    mode_changed: bool = False

    def __str__(self) -> str:
        return self.text


class JarvisChat:
    """Conversational front-end for JARVIS."""

    DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "AUDUSD", "USDCAD")

    def __init__(
        self,
        boss: JarvisBoss,
        execution: ExecutionEngine,
        memory=None,
    ) -> None:
        self.boss = boss
        self.execution = execution
        self.memory = memory
        self._awaiting_confirmation: str | None = None

    @property
    def settings(self):
        return self.boss.settings

    # ------------------------------------------------------------------ #
    def handle(self, message: str, user: str = "user") -> ChatResponse:
        """Process one user message. Returns a structured chat response.

        This method is the SINGLE gateway from chat to actions. It guarantees:
        - analysis/info/scan intents never produce orders;
        - live/close intents first stage a pending order and require explicit
          confirmation before the broker is called.
        """
        if self._awaiting_confirmation is not None:
            return self._handle_confirmation(message, user)

        cmd = classify(message)

        if cmd.intent is Intent.KILLSWITCH:
            return self._killswitch()

        if cmd.intent is Intent.MODE_CHANGE:
            return self._change_mode(cmd.mode)

        if cmd.intent is Intent.ANALYSIS:
            return self._do_analysis(cmd)

        if cmd.intent is Intent.SCAN_OPPORTUNITIES:
            return self._scan_opportunities(cmd)

        if cmd.intent is Intent.INFO:
            return self._info(cmd)

        if cmd.intent is Intent.SIMULATION:
            return self._do_paper(cmd)

        if cmd.intent is Intent.LIVE_ORDER:
            return self._prepare_live_order(cmd, user)

        if cmd.intent is Intent.CLOSE_POSITION:
            return self._prepare_close(cmd, user)

        return ChatResponse(
            text=(
                "Je n'ai pas compris votre demande. "
                "Exemples : « Analyse EUR/USD », « Cherche les meilleures opportunités », "
                "« Exécute le trade proposé », « Ferme cette position »."
            )
        )

    # ------------------------------------------------------------------ #
    def _do_analysis(self, cmd) -> ChatResponse:
        sym = cmd.symbol or "EURUSD"
        if not self.boss.broker.symbol_valid(sym):
            return ChatResponse(text=f"Paire {sym} non disponible. Vérifiez le symbole.")
        self._announce(f"J'analyse {sym} avec mes différents agents...")
        decision = self.boss.analyze(sym)
        text = self._render_analysis(decision)
        return ChatResponse(text=text, decision=decision, actions=["analysis"])

    def _scan_opportunities(self, cmd) -> ChatResponse:
        symbols = [cmd.symbol] if cmd.symbol else list(self.DEFAULT_SYMBOLS)
        self._announce("Je scanne les opportunités sur les paires surveillées...")
        results = []
        for sym in symbols:
            if self.boss.broker.symbol_valid(sym):
                results.append(self.boss.analyze(sym))
        best = None
        for d in results:
            if d.decision.value in ("BUY", "SELL") and d.proposal and not d.proposal.is_rejected:
                if best is None or d.confidence > best.confidence:
                    best = d
        if best is None:
            return ChatResponse(
                text=(
                    "Aucune opportunité claire pour le moment. "
                    "Les agents ne sont pas suffisamment alignés ou le risque est élevé. "
                    "Je recommande d'attendre."
                ),
                actions=["scan"],
            )
        text = "Meilleure opportunité détectée (analyse uniquement — aucun ordre envoyé) :\n\n"
        text += self._render_analysis(best)
        text += "\n\n⚠️ Ceci est une proposition. Aucun ordre ne sera envoyé sans votre instruction explicite."
        return ChatResponse(text=text, decision=best, actions=["scan"])

    def _info(self, cmd) -> ChatResponse:
        if cmd.symbol:
            return ChatResponse(
                text=(
                    f"Vous mentionnez {cmd.symbol}. "
                    "Souhaitez-vous une analyse complète ? Dites « Analyse {cmd.symbol} ». "
                    "Aucun ordre ne sera envoyé sur simple mention."
                ),
                actions=["info"],
            )
        return ChatResponse(
            text="Que souhaitez-vous savoir ? Vous pouvez demander une analyse ou scanner des opportunités.",
            actions=["info"],
        )

    def _do_paper(self, cmd) -> ChatResponse:
        sym = cmd.symbol or "EURUSD"
        decision = self.boss.analyze(sym)
        if not decision.proposal or decision.proposal.is_rejected:
            return ChatResponse(
                text=(
                    "Simulation impossible : la proposition est rejetée ou absente. "
                    f"Raison : {decision.reasoning}"
                ),
                decision=decision,
                actions=["paper"],
            )
        try:
            order = self.execution.prepare_order(
                decision.proposal, user="paper", source=OrderSource.PAPER_SIMULATION
            )
        except ExecutionBlocked as exc:
            return ChatResponse(
                text=f"Simulation bloquée par sécurité : {exc}",
                decision=decision,
                actions=["paper_blocked"],
            )
        self._awaiting_confirmation = order.order_id
        text = "🟡 PAPER TRADING — ordre simulé préparé (aucun argent réel) :\n\n"
        text += self._render_order_confirmation(order, decision.proposal, paper=True)
        text += "\n\nConfirmez-vous l'envoi de cet ordre simulé ? (oui/non)"
        return ChatResponse(
            text=text,
            decision=decision,
            pending_order_id=order.order_id,
            awaiting_confirmation=True,
            actions=["paper_prepare"],
        )

    # ------------------------------------------------------------------ #
    def _prepare_live_order(self, cmd, user: str) -> ChatResponse:
        if not self.settings.mode.allows_order_submission():
            return ChatResponse(
                text=(
                    f"Mode actuel : {self.settings.mode.indicator}. "
                    "Les ordres ne sont pas autorisés dans ce mode. "
                    "Passez en mode PAPER ou LIVE pour exécuter."
                ),
                actions=["mode_block"],
            )
        if self.settings.mode is Mode.LIVE and not self.settings.is_live_allowed():
            return ChatResponse(
                text=(
                    "🔴 LIVE TRADING est désactivé dans la configuration (LIVE_TRADING_ENABLED=false). "
                    "Activez-le explicitement dans votre .env pour trader en réel."
                ),
                actions=["live_disabled"],
            )
        proposal = self._resolve_proposal(cmd)
        if proposal is None or proposal.is_rejected:
            return ChatResponse(
                text=(
                    "Aucune proposition de trade valable à exécuter. "
                    "Demandez d'abord une analyse (ex: « Analyse EUR/USD »), "
                    "puis « Exécute le trade proposé »."
                ),
                actions=["no_proposal"],
            )
        try:
            order = self.execution.prepare_order(
                proposal, user=user, source=OrderSource.USER_EXPLICIT
            )
        except ExecutionBlocked as exc:
            return ChatResponse(
                text=f"Ordre bloqué par les vérifications de sécurité : {exc}",
                actions=["live_blocked"],
            )
        self._awaiting_confirmation = order.order_id
        text = "🔴 LIVE ORDER CONFIRMATION — veuillez vérifier attentivement :\n\n"
        text += self._render_order_confirmation(order, proposal, paper=(self.settings.mode is Mode.PAPER))
        if self.settings.fast_confirmation and self.settings.mode is Mode.PAPER:
            return self._finalize_confirmation(confirmed=True, user=user)
        text += "\n\n⚠️ Confirmez-vous l'envoi de cet ordre réel ? (oui/non)"
        return ChatResponse(
            text=text,
            pending_order_id=order.order_id,
            awaiting_confirmation=True,
            actions=["live_prepare"],
        )

    def _resolve_proposal(self, cmd) -> TradeProposal | None:
        """Find the most recent non-rejected proposal, or build a fresh one.

        If the command mentions a symbol, target the latest decision for that
        symbol. Otherwise (e.g. "Exécute le trade proposé") fall back to the most
        recent decision overall. If nothing is found, run a fresh analysis for
        the mentioned symbol (or EURUSD as default).
        """
        sym = cmd.symbol
        try:
            from jarvis.core.memory import get_memory

            mem = self.memory or get_memory()
            for d in mem.recent_decisions(limit=10):
                # If a symbol was explicitly mentioned, require a match;
                # otherwise accept any recent decision.
                if sym and d.get("symbol", "").upper().replace("/", "") != sym.upper().replace("/", ""):
                    continue
                prop = d.get("proposal")
                if prop and prop.get("risk_level", "").upper() != "REJECTED":
                    return TradeProposal(
                        proposal_id=prop.get("proposal_id", ""),
                        symbol=prop.get("symbol", sym or ""),
                        side=OrderSide(prop["side"]),
                        order_type=OrderType(prop["order_type"]),
                        volume_lots=prop.get("volume_lots", 0.0),
                        entry_price=prop.get("entry_price"),
                        stop_loss=prop.get("stop_loss"),
                        take_profit=prop.get("take_profit"),
                        confidence=prop.get("confidence", 0.0),
                        risk_level=prop.get("risk_level", "UNKNOWN"),
                        reasoning=prop.get("reasoning", ""),
                        estimated_spread_cost=prop.get("estimated_spread_cost"),
                        estimated_risk_amount=prop.get("estimated_risk_amount"),
                    )
        except Exception:  # pragma: no cover
            pass
        # No matching proposal in memory: run a fresh analysis.
        target = sym or "EURUSD"
        if self.boss.broker.symbol_valid(target):
            decision = self.boss.analyze(target)
            return decision.proposal
        return None

    def _prepare_close(self, cmd, user: str) -> ChatResponse:
        positions = self.boss.broker.get_positions()
        if not positions:
            return ChatResponse(text="Aucune position ouverte à fermer.", actions=["no_positions"])
        target = positions
        if cmd.symbol:
            sym = cmd.symbol.upper().replace("/", "")
            target = [p for p in positions if p.symbol.upper() == sym]
        if not target:
            return ChatResponse(text="Aucune position correspondante à fermer.", actions=["no_match"])
        self._awaiting_confirmation = f"CLOSE:{cmd.fraction or 1.0}:{[p.position_id for p in target]}"
        text = "🔴 CONFIRMATION DE FERMETURE DE POSITION :\n\n"
        for p in target:
            text += (
                f"Paire : {p.symbol}\nDirection : {p.side.value}\nVolume : {p.volume_lots}\n"
                f"Prix entrée : {p.entry_price}\n"
                + (f"Prix actuel : {p.current_price}\n" if p.current_price else "")
                + (f"P&L non réalisé : {p.unrealized_pnl:.2f}\n" if p.unrealized_pnl is not None else "")
                + "\n"
            )
        frac = cmd.fraction
        text += (
            f"Fraction à fermer : {int(frac*100)}%\n" if frac else "Fermeture totale\n"
        )
        text += "\n⚠️ Confirmez-vous la fermeture de cette/ces position(s) ? (oui/non)"
        return ChatResponse(
            text=text,
            awaiting_confirmation=True,
            actions=["close_prepare"],
        )

    # ------------------------------------------------------------------ #
    def _handle_confirmation(self, message: str, user: str) -> ChatResponse:
        cmd = classify(message)
        if cmd.intent is Intent.CANCEL:
            return self._finalize_confirmation(confirmed=False, user=user)
        if cmd.intent is Intent.CONFIRM:
            return self._finalize_confirmation(confirmed=True, user=user)
        return ChatResponse(
            text=(
                "J'attends une confirmation explicite (oui/non). "
                "Votre message n'a pas été reconnu comme une confirmation — "
                "l'ordre n'a PAS été envoyé."
            ),
            awaiting_confirmation=True,
            actions=["ambiguous_no_submit"],
        )

    def _finalize_confirmation(self, confirmed: bool, user: str) -> ChatResponse:
        pending = self._awaiting_confirmation
        self._awaiting_confirmation = None
        if pending is None:
            return ChatResponse(text="Aucun ordre en attente.")

        if isinstance(pending, str) and pending.startswith("CLOSE:"):
            if not confirmed:
                return ChatResponse(text="Fermeture annulée. Aucune position touchée.", actions=["close_cancelled"])
            parts = pending.split(":", 2)
            frac = float(parts[1])
            ids = parts[2].split(",")
            results = []
            for pos in self.boss.broker.get_positions():
                if pos.position_id in ids:
                    vol = pos.volume_lots * frac if frac < 1.0 else None
                    ok = self.execution.close_position(pos.ticket or int(pos.position_id), volume=vol)
                    results.append((pos.symbol, ok))
            txt = "Fermeture exécutée :\n" + "\n".join(f"- {s}: {'OK' if ok else 'ÉCHEC'}" for s, ok in results)
            return ChatResponse(text=txt, actions=["close_done"])

        if not confirmed:
            self.execution.cancel_pending(pending)
            return ChatResponse(text="Ordre annulé. Aucun ordre envoyé au broker.", actions=["order_cancelled"])
        try:
            order = self.execution.confirm_and_submit(pending)
        except ExecutionBlocked as exc:
            return ChatResponse(text=f"Ordre bloqué à la soumission : {exc}", actions=["submit_blocked"])
        if order.status in (OrderStatus.FILLED, OrderStatus.SUBMITTED):
            mode_lbl = self.settings.mode.indicator
            return ChatResponse(
                text=(
                    f"✅ Ordre envoyé ({mode_lbl}).\n"
                    f"Order ID : {order.order_id}\n"
                    f"Ticket broker : {order.broker_ticket}\n"
                    f"Paire : {order.symbol} | Side : {order.side.value} | "
                    f"Volume : {order.volume_lots} | Prix : {order.price}\n"
                    f"SL : {order.stop_loss} | TP : {order.take_profit}\n"
                    f"Je surveille la position en temps réel."
                ),
                actions=["order_submitted"],
            )
        return ChatResponse(
            text=f"❌ Ordre rejeté : {order.rejection_reason}",
            actions=["order_rejected"],
        )

    # ------------------------------------------------------------------ #
    def _killswitch(self) -> ChatResponse:
        from jarvis.execution.engine import SafetyCheckResult

        def _blocked_checks(*a, **kw):
            return SafetyCheckResult(ok=False, reasons=["runtime kill-switch active"])

        self.execution.pre_trade_checks = _blocked_checks  # type: ignore[assignment]
        return ChatResponse(
            text=(
                "🛑 KILL-SWITCH activé. Aucun nouvel ordre (réel ou simulé) ne sera autorisé. "
                "Pour reprendre, redémarrez JARVIS avec TRADING_KILLSWITCH=false."
            ),
            actions=["killswitch"],
        )

    def _change_mode(self, mode: str | None) -> ChatResponse:
        if not mode:
            return ChatResponse(text="Mode actuel : " + self.settings.mode.indicator)
        return ChatResponse(
            text=(
                f"Pour passer en mode {mode}, modifiez TRADING_MODE={mode} dans votre .env "
                f"et redémarrez JARVIS. Mode actuel : {self.settings.mode.indicator}."
            ),
            mode_changed=False,
            actions=["mode_instruction"],
        )

    # ------------------------------------------------------------------ #
    # Rendering helpers
    # ------------------------------------------------------------------ #
    def _render_analysis(self, d: DecisionPacket) -> str:
        lines = []
        lines.append("━━━ ANALYSE JARVIS ━━━")
        lines.append(f"MARCHÉ          : {d.symbol}")
        lines.append(f"TENDANCE/RÉGIME : {d.regime.value}")
        for r in d.agent_reports:
            tag = r.opinion.value
            if r.warning:
                tag += " ⚠️"
            lines.append(f"{r.agent_name:<16}: {tag}  (conf {r.confidence:.0%})")
        lines.append("─" * 40)
        lines.append(f"DÉCISION PROPOSÉE : {d.decision.value}")
        lines.append(f"CONFIANCE         : {d.confidence:.0%}")
        lines.append(f"RISQUE            : {d.risk_level}")
        if d.event_risk:
            lines.append(f"RISQUE ÉVÉNEMENTIEL: {d.event_risk.value}")
        if d.proposal and not d.proposal.is_rejected:
            p = d.proposal
            lines.append("─" * 40)
            lines.append("PROPOSITION (non exécutée) :")
            lines.append(f"  Direction : {p.side.value}")
            lines.append(f"  Type      : {p.order_type.value}")
            lines.append(f"  Volume    : {p.volume_lots} lots")
            lines.append(f"  Entrée    : {p.entry_price}")
            lines.append(f"  Stop Loss : {p.stop_loss}")
            lines.append(f"  Take Profit : {p.take_profit}")
            if p.estimated_risk_amount is not None:
                lines.append(f"  Risque estimé : {p.estimated_risk_amount:.2f}")
            if p.estimated_spread_cost is not None:
                lines.append(f"  Coût spread estimé : {p.estimated_spread_cost:.4f}")
        lines.append("─" * 40)
        lines.append("RAISONNEMENT :")
        lines.append(d.reasoning)
        if d.decision.value in ("NO_TRADE", "WAIT"):
            lines.append("")
            lines.append("ℹ️ Je recommande de NE PAS trader maintenant.")
        lines.append("")
        lines.append("« Trade prêt. En attente de votre ordre. » — aucun ordre envoyé.")
        return "\n".join(lines)

    def _render_order_confirmation(self, order, proposal: TradeProposal, paper: bool = False) -> str:
        mode_lbl = "PAPER (simulé)" if paper else "LIVE (réel)"
        lines = [
            "LIVE ORDER CONFIRMATION" + (" [PAPER]" if paper else ""),
            f"Mode             : {mode_lbl}",
            f"Paire            : {order.symbol}",
            f"Direction        : {order.side.value}",
            f"Type             : {order.order_type.value}",
            f"Volume (lots)    : {order.volume_lots}",
            f"Prix estimé      : {order.price}",
            f"Stop Loss        : {order.stop_loss}",
            f"Take Profit      : {order.take_profit}",
            f"Risque estimé    : {proposal.estimated_risk_amount}",
            f"Frais/spread est.: {proposal.estimated_spread_cost}",
            f"Source           : {order.source.value}",
        ]
        return "\n".join(lines)

    def _announce(self, msg: str) -> None:
        _log.info("JARVIS: %s", msg)
