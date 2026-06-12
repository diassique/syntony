"""L2 — agent definitions + the (lazy) adapter factory.

This module is domain-independent. It defines:

- ``Framework`` — which reasoning stack backs a role.
- ``RoleSpec`` — a *declarative* description of one agent: its Band identity, which
  side it represents, the framework + model that powers it, whether it streams its
  reasoning to the room, which L1 protocol states it acts in, and its system prompt.
  This is pure data — fully testable without any framework installed or any key.
- ``build_adapter`` — turns a ``RoleSpec`` into a concrete Band framework adapter.
  Adapters need their pip extra + a ``provider_key``, so imports happen lazily inside
  this function. The per-framework construction is wired incrementally (see TODOs);
  exact framework/Band APIs are confirmed in NOTES_BAND.md before use — never guessed.

The actual run loop is Band's: ``Agent.create(adapter=build_adapter(spec, key), ...).run()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from protocol import State


class Framework(str, Enum):
    LANGGRAPH = "langgraph"
    PYDANTIC_AI = "pydantic_ai"
    ANTHROPIC = "anthropic"
    LETTA = "letta"
    CREWAI = "crewai"
    GEMINI = "gemini"
    HUMAN = "human"          # no adapter — a human participant in the room


class Side(str, Enum):
    PROVIDER = "provider"
    PAYER = "payer"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class RoleSpec:
    """Declarative definition of one agent in a domain pack."""

    id: str                                  # logical/mention id, e.g. "provider.counsel"
    display_name: str                        # meaningful name (Band routes on it; never "Bot")
    side: Side
    framework: Framework
    acts_in: tuple[State, ...]               # which L1 states this role is active in
    system_prompt: str
    model: str | None = None                 # provider model slug (None for HUMAN)
    emit_reasoning: bool = True              # stream thoughts/tool-calls to the room (demo)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_human(self) -> bool:
        return self.framework is Framework.HUMAN


def build_adapter(spec: RoleSpec, provider_key: str):
    """Construct the Band framework adapter for ``spec``.

    Lazy imports: each branch needs the matching `band-sdk` extra installed. Wired
    incrementally as we install extras and obtain keys (Day 2+). HUMAN has no adapter.
    """
    if spec.is_human:
        raise ValueError(f"Role {spec.id!r} is a human participant; it has no adapter.")

    from band import AdapterFeatures, Emit

    emit = {Emit.EXECUTION, Emit.THOUGHTS} if spec.emit_reasoning else set()
    features = AdapterFeatures(emit=emit)

    if spec.framework is Framework.PYDANTIC_AI:
        # Preferred path: model-agnostic + AI/ML API base_url (see engine/llm.py).
        # TODO(day2): from band.adapters.pydantic_ai import PydanticAIAdapter
        #   return PydanticAIAdapter(model=..., system_prompt=spec.system_prompt, features=features)
        raise NotImplementedError("pydantic_ai adapter wiring lands once extras+keys are present")
    if spec.framework is Framework.LANGGRAPH:
        # TODO(day2): inject llm=ChatOpenAI(base_url=AIML, api_key=...) from engine/llm.py
        raise NotImplementedError("langgraph adapter wiring lands once extras+keys are present")
    if spec.framework in (Framework.LETTA, Framework.CREWAI):
        raise NotImplementedError("appeals adapter (Featherless open model) — Day 4")

    raise NotImplementedError(f"No adapter wiring yet for framework {spec.framework}")
