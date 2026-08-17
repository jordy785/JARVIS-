"""JARVIS — Interface web (dashboard + chat).

Lancez avec :
    streamlit run app.py

Une page web locale s'ouvre avec :
- le mode actuel et les sécurités (sidebar)
- le dashboard portfolio
- les opinions des agents + décision du BOSS
- le calendrier macro
- l'historique des trades
- un graphique de prix
- un chat où vous commandez JARVIS et il vous répond

Règle fondamentale préservée : aucune analyse / opportunité / news ne déclenche
un ordre. Seul un ordre explicite + confirmation envoie au broker.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="JARVIS — AI Forex Trading OS",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from jarvis.web.session import ChatMessage, get_chat_history, get_stack  # noqa: E402

# --------------------------------------------------------------------------- #
# CSS pour un rendu plus pro
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
    .big-title { font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px; }
    .mode-badge { font-size: 1.1rem; font-weight: 700; padding: 4px 12px; border-radius: 8px; }
    .agent-row { padding: 2px 0; }
    .jarvis-bubble {
        background-color: #1e293b; color: #f1f5f9; padding: 12px 16px;
        border-radius: 12px; margin: 6px 0; border-left: 4px solid #6366f1;
    }
    .user-bubble {
        background-color: #312e81; color: #e0e7ff; padding: 12px 16px;
        border-radius: 12px; margin: 6px 0; border-left: 4px solid #a78bfa;
        text-align: right;
    }
    .warning-box {
        background-color: #422006; color: #fde68a; padding: 10px 14px;
        border-radius: 8px; border-left: 4px solid #f59e0b; margin: 8px 0;
    }
    .metric-card {
        background-color: #0f172a; padding: 14px; border-radius: 10px;
        border: 1px solid #1e293b;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def agent_color(opinion: str) -> str:
    o = opinion.upper()
    if o in ("BUY", "APPROVED"):
        return "🟢"
    if o in ("SELL", "REJECTED", "NO_TRADE"):
        return "🔴"
    if o in ("WARNING",):
        return "🟡"
    return "⚪"


def mode_emoji(mode_value: str) -> str:
    return {"ANALYSIS": "🟢", "PAPER": "🟡", "LIVE": "🔴"}.get(mode_value, "⚪")


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
settings, broker, boss, execution, chat, memory = get_stack()

col1, col2, col3 = st.columns([6, 2, 2])
with col1:
    st.markdown(
        '<div class="big-title">🤖 JARVIS — AI Forex Trading Operating System</div>',
        unsafe_allow_html=True,
    )
    st.caption("Multi-agent forex intelligence • MetaTrader 5 • Exécution contrôlée par l'utilisateur")
with col2:
    st.markdown(
        f'<div class="mode-badge">Mode: {mode_emoji(settings.mode.value)} {settings.mode.value}</div>',
        unsafe_allow_html=True,
    )
with col3:
    st.metric("Broker", broker.name)
    st.caption(f"Live activé: {'oui' if settings.is_live_allowed() else 'non'}")

st.divider()

# --------------------------------------------------------------------------- #
# Sidebar — sécurité + commandes rapides
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Configuration")
    st.write(f"**Mode** : {settings.mode.indicator}")
    st.write(f"**Broker** : `{broker.name}`")
    st.write(f"**LIVE activé** : {'✅' if settings.is_live_allowed() else '❌'}")
    st.write(f"**Kill-switch** : {'🛑 ON' if settings.trading_killswitch else '✅ OFF'}")

    st.divider()
    st.subheader("⚡ Commandes rapides")
    quick = st.text_input("Commande", placeholder="Ex: Analyse EUR/USD", key="quick_cmd_input")
    if st.button("Envoyer", type="primary", use_container_width=True):
        if quick.strip():
            st.session_state["pending_input"] = quick.strip()

    st.divider()
    st.subheader("🛟 Aide")
    st.markdown(
        """
        **Analyse** : « Analyse EUR/USD », « Que penses-tu de GBP/USD ? »

        **Opportunités** : « Cherche les meilleures opportunités »

        **Simulation** : « Simule ce trade », « Fais un paper trade »

        **Ordre réel** : « Exécute le trade proposé » puis confirmez

        **Position** : « Ferme cette position », « Vends 50% de ma position »

        **Sécurité** : « kill-switch »
        """
    )
    st.divider()
    st.caption("⚠️ JARVIS n'exécute JAMAIS un ordre réel sans votre instruction explicite.")

# --------------------------------------------------------------------------- #
# Ligne du dessus : Portfolio | Agents | Macro
# --------------------------------------------------------------------------- #
pcol, acol, mcol = st.columns([1, 1.2, 1])

# ---- Portfolio ----
with pcol:
    st.subheader("💼 Portfolio")
    info = broker.get_account_info()
    positions = broker.get_positions()
    if info is not None:
        pnl = info.equity - info.balance
        pnl_pct = (pnl / info.balance * 100) if info.balance else 0.0
        c1, c2 = st.columns(2)
        c1.metric("Balance", f"{info.balance:,.0f} {info.currency}")
        c2.metric("Equity", f"{info.equity:,.0f} {info.currency}")
        c3, c4 = st.columns(2)
        c3.metric("P&L", f"{pnl:+,.0f}")
        c4.metric("P&L %", f"{pnl_pct:+.2f}%")
        c5, c6 = st.columns(2)
        c5.metric("Positions", len(positions))
        exposure = sum(abs(p.volume_lots) for p in positions)
        c6.metric("Exposition", f"{exposure:.2f} lots")
    else:
        st.warning("Broker non connecté")

# ---- Agents (dernière décision) ----
with acol:
    st.subheader("🧠 Agents")
    decisions = memory.recent_decisions(limit=1)
    if decisions:
        d = decisions[0]
        st.caption(f"Dernière analyse : {d.get('symbol','?')} • {d.get('timestamp','')[:19]}")
        for r in d.get("agent_reports", []):
            op = r.get("opinion", "?")
            warn = " ⚠️" if r.get("warning") else ""
            st.markdown(
                f"<div class='agent-row'>{agent_color(op)} "
                f"<b>{r.get('agent_name','?')}</b> : "
                f"<code>{op}</code>{warn} "
                f"<small>(conf {r.get('confidence',0):.0%})</small></div>",
                unsafe_allow_html=True,
            )
        st.divider()
        dec = d.get("decision", "?")
        st.markdown(
            f"### {agent_color(dec)} BOSS : **{dec}** "
            f"(conf {d.get('confidence',0):.0%}) • Risque: `{d.get('risk_level','?')}`"
        )
        er = d.get("event_risk", "UNKNOWN")
        st.caption(f"Risque événementiel : {er}")
    else:
        st.info("Aucune analyse récente. Demandez : « Analyse EUR/USD »")

# ---- Calendrier macro ----
with mcol:
    st.subheader("📅 Calendrier macro")
    events = memory.macro_events(limit=8)
    if events:
        for e in events:
            impact = e.get("impact", "UNKNOWN")
            color = {"HIGH": "🔴", "MODERATE": "🟡", "LOW": "🟢"}.get(impact, "⚪")
            st.markdown(
                f"{color} **{e.get('currency','?')}** • {e.get('title','?')[:50]}"
            )
            st.caption(f"impact: {impact}")
    else:
        st.info("Aucun événement macro enregistré.")

st.divider()

# --------------------------------------------------------------------------- #
# Deuxième ligne : graphique de prix | trades | JARVIS status
# --------------------------------------------------------------------------- #
gcol, tcol = st.columns([1.3, 1])

with gcol:
    st.subheader("📈 Prix du marché")
    sym_choice = st.selectbox(
        "Paire", ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "AUDUSD", "USDCAD"],
        index=0, key="chart_symbol",
    )
    try:
        candles = broker.get_candles(sym_choice, "H1", 100)
        if candles:
            import plotly.graph_objects as go

            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=[c.time for c in candles],
                        open=[c.open for c in candles],
                        high=[c.high for c in candles],
                        low=[c.low for c in candles],
                        close=[c.close for c in candles],
                        name=sym_choice,
                    )
                ]
            )
            fig.update_layout(
                height=320, xaxis_rangeslider_visible=False,
                template="plotly_dark", margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Pas de données de prix")
    except Exception as exc:
        st.error(f"Erreur graphique: {exc}")

with tcol:
    st.subheader("📋 Trades récents")
    orders = memory.recent_orders(limit=10)
    if orders:
        for o in orders:
            status = o.get("status", "?")
            emoji = {"FILLED": "✅", "SUBMITTED": "📨", "REJECTED": "❌",
                     "CANCELLED": "🚫", "PENDING": "⏳"}.get(status, "❔")
            st.markdown(
                f"{emoji} **{o.get('symbol','?')}** {o.get('side','?')} "
                f"{o.get('volume_lots',0)} lots • `{status}`"
            )
            st.caption(f"src: {o.get('source','?')} • {o.get('timestamp','')[:19]}")
    else:
        st.info("Aucun ordre enregistré.")

st.divider()

# --------------------------------------------------------------------------- #
# Positions ouvertes (si elles existent)
# --------------------------------------------------------------------------- #
if positions:
    st.subheader("📊 Positions ouvertes")
    pos_cols = st.columns([1, 1, 1, 1, 1, 1])
    headers = ["Paire", "Direction", "Volume", "Entrée", "Actuel", "P&L"]
    for c, h in zip(pos_cols, headers, strict=False):
        c.markdown(f"**{h}**")
    for p in positions:
        cols = st.columns([1, 1, 1, 1, 1, 1])
        cols[0].write(p.symbol)
        cols[1].write(p.side.value)
        cols[2].write(f"{p.volume_lots}")
        cols[3].write(f"{p.entry_price:.5f}")
        cols[4].write(f"{p.current_price:.5f}" if p.current_price else "—")
        pnl = p.unrealized_pnl
        cols[5].write(f"{pnl:+.2f}" if pnl is not None else "—")
    st.divider()

# --------------------------------------------------------------------------- #
# CHAT — la pièce maîtresse
# --------------------------------------------------------------------------- #
st.subheader("💬 Discutez avec JARVIS")

# Rendu de l'historique
history = get_chat_history()
chat_container = st.container()
with chat_container:
    for msg in history:
        if msg.role == "user":
            st.markdown(
                f'<div class="user-bubble"><b>Vous</b><br>{msg.text}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="jarvis-bubble"><b>JARVIS</b>{msg.text}</div>',
                unsafe_allow_html=True,
            )

# Zone de saisie
st.divider()
input_col, btn_col = st.columns([5, 1])
with input_col:
    user_input = st.text_input(
        "Votre message à JARVIS",
        placeholder="Ex: Analyse EUR/USD — ou — Exécute le trade proposé",
        key="chat_input",
        label_visibility="collapsed",
    )
with btn_col:
    send = st.button("Envoyer ▶", type="primary", use_container_width=True)

# Traitement d'une commande (soit via le bouton, soit via la sidebar quick cmd)
to_send = None
if send and user_input.strip():
    to_send = user_input.strip()
elif "pending_input" in st.session_state and st.session_state["pending_input"]:
    to_send = st.session_state["pending_input"]
    st.session_state["pending_input"] = ""

if to_send:
    history.append(ChatMessage(role="user", text=to_send))
    with st.spinner("JARVIS réfléchit…"):
        try:
            resp = chat.handle(to_send)
        except Exception as exc:
            resp = type("R", (), {"text": f"Erreur interne: {exc}", "actions": [], "decision": None})()
    summary = None
    if getattr(resp, "decision", None) is not None:
        d = resp.decision
        summary = (
            f"Décision: {d.decision.value} (conf {d.confidence:.0%}) • "
            f"Risque: {d.risk_level} • Événementiel: {d.event_risk.value}"
        )
    history.append(
        ChatMessage(
            role="jarvis",
            text=resp.text,
            actions=list(getattr(resp, "actions", [])),
            decision_summary=summary,
        )
    )
    # Si en attente de confirmation, on l'indique clairement
    if getattr(resp, "awaiting_confirmation", False):
        history.append(
            ChatMessage(
                role="jarvis",
                text=(
                    "⏳ J'attends votre confirmation. Répondez **oui** pour envoyer "
                    "l'ordre, ou **non** pour annuler."
                ),
            )
        )
    st.rerun()
