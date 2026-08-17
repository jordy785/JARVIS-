"""Conversational interface layer.

Translates user natural-language messages into intents, dispatches to the
appropriate handler (analysis, simulation, live order with confirmation),
and renders JARVIS responses. Enforces the explicit-order rule end-to-end.
"""

from jarvis.chat.classifier import Intent, ParsedCommand, classify

__all__ = ["Intent", "ParsedCommand", "classify"]
