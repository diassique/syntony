"""L2 — the single LLM seam.

This is the *only* place in the engine that knows an LLM exists. Agent code names a
role, never a model or a provider; the engine binds a ``RoleSpec`` to an ``LLMConfig``
here at runtime. That indirection is what makes Syntony honestly provider-agnostic
rather than nailed to one vendor — and it's the lever for the AI/ML API partner prize.

**Three axes of pluggability, one contract:**

1. *Model* — any of AI/ML API's 400+ models behind one key (`AIML_API_KEY`). Swap the
   ``model`` slug; nothing else changes.
2. *Provider* — ``base_url`` is per-config. Point a role at any OpenAI-compatible
   endpoint (Featherless for the open-model role = the second partner prize) without
   touching engine code.
3. *Framework* — PydanticAI / LangGraph accept a custom OpenAI client, so every
   framework funnels through this one seam (see ``engine.agent_base.build_adapter``).

AI/ML API is **OpenAI-compatible** (`https://api.aimlapi.com/v1`), so we use the
``openai`` SDK pointed at its ``base_url`` — confirmed facts in ``NOTES_AIML.md``. The
import is lazy (inside ``make_client``) so this module loads and is testable with no
``openai`` installed and no key present. ``completion_kwargs`` is pure data — it builds
the request body and surfaces the AI/ML features we lean on for the prize: structured
outputs (`response_format` json_schema), function calling (`tools`), `reasoning_effort`
per role, and streaming.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

# --- Providers (OpenAI-compatible endpoints) -------------------------------------
# AI/ML API: confirmed in NOTES_AIML.md. Featherless base_url is UNCONFIRMED — verify
# against Featherless docs before the open-model role goes live (2nd partner prize).
AIML_BASE_URL = "https://api.aimlapi.com/v1"
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"  # UNCONFIRMED — verify before wiring

# Debug downshift target. Cheapest Claude tier on the gateway ($1/$5 per MTok). Haiku is
# NOT reasoning-capable, so the debug path must NOT send `reasoning_effort` (AI/ML rejects
# it for non-reasoning models). VERIFIED LIVE against the AI/ML catalog (2026-06-13): slugs
# are BARE (no `anthropic/` prefix), and Haiku alone carries its date suffix — opus/sonnet
# don't. See NOTES_AIML.md "VERIFIED LIVE".
DEBUG_MODEL = "claude-haiku-4-5-20251001"


class LLMKeyMissing(RuntimeError):
    """Raised when the provider API key env var is absent. Carries a fix hint."""


@dataclass(frozen=True)
class LLMConfig:
    """Which 'brain' powers a role, and how. Pure data — no network, no key needed.

    Defaults target AI/ML API. To route a role elsewhere (e.g. Featherless for the open
    model), set ``base_url`` + ``api_key_env`` — that is the whole provider-swap.
    """

    model: str                                  # gateway slug, e.g. "anthropic/claude-opus-4-8"
    base_url: str = AIML_BASE_URL               # ← axis 2: any OpenAI-compatible endpoint
    api_key_env: str = "AIML_API_KEY"           # env var holding this provider's key
    reasoning_effort: str | None = None         # low|medium|high (reasoning-capable models only)
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: dict[str, Any] | None = None   # {"type": "json_schema", ...} — typed agent I/O
    extra_body: dict[str, Any] = field(default_factory=dict)  # escape hatch for per-model params

    @classmethod
    def from_role(cls, spec: "RoleSpec", *, debug: bool = False) -> "LLMConfig":  # noqa: F821
        """Bind a declarative ``RoleSpec`` to a concrete config.

        Provider is chosen by the model slug's prefix (``featherless/`` → Featherless,
        everything else → AI/ML). ``reasoning_effort`` is read from ``spec.extra``.

        ``debug=True`` downshifts any Anthropic role to the cheap Haiku tier for cheap
        iteration on the live loop, and drops ``reasoning_effort`` (Haiku can't take it).
        """
        model = spec.model
        if model is None:
            raise ValueError(f"Role {spec.id!r} has no model (is it a HUMAN role?)")

        effort = spec.extra.get("reasoning_effort")
        if debug and model.startswith("claude"):  # AI/ML Claude slugs are bare, not anthropic/-prefixed
            model, effort = DEBUG_MODEL, None

        if model.startswith("featherless/"):
            base_url, api_key_env = FEATHERLESS_BASE_URL, "FEATHERLESS_API_KEY"
        else:
            base_url, api_key_env = AIML_BASE_URL, "AIML_API_KEY"

        return cls(
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            reasoning_effort=effort,
            temperature=spec.extra.get("temperature"),
            max_tokens=spec.extra.get("max_tokens"),
        )

    def with_model(self, model: str) -> "LLMConfig":
        """Return a copy targeting a different model (re-routes provider by prefix)."""
        base_url, api_key_env = (
            (FEATHERLESS_BASE_URL, "FEATHERLESS_API_KEY")
            if model.startswith("featherless/")
            else (AIML_BASE_URL, "AIML_API_KEY")
        )
        return replace(self, model=model, base_url=base_url, api_key_env=api_key_env)


def make_client(cfg: LLMConfig, *, env: Mapping[str, str] | None = None):
    """Build an OpenAI-compatible client for ``cfg``. Lazy-imports ``openai``.

    Raises ``LLMKeyMissing`` (with a fix hint) when the provider key is absent, rather
    than letting the SDK fail with an opaque auth error at request time.
    """
    env = os.environ if env is None else env
    key = env.get(cfg.api_key_env)
    if not key:
        raise LLMKeyMissing(
            f"{cfg.api_key_env} is not set — needed to reach {cfg.base_url}. "
            f"Add it to .env (gitignored)."
        )
    from openai import OpenAI  # lazy: keep this module import-safe without the SDK

    return OpenAI(base_url=cfg.base_url, api_key=key)


def completion_kwargs(
    cfg: LLMConfig,
    messages: list[dict[str, Any]],
    *,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    """Assemble the ``chat.completions.create`` request body from ``cfg``. Pure function.

    Only emits a parameter when it's set, so a config built for a non-reasoning model
    (e.g. the debug Haiku tier) never sends ``reasoning_effort``. ``stream`` adds
    ``stream_options.include_usage`` so we get token counts on the final chunk.
    """
    kwargs: dict[str, Any] = {"model": cfg.model, "messages": messages}
    if cfg.max_tokens is not None:
        kwargs["max_tokens"] = cfg.max_tokens
    if cfg.temperature is not None:
        kwargs["temperature"] = cfg.temperature
    if cfg.reasoning_effort is not None:
        kwargs["reasoning_effort"] = cfg.reasoning_effort
    if cfg.response_format is not None:
        kwargs["response_format"] = cfg.response_format
    if tools is not None:
        kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
    if stream:
        kwargs["stream"] = True
        kwargs["stream_options"] = {"include_usage": True}
    kwargs.update(cfg.extra_body)
    return kwargs
