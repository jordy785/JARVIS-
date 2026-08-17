# JARVIS — AI Forex Trading Operating System

[![Deploy on Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render)](https://render.com/deploy)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit)](https://streamlit.io)
[![Tests](https://img.shields.io/badge/tests-84%20passing-brightgreen)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

A multi-agent **forex trading intelligence** system that connects to
**MetaTrader 5** for market data and order routing — with real execution
capability that is **strictly gated by explicit user orders**.

> **Fundamental invariant:** JARVIS may analyze and prepare a trade. JARVIS may
> be connected to the real market via MetaTrader 5. JARVIS may execute a real
> trade. **But JARVIS may only execute a real trade on explicit user order.**
>
> An analysis, an opportunity alert, or a recommended trade proposal must
> **never** trigger a real (or paper) order. Only an explicitly recognized
> order command from the user, followed by an explicit confirmation, may result
> in order submission to the broker.

This invariant is enforced structurally (agents physically cannot submit orders)
and verified by dedicated tests (see `tests/test_explicit_order_rule.py`).

---

## Déploiement en ligne (gratuit)

### Option A — Render (le plus simple, comme Vercel)

1. Va sur **[render.com](https://render.com)** et connecte-toi avec ton GitHub
2. Clique **« New + »** → **« Web Service »**
3. Connecte ton repo `jordy785/JARVIS-`
4. Render détecte automatiquement le `render.yaml` — clique **« Apply »**
5. En 2-3 minutes, ton app est en ligne à une URL publique du type :
   `https://jarvis-forex-os.onrender.com`

✅ L'app reste en ligne 24/7, se redéploie automatiquement à chaque push.

### Option B — Streamlit Cloud

1. Va sur **[share.streamlit.io](https://share.streamlit.io)**
2. Connecte-toi avec GitHub
3. **New app** → repo `jordy785/JARVIS-` → branch `main` → fichier `app.py`
4. Clique **« Deploy! »**

### Option C — En local (pour MetaTrader 5 réel)

```bash
pip install -e ".[dev]"
streamlit run app.py
```

Voir `INSTALL.md` pour le guide complet Windows.

> ⚠️ Sur le cloud, JARVIS tourne en mode PAPER (simulation). Pour trader en
> réel avec MetaTrader 5, installe-le sur ton PC Windows.

---

## Architecture

```
USER → CHAT → JARVIS BOSS
                  │
        ┌─────────┴──────────────────────────────────────┐
        │  MARKET ANALYST   QUANT AGENT                  │
        │  TECHNICAL ANALYST  MARKET REGIME AGENT        │
        │  MACRO/NEWS AGENT   RESEARCH AGENT             │
        │  RISK AGENT   CRITIC AGENT   LEARNING AGENT    │
        └────────────────────────────────────────────────┘
                  │
        JARVIS BOSS → FINAL ANALYSIS → USER
                                        │
                          EXPLICIT ORDER (user confirms)
                                        │
                          EXECUTION ENGINE  ←  only module allowed to submit
                                        │
                          METATRADER 5 API → REAL FOREX MARKET
```

Sub-agents **never** send orders. They produce structured `AgentReport`s for the
BOSS. The BOSS synthesizes a `DecisionPacket` + optional `TradeProposal`
(non-executed). The `ExecutionEngine` is the **single** authorized path to the
broker; it requires both an explicit user command (`OrderSource.USER_EXPLICIT`)
and an explicit confirmation before calling `broker.place_order`.

## Operating modes

| Mode | Indicator | Orders |
|------|-----------|--------|
| `ANALYSIS` | 🟢 ANALYSIS | None — analysis only |
| `PAPER` | 🟡 PAPER TRADING | Simulated only (no real money) |
| `LIVE` | 🔴 LIVE TRADING | Real via MT5 — **only if `LIVE_TRADING_ENABLED=true`**; still requires explicit user order |

Even in `LIVE`, **no execution without an explicit user order.**

## Sub-agents

- **Market Analyst** — trend, volatility, structure, volume, momentum.
- **Quant Agent** — statistics, probabilities, expectancy, drawdown, correlations (never presents probability as certainty).
- **Technical Analyst** — EMA/SMA/RSI/MACD/ATR/support/resistance/breakout across M15/H1/H4/D1.
- **Market Regime Agent** — trend up/down, range, high/low volatility, unusual.
- **Macro/News Agent** — economic calendar + geopolitical surveillance; evaluates event-risk (LOW/MODERATE/HIGH/UNKNOWN) per pair. **Prudence-only**: alerts on approaching events, never predicts price impact.
- **Research Agent** — proposes hypotheses (strategies/filters) without touching production.
- **Risk Agent** — independent gate: position size, exposure, stops, drawdown, volatility, concentration, daily limits, event risk. Can `REJECTED` and block execution even if the BOSS is favorable.
- **Critic Agent** — actively tries to refute the BOSS' emerging decision.
- **Learning Agent** — surfaces active model version + recent performance.

## Safety

- Secrets (`MT5_LOGIN/PASSWORD/SERVER`, `MACRO_NEWS_API_KEY`) come from `.env` only, are never hardcoded, and are **redacted** from logs by a logging filter.
- `LIVE_TRADING_ENABLED=false` by default.
- Runtime **kill-switch** (`TRADING_KILLSWITCH=true`, or chat command "kill-switch") blocks all orders.
- Pre-trade safety checks before every order: valid symbol, valid volume, sufficient balance, market open, broker limits, risk, exposure, imminent macro event, coherent order, explicit confirmation.
- Fast-confirmation mode (`FAST_CONFIRMATION=true`) auto-confirms **paper** orders only — never live.

## Learning & memory

- Structured SQLite memory: analyses, decisions, orders, positions, self-critic entries, past macro events & observed impact, backtest results, model versions.
- **Self-critic** journal after each trade (why proposed, what hypotheses were right/wrong, timing, risk, macro, overconfidence).
- **Model versioning**: train → validate → backtest → out-of-sample → paper → evaluation → promote. Versions V1, V2, ... with performance retained.

## Backtesting

Event-driven, no look-ahead bias (strategy sees only `candles[:i+1]`). Metrics:
win rate, profit factor, expectancy, max drawdown, Sharpe, avg win/loss,
consecutive wins/losses, return, volatility, #trades. Supports
train/validation/test split and walk-forward.

## Quick start

```bash
cp .env.example .env          # edit credentials / mode
pip install -e ".[dev]"
pytest -q                     # 84 tests, including the explicit-order rule
```

### Interface web (dashboard + chat) — recommandée

```bash
streamlit run app.py
```

Une page web s'ouvre (http://localhost:8501) avec :
- **Portfolio** (balance, equity, P&L, positions, exposition)
- **Agents** (opinions des 9 sous-agents + décision du BOSS + confiance + risque)
- **Calendrier macro** (événements à fort impact)
- **Graphique de prix** (chandeliers japonais interactifs, paire au choix)
- **Trades récents** (statut, source, P&L)
- **Chat intégré** où vous commandez JARVIS et il vous répond
- **Sidebar** : mode, sécurité, kill-switch, commandes rapides, aide

Vous tapez vos ordres directement dans le chat en bas de page :
`Analyse EUR/USD` → `Exécute le trade proposé` → `oui`.

### En ligne de commande

```bash
jarvis                        # REPL conversationnel interactif
jarvis --once "Analyse EUR/USD"   # une commande
jarvis --dashboard            # dashboard texte
```

### Example conversation

```
you > Analyse EUR/USD
JARVIS: ━━━ ANALYSE JARVIS ━━━
MARCHÉ          : EURUSD
...
DÉCISION PROPOSÉE : BUY
« Trade prêt. En attente de votre ordre. » — aucun ordre envoyé.

you > Exécute le trade proposé
JARVIS: 🔴 LIVE ORDER CONFIRMATION ...
⚠️ Confirmez-vous l'envoi de cet ordre réel ? (oui/non)

you > oui
JARVIS: ✅ Ordre envoyé (🟡 PAPER TRADING). Je surveille la position en temps réel.
```

## Project layout

```
jarvis/
├── core/           # config, enums, models, memory, indicators, logging
├── brokers/        # TradingBroker (abstract) + MetaTrader5 + DemoBroker + factory
├── execution/      # ExecutionEngine — ONLY module allowed to submit orders
├── agents/         # 9 sub-agents + base Agent / AgentContext (read-only)
├── engine/         # backtest, paper trading, position monitor
├── chat/           # NL command classifier + conversation handler
├── dashboard/      # portfolio / agents / macro / trades rendering
├── learning/       # self-critic + model versioning
├── web/            # Streamlit session state (app web)
├── cli.py          # interactive REPL + --once + --dashboard
└── app.py          # interface web Streamlit (dashboard + chat)
tests/              # 84 tests incl. analysis-never-orders guarantee
```

## Connecting a real MT5 account

1. Install the official `MetaTrader5` Python package on a Windows host with a
   MT5 terminal installed: `pip install "jarvis-trading[mt5]"`.
2. Set in `.env`: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `MT5_PATH` (path to
   `terminal64.exe` if needed).
3. Set `TRADING_MODE=LIVE` and `LIVE_TRADING_ENABLED=true`.
4. **Start with a demo MT5 account before any real account.**

When MT5 is unavailable (e.g. CI, Linux dev), the factory falls back to
`DemoBroker`, which provides synthetic market data and a paper portfolio — so the
full stack remains runnable and testable everywhere.

## Macro/News data source

The Macro/News agent has a pluggable `CalendarProvider`. With no provider
configured, it returns `UNKNOWN` event risk (prudence by default). A
Trading Economics provider hook is included (`MACRO_NEWS_API_KEY`); Forex
Factory or equivalent can be added by implementing the same callable.

## Tests

```
tests/test_explicit_order_rule.py   # CRITICAL: analysis never triggers orders
tests/test_classifier.py            # NL intent classification
tests/test_agents.py                # all 9 sub-agents + BOSS synthesis
tests/test_execution.py             # safety checks + gating
tests/test_backtest.py              # metrics + no look-ahead
tests/test_paper.py                 # paper trading (no real money)
tests/test_brokers.py               # demo broker + factory fallback
tests/test_memory.py                # memory store
tests/test_learning.py              # self-critic + model versioning
tests/test_security.py              # secrets never logged, LIVE disabled by default
tests/test_monitor.py               # position monitor is informational only
```

## License

MIT.
