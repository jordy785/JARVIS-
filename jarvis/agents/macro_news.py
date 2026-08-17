"""Macro / News agent — calendar & geopolitical surveillance.

ROLE (deliberately limited — agent of prudence, not prediction):
- monitor the economic calendar (rates, inflation, employment, GDP, CB speeches);
- detect high-impact events approaching (e.g. within next 24-48h);
- identify geopolitical tensions affecting currencies;
- evaluate an event-risk level (LOW/MODERATE/HIGH/UNKNOWN) per monitored pair;
- report the assessment to the BOSS and to the Risk Agent.

This agent NEVER attempts to predict the precise price impact of a news item.
Its job is to alert on the *presence* or *approach* of a risky event, not to
guess market direction afterwards.

Data source: pluggable provider. Built-in fallback returns a static small
calendar + UNKNOWN risk when no provider/API is configured, so the system is
safe-by-default (prudence) rather than overconfident.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion, EventRiskLevel
from jarvis.core.logging import get_logger
from jarvis.core.models import AgentReport, NewsEvent

_log = get_logger("agents.macro_news")

# Currency mapping for common forex symbols.
_SYMBOL_CURRENCIES = {
    "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
    "GBPJPY": ("GBP", "JPY"), "USDCHF": ("USD", "CHF"), "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"), "NZDUSD": ("NZD", "USD"), "EURJPY": ("EUR", "JPY"),
    "EURGBP": ("EUR", "GBP"),
}

# High-impact keywords in event titles.
_HIGH_IMPACT_KEYWORDS = (
    "interest rate", "rate decision", "nonfarm", "non-farm", "nfp",
    "gdp", "cpi", "inflation", "fomc", "ecb", "boe", "boj", "fed chair",
    "press conference", "monetary policy",
)


def symbol_currencies(symbol: str) -> tuple[str, str] | tuple[None, None]:
    s = symbol.upper().replace("/", "")
    return _SYMBOL_CURRENCIES.get(s, (None, None))


# Type alias for a calendar provider: returns a list of NewsEvent.
CalendarProvider = Callable[[datetime, timedelta], list[NewsEvent]]


class MacroNewsAgent(Agent):
    name = "MACRO/NEWS"

    def __init__(self, settings=None, calendar_provider: CalendarProvider | None = None) -> None:
        super().__init__(settings)
        self.calendar_provider = calendar_provider or self._default_provider

    # ---------------- default (safe) provider ----------------
    def _default_provider(self, now: datetime, horizon: timedelta) -> list[NewsEvent]:
        """Fallback calendar when no external API is configured.

        Returns an empty list (no known events) — which leads to UNKNOWN
        event-risk by default rather than a falsely low risk.
        """
        return []

    # ---------------- external provider hooks ----------------
    @staticmethod
    def trading_economics_provider(api_key: str) -> CalendarProvider:
        """Build a Trading Economics calendar provider (illustrative).

        Requires ``MACRO_NEWS_API_KEY``. Returns events for the next 48h.
        Network is only hit when explicitly called — never at import time.
        """
        if not api_key:
            _log.warning("Trading Economics requested but no API key set — using fallback")
            return MacroNewsAgent(settings=None)._default_provider  # type: ignore[misc]

        def provider(now: datetime, horizon: timedelta) -> list[NewsEvent]:
            try:
                import requests  # local import to avoid hard dep
            except ImportError:  # pragma: no cover
                _log.warning("requests not available for calendar")
                return []
            try:
                end = now + horizon
                url = "https://api.tradingeconomics.com/calendar"
                params = {"c": api_key, "format": "json", "start": now.isoformat(), "end": end.isoformat()}
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                out: list[NewsEvent] = []
                for item in data:
                    impact_str = str(item.get("importance", "")).lower()
                    if "high" in impact_str:
                        impact = EventRiskLevel.HIGH
                    elif "medium" in impact_str or "moderate" in impact_str:
                        impact = EventRiskLevel.MODERATE
                    else:
                        impact = EventRiskLevel.LOW
                    out.append(NewsEvent(
                        currency=str(item.get("country", "")),
                        impact=impact,
                        title=str(item.get("event", "")),
                        source="trading_economics",
                        forecast=str(item.get("forecast", "")),
                        previous=str(item.get("previous", "")),
                        time=str(item.get("date", now.isoformat())),
                    ))
                return out
            except Exception as exc:  # pragma: no cover - network
                _log.warning("calendar fetch failed: %s", exc)
                return []

        return provider

    # ---------------- analysis ----------------
    def _classify_event_impact(self, event: NewsEvent) -> EventRiskLevel:
        title = (event.title or "").lower()
        if any(kw in title for kw in _HIGH_IMPACT_KEYWORDS):
            return EventRiskLevel.HIGH
        return event.impact

    def evaluate_event_risk(
        self, symbol: str, now: datetime | None = None, horizon_hours: int = 48
    ) -> tuple[EventRiskLevel, list[NewsEvent]]:
        """Return (risk_level, relevant_events) for the symbol's currencies."""
        now = now or datetime.now(timezone.utc)
        horizon = timedelta(hours=horizon_hours)
        events = self.calendar_provider(now, horizon)
        cur_base, cur_quote = symbol_currencies(symbol)
        relevant: list[NewsEvent] = []
        risk = EventRiskLevel.LOW
        for ev in events:
            ev_currency = (ev.currency or "").upper()
            if cur_base and ev_currency == cur_base:
                relevant.append(ev)
            elif cur_quote and ev_currency == cur_quote:
                relevant.append(ev)
        # If no events known for the currencies, we cannot assert LOW risk → UNKNOWN
        if not relevant:
            return EventRiskLevel.UNKNOWN, []
        for ev in relevant:
            cls = self._classify_event_impact(ev)
            if cls is EventRiskLevel.HIGH:
                risk = EventRiskLevel.HIGH
                break
            if cls is EventRiskLevel.MODERATE and risk is EventRiskLevel.LOW:
                risk = EventRiskLevel.MODERATE
        return risk, relevant

    def analyze(self, context: AgentContext) -> AgentReport:
        risk, events = self.evaluate_event_risk(context.symbol)

        if risk is EventRiskLevel.HIGH:
            opinion = AgentOpinion.NO_TRADE
            recommendation = "Reduce exposure or wait for the announcement before a new position."
        elif risk is EventRiskLevel.MODERATE:
            opinion = AgentOpinion.WARNING
            recommendation = "Moderate event risk — size down or wait."
        elif risk is EventRiskLevel.UNKNOWN:
            opinion = AgentOpinion.WARNING
            recommendation = "Event risk UNKNOWN (no calendar data) — assume prudence."
        else:
            opinion = AgentOpinion.NEUTRAL
            recommendation = "No major events detected in the window."

        next_event = events[0] if events else None
        reasoning_parts = [
            f"event_risk={risk.value}",
            f"recommendation={recommendation}",
        ]
        if next_event:
            reasoning_parts.append(
                f"next_event={next_event.title!r} ({next_event.currency}) "
                f"impact={next_event.impact.value}"
            )
        else:
            reasoning_parts.append("no upcoming high-impact event matched the pair's currencies")

        # Record events into memory for later impact analysis
        from jarvis.core.memory import get_memory

        mem = None
        try:
            mem = get_memory()
        except Exception:  # pragma: no cover
            pass
        if mem is not None:
            for ev in events:
                mem.record("macro_event", ev.as_dict())

        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=0.7 if risk in (EventRiskLevel.HIGH, EventRiskLevel.MODERATE) else 0.4,
            reasoning=" | ".join(reasoning_parts),
            metrics={
                "event_risk": risk.value,
                "recommendation": recommendation,
                "next_event": next_event.as_dict() if next_event else None,
                "events_count": len(events),
            },
            event_risk=risk,
            warning=(risk in (EventRiskLevel.HIGH, EventRiskLevel.UNKNOWN)),
        )
