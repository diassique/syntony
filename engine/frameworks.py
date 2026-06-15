"""L2 — real agent-framework execution for a role's turn.

The heterogeneity is genuine: a role's reasoning is produced by an actual framework, with the
model served through the AI/ML gateway (one key — the partner prize stays intact):

- **Pydantic AI** — a typed ``Agent`` (``output_type``) for the typed/reasoning roles.
- **LangGraph** — a one-node ``StateGraph`` for the stateful/pipeline roles.

Both return a structured ``{message, reasoning}``. The exact installed APIs were verified live
(``spikes/08``). Imports are lazy so this module stays import-safe without the extras, and each
call is **best-effort**: the caller (``runner.llm_narrator``) falls back to the gateway or the
deterministic facts on any failure, so a framework hiccup never breaks a negotiation.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from pydantic import BaseModel

from engine.llm import AIML_BASE_URL


class _Turn(BaseModel):
    message: str
    reasoning: str


def _key() -> str:
    key = os.environ.get("AIML_API_KEY")
    if not key:
        raise RuntimeError("AIML_API_KEY not set — needed for framework execution")
    return key


def _clean(msg: str) -> str:
    """Drop a leading "@role:" addressing prefix the model may add."""
    return re.sub(r"^@[\w.]+:\s*", "", msg.strip())


def pydantic_ai_turn(*, model: str, system_prompt: str, user: str, max_tokens: int = 400) -> dict[str, Any]:
    """Produce a turn via a real Pydantic AI Agent (model served at the AI/ML base_url)."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    chat = OpenAIChatModel(model, provider=OpenAIProvider(base_url=AIML_BASE_URL, api_key=_key()))
    agent = Agent(chat, output_type=_Turn, system_prompt=system_prompt,
                  model_settings={"max_tokens": max_tokens})
    out = agent.run_sync(user).output
    return {"message": _clean(out.message), "reasoning": out.reasoning}


def langgraph_turn(*, model: str, system_prompt: str, user: str, max_tokens: int = 400) -> dict[str, Any]:
    """Produce a turn via a real LangGraph StateGraph (ChatOpenAI bound to the AI/ML base_url).

    Parses the reply defensively (not ``with_structured_output``) so it's reliable across models
    including the cheap Haiku tier — the graph genuinely executes; only the parse is forgiving."""
    from typing import TypedDict

    from langchain_openai import ChatOpenAI
    from langgraph.graph import END, START, StateGraph

    from engine.llm import loads_json

    llm = ChatOpenAI(model=model, base_url=AIML_BASE_URL, api_key=_key(), temperature=0, max_tokens=max_tokens)
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
