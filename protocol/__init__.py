"""L1 — Syntony protocol: domain-independent envelopes + conversation state machine.

This layer is pure data and pure functions. It knows nothing about Band, about LLMs,
or about any domain. Everything above it (engine, domains, UI) depends on these types;
this layer depends on nothing in the project.
"""

from .envelope import Envelope, Kind, Visibility
from .state_machine import TERMINAL, TRANSITIONS, State, is_allowed

__all__ = [
    "Envelope",
    "Kind",
    "Visibility",
    "State",
    "TRANSITIONS",
    "TERMINAL",
    "is_allowed",
]
