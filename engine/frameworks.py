"""L2 — real agent-framework execution for a role's turn.

The heterogeneity is genuine: a role's reasoning is produced by an actual framework, configured
from the SAME ``LLMConfig`` the gateway path uses (one source of truth) — model, ``base_url``,
key env and temperature flow through. (``reasoning_effort`` is intentionally left to the gateway
path: enabling Anthropic "thinking" conflicts with the frameworks' forced structured output.)

- **Pydantic AI** — a typed ``Agent`` (``output_type``) for the typed/reasoning roles.
- **LangGraph** — a one-node ``StateGraph`` for the stateful/pipeline roles.

Both return a structured ``{message, reasoning}``. Imports are lazy so the module stays
import-safe without the extras, and each call is **best-effort**: the caller
(``runner.llm_narrator``) falls back to the gateway or deterministic facts on any failure.
APIs verified live (``spikes/08``).
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from pydantic import BaseModel

from engine.llm import LLMConfig


class _Turn(BaseModel):
    message: str
    reasoning: str


def _key(cfg: LLMConfig) -> str:
    key = os.environ.get(cfg.api_key_env)
    if not key:
        raise RuntimeError(f"{cfg.api_key_env} not set — needed for framework execution")
    return key


def _clean(msg: str) -> str:
    """Drop a leading "@role:" addressing prefix the model may add."""
    return re.sub(r"^@[\w.]+:\s*", "", msg.strip())


def pydantic_ai_turn(*, cfg: LLMConfig, system_prompt: str, user: str, max_tokens: int = 400) -> dict[str, Any]:
    """Produce a turn via a real Pydantic AI Agent, configured from ``cfg`` (AI/ML provider)."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    chat = OpenAIChatModel(cfg.model, provider=OpenAIProvider(base_url=cfg.base_url, api_key=_key(cfg)))
    settings: dict[str, Any] = {"max_tokens": max_tokens}
    if cfg.temperature is not None:
        settings["temperature"] = cfg.temperature
    # NB: reasoning_effort is deliberately NOT set here — it enables Anthropic "thinking", which the
    # provider rejects together with the forced tool-call structured output (output_type). Deep
    # reasoning isn't needed to phrase already-decided facts; reasoning_effort lives on the gateway path.
    agent = Agent(chat, output_type=_Turn, system_prompt=system_prompt, model_settings=settings)
    out = agent.run_sync(user).output
    return {"message": _clean(out.message), "reasoning": out.reasoning}


def langgraph_turn(*, cfg: LLMConfig, system_prompt: str, user: str, max_tokens: int = 400) -> dict[str, Any]:
    """Produce a turn via a real LangGraph StateGraph (ChatOpenAI from ``cfg``). Parses defensively
    so it's reliable across models incl. the cheap tier — the graph genuinely executes."""
    from typing import TypedDict

    from langchain_openai import ChatOpenAI
    from langgraph.graph import END, START, StateGraph

    from engine.llm import loads_json

    kw: dict[str, Any] = {"model": cfg.model, "base_url": cfg.base_url, "api_key": _key(cfg), "max_tokens": max_tokens}
    if cfg.temperature is not None:
        kw["temperature"] = cfg.temperature
    # reasoning_effort omitted (see pydantic_ai_turn) — it stays on the gateway path.
    llm = ChatOpenAI(**kw)
    instruction = (user + '\n\nReturn ONLY a JSON object with two string fields: "message" '
                   '(1–2 sentences, no PHI) and "reasoning" (one sentence).')

    class S(TypedDict):
        out: dict

    def reason(_state: S) -> dict:
        resp = llm.invoke([("system", system_prompt), ("user", instruction)])
        content = getattr(resp, "content", "") or ""
        if isinstance(content, list):  # some providers return content parts
            content = " ".join(str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in content)
        d = loads_json(content)
        if not d.get("message"):
            raise ValueError("LangGraph turn produced no message")
        return {"out": {"message": _clean(str(d["message"])), "reasoning": str(d.get("reasoning") or d["message"])}}

    graph = StateGraph(S)
    graph.add_node("reason", reason)
    graph.add_edge(START, "reason")
    graph.add_edge("reason", END)
    return graph.compile().invoke({})["out"]


#: Framework enum value (``RoleSpec.framework.value``) → its turn function, or None (use the gateway).
_TURN_FNS: dict[str, Callable[..., dict[str, Any]]] = {
    "pydantic_ai": pydantic_ai_turn,
    "langgraph": langgraph_turn,
}


def turn_fn(framework_value: str) -> Callable[..., dict[str, Any]] | None:
    """Return the framework's turn function for a ``Framework`` value, or None if not wired."""
    return _TURN_FNS.get(framework_value)
