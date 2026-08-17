"""Natural-language command classifier.

Distinguishes ANALYSIS / SIMULATION / LIVE ORDER / INFO / CONFIRM commands.

The rule that protects the user's money lives here: only commands that match
the explicit LIVE ORDER patterns (in the user's language) are classified as
``LIVE_ORDER``. Anything ambiguous or analysis-flavored is classified as
``ANALYSIS`` (or ``INFO``), which can NEVER produce an order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from jarvis.core.logging import get_logger

_log = get_logger("chat.classifier")


class Intent(str, Enum):
    ANALYSIS = "ANALYSIS"
    SCAN_OPPORTUNITIES = "SCAN_OPPORTUNITIES"
    SIMULATION = "SIMULATION"
    LIVE_ORDER = "LIVE_ORDER"
    CLOSE_POSITION = "CLOSE_POSITION"
    MODIFY_POSITION = "MODIFY_POSITION"
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    INFO = "INFO"
    MODE_CHANGE = "MODE_CHANGE"
    KILLSWITCH = "KILLSWITCH"
    UNKNOWN = "UNKNOWN"


@dataclass
class ParsedCommand:
    intent: Intent
    raw: str
    symbol: str | None = None
    side: str | None = None  # BUY/SELL
    volume: float | None = None
    fraction: float | None = None  # for "close 50% of my position"
    confirm_word: str | None = None
    mode: str | None = None  # ANALYSIS/PAPER/LIVE
    extra: dict = None  # type: ignore[assignment]

    def is_analysis_only(self) -> bool:
        """True if this intent must NEVER trigger an order."""
        return self.intent in (
            Intent.ANALYSIS,
            Intent.SCAN_OPPORTUNITIES,
            Intent.INFO,
            Intent.UNKNOWN,
            Intent.MODE_CHANGE,
            Intent.KILLSWITCH,
        )

    def requires_user_confirmation(self) -> bool:
        return self.intent in (Intent.LIVE_ORDER, Intent.CLOSE_POSITION, Intent.MODIFY_POSITION)


_SYMBOL_RE = re.compile(r"\b([A-Z]{3})\s*[/\-]?\s*([A-Z]{3})\b")
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:lots?|lot|l)\b", re.IGNORECASE)
_FRACTION_RE = re.compile(r"(\d{1,3})\s*%\s*(?:de\s*ma\s*position|of\s*(?:my\s*)?position|of\s*it)", re.IGNORECASE)

# Explicit live-order trigger phrases (multi-language: FR/EN).
_LIVE_ORDER_PATTERNS = [
    r"\bex[ée]cute\b.*\b(trade|ordre|strat[ée]gie|deal|proposal|trade propos[ée]|proposition)\b",
    r"\bach[èe]te\b.*\bmaintenant\b",
    r"\bvends?\b.*\bmaintenant\b",
    r"\bach[èe]te\b.*\b(eurusd|gbpusd|usdjpy|gbpjpy|usdchf|audusd|usdcad|nzdusd|eurjpy|eurgbp)\b",
    r"\bvends?\b.*\b(eurusd|gbpusd|usdjpy|gbpjpy|usdchf|audusd|usdcad|nzdusd|eurjpy|eurgbp)\b",
    r"\bbuy\b.*\b(now|eurusd|gbpusd|usdjpy|gbpjpy)\b",
    r"\bsell\b.*\b(now|eurusd|gbpusd|usdjpy|gbpjpy)\b",
    r"\bplace\s+(?:a\s+)?(?:live\s+|real\s+)?order\b",
    r"\benvoie?\s+l['e ]ordre\b",
    r"\blive\s+order\b",
    r"\border\s+r[ée]el(le)?\b",
]
_LIVE_ORDER_RE = re.compile("|".join(_LIVE_ORDER_PATTERNS), re.IGNORECASE)

_CLOSE_PATTERNS = [
    r"\bferme\b.*\b(position|trade)\b",
    r"\bclose\b.*\b(position|trade)\b",
    r"\bcl[ôo]ture\b.*\bposition\b",
    r"\bvends?\s+(?:tout|50%|25%|100%|cette\s*position|\d+%\s*de\s*ma\s*position)\b",
    r"\bvends?\b.*\bposition\b",
    r"\bclose\s+(?:this\s+)?position\b",
]
_CLOSE_RE = re.compile("|".join(_CLOSE_PATTERNS), re.IGNORECASE)

_CONFIRM_PATTERNS = [
    r"^\s*(oui|yes|confirme?|confirm|go|ok|okay|ex[ée]cute|envoie?|valid[ée])\s*[.!?]?\s*$",
]
_CONFIRM_RE = re.compile("|".join(_CONFIRM_PATTERNS), re.IGNORECASE)

_CANCEL_PATTERNS = [r"^\s*(non|no|cancel|annule?|abandon|stop)\b"]
_CANCEL_RE = re.compile("|".join(_CANCEL_PATTERNS), re.IGNORECASE)

_ANALYSIS_PATTERNS = [
    r"\banalyse\b", r"\banalyze\b", r"\bque penses?-?tu\b", r"\bqu['e ]est-?ce que.*pense",
    r"\bsignaux\b", r"\bsignals\b", r"\bmontre-?moi\b", r"\bshow me\b",
    r"\bnews?\b", r"\bactualit[ée]s?\b", r"\b[ée]v[ée]nement\b",
    r"\bopportunit[ée]\b", r"\bopportunity\b", r"\bmeilleures?\b.*\bopportunit",
    r"\bpourquoi\b", r"\bwhy\b", r"\bquel serait ton trade\b",
]
_ANALYSIS_RE = re.compile("|".join(_ANALYSIS_PATTERNS), re.IGNORECASE)

_SIMULATION_PATTERNS = [
    r"\bsimule\b", r"\bsimulate\b", r"\bpaper\s*trade\b", r"\bbacktest\b",
]
_SIMULATION_RE = re.compile("|".join(_SIMULATION_PATTERNS), re.IGNORECASE)

_MODE_CHANGE_RE = re.compile(
    r"\b(mode\s*)?(analysis|paper|live|analyse|simulation)\b\s*(mode)?",
    re.IGNORECASE,
)
_KILLSWITCH_RE = re.compile(r"\b(kill[\s-]?switch|stop\s+everything|arr[êe]te\s+tout)\b", re.IGNORECASE)


def extract_symbol(text: str) -> str | None:
    m = _SYMBOL_RE.search(text)
    if not m:
        # try word match for known pairs
        for pair in ("EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURJPY", "EURGBP"):
            if pair in text.upper().replace("/", "").replace(" ", ""):
                return pair
        return None
    return (m.group(1) + m.group(2)).upper()


def extract_volume(text: str) -> float | None:
    m = _VOLUME_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def extract_fraction(text: str) -> float | None:
    m = _FRACTION_RE.search(text)
    if not m:
        return None
    try:
        v = float(m.group(1))
        if 0 < v < 100:
            return v / 100.0
        if v == 100:
            return 1.0
    except ValueError:
        return None
    return None


def extract_side(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b(ach[èe]te|buy|long|achat)\b", t):
        return "BUY"
    if re.search(r"\b(vends?|sell|short|vente)\b", t):
        return "SELL"
    return None


def classify(text: str) -> ParsedCommand:
    raw = text
    t = text.strip()

    if _KILLSWITCH_RE.search(t):
        return ParsedCommand(intent=Intent.KILLSWITCH, raw=raw)

    if _CANCEL_RE.search(t):
        return ParsedCommand(intent=Intent.CANCEL, raw=raw)

    if _CONFIRM_RE.search(t):
        return ParsedCommand(intent=Intent.CONFIRM, raw=raw, confirm_word=t)

    # Order matters: live-order and close must be checked BEFORE analysis,
    # because a sentence like "achète EUR/USD maintenant" is an explicit order
    # even though it contains the symbol.
    if _LIVE_ORDER_RE.search(t):
        # 'exécute la stratégie proposée' / 'achète EUR/USD maintenant' etc.
        # are explicit order triggers and must be classified as LIVE_ORDER.
        sym = extract_symbol(t)
        side = extract_side(t)
        vol = extract_volume(t)
        intent = Intent.LIVE_ORDER
        return ParsedCommand(
            intent=intent, raw=raw, symbol=sym, side=side, volume=vol, extra={}
        )

    if _CLOSE_RE.search(t):
        frac = extract_fraction(t)
        sym = extract_symbol(t)
        return ParsedCommand(
            intent=Intent.CLOSE_POSITION, raw=raw, symbol=sym, fraction=frac, extra={}
        )

    if _SIMULATION_RE.search(t):
        sym = extract_symbol(t)
        return ParsedCommand(intent=Intent.SIMULATION, raw=raw, symbol=sym, extra={})

    if _ANALYSIS_RE.search(t):
        sym = extract_symbol(t)
        # "cherche une opportunité" / "meilleures opportunités" → scan
        if re.search(r"\b(opportunit|meilleures?|scan)\b", t, re.IGNORECASE):
            return ParsedCommand(intent=Intent.SCAN_OPPORTUNITIES, raw=raw, symbol=sym, extra={})
        return ParsedCommand(intent=Intent.ANALYSIS, raw=raw, symbol=sym, extra={})

    # mode change?
    mm = _MODE_CHANGE_RE.search(t)
    if mm and re.search(r"\b(mode|passer|switch|change)\b", t, re.IGNORECASE):
        mode_token = mm.group(0).lower()
        mode = None
        if "paper" in mode_token:
            mode = "PAPER"
        elif "live" in mode_token:
            mode = "LIVE"
        elif "analysis" in mode_token or "analyse" in mode_token or "simulation" in mode_token:
            mode = "ANALYSIS"
        if mode:
            return ParsedCommand(intent=Intent.MODE_CHANGE, raw=raw, mode=mode, extra={})

    # symbol mention without action verb → info
    sym = extract_symbol(t)
    if sym:
        return ParsedCommand(intent=Intent.INFO, raw=raw, symbol=sym, extra={})

    return ParsedCommand(intent=Intent.UNKNOWN, raw=raw, extra={})
