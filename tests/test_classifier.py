"""Tests for the natural-language command classifier."""

import pytest

from jarvis.chat.classifier import Intent, classify, extract_symbol, extract_volume


@pytest.mark.parametrize("text,intent", [
    ("Analyse EUR/USD", Intent.ANALYSIS),
    ("Analyse GBP/JPY", Intent.ANALYSIS),
    ("Cherche les meilleures opportunites", Intent.SCAN_OPPORTUNITIES),
    ("Que penses-tu de GBP/USD ?", Intent.ANALYSIS),
    ("Y a-t-il une news importante aujourd'hui ?", Intent.ANALYSIS),
    ("Montre-moi les signaux actuels", Intent.ANALYSIS),
    ("Quel serait ton trade ?", Intent.ANALYSIS),
    ("Simule ce trade", Intent.SIMULATION),
    ("Fais un paper trade", Intent.SIMULATION),
    ("Achete EUR/USD maintenant", Intent.LIVE_ORDER),
    ("Exécute le trade proposé", Intent.LIVE_ORDER),
    ("Exécute la stratégie proposée", Intent.LIVE_ORDER),
    ("Ferme cette position", Intent.CLOSE_POSITION),
    ("Vends 50% de ma position", Intent.CLOSE_POSITION),
    ("oui", Intent.CONFIRM),
    ("non", Intent.CANCEL),
    ("annule", Intent.CANCEL),
    ("kill-switch", Intent.KILLSWITCH),
])
def test_classification(text, intent):
    cmd = classify(text)
    assert cmd.intent is intent, f"{text!r} -> {cmd.intent} (expected {intent})"


def test_analysis_intents_are_analysis_only():
    for t in ["Analyse EUR/USD", "Cherche une opportunite", "Quel serait ton trade ?"]:
        cmd = classify(t)
        assert cmd.is_analysis_only()


def test_live_order_requires_confirmation():
    assert classify("Achete EUR/USD maintenant").requires_user_confirmation()


def test_extract_symbol():
    assert extract_symbol("Analyse EUR/USD") == "EURUSD"
    assert extract_symbol("GBPJPY") == "GBPJPY"


def test_extract_volume():
    assert extract_volume("Achete 0.5 lots EUR/USD") == 0.5
    assert extract_volume("Analyse EUR/USD") is None
