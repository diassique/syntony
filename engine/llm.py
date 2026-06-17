"""L2 — the single LLM seam.

This is the *only* place in the engine that knows an LLM exists. Agent code names a
role, never a model or a provider; the engine binds a ``RoleSpec`` to an ``LLMConfig``
here at runtime. That indirection is what makes Syntony honestly provider-agnostic
rather than nailed to one vendor — and it's the lever for the AI/ML API partner prize.

**Three axes of pluggability, one contract:**

1. *Model* — any of AI/ML API's 400+ models behind one key (`AIML_API_KEY`). Swap the
   ``model`` slug; nothing else changes.
2. *Provider* — ``base_url`` is per-config. Point a role at any OpenAI-compatible
   endpoint (a self-hosted/open-model gateway, a second vendor, …) without touching
   engine code. The default for every role is the AI/ML gateway.
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

import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

# --- Providers (OpenAI-compatible endpoints) -------------------------------------
# AI/ML API powers every role (confirmed in NOTES_AIML.md). The `featherless/` prefix is
# kept as a worked example of routing a role to a second OpenAI-compatible endpoint via
# `base_url` — not used by any role today (base_url UNCONFIRMED; verify before enabling).
AIML_BASE_URL = "https://api.aimlapi.com/v1"
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"  # example only — UNCONFIRMED, unused

# Multimodal models, VERIFIED LIVE on our key (2026-06-15, see NOTES_AIML.md):
VISION_MODEL = "gpt-5.5-2026-04-23"          # image→JSON; Claude is NOT vision-capable via this gateway
EMBED_MODEL = "text-embedding-3-small"        # 1536-dim
OCR_MODEL = "mistral/mistral-ocr-latest"      # /v1/ocr → pages[].markdown

# Debug downshift target. Cheapest Claude tier on the gateway ($1/$5 per MTok). Haiku is
# NOT reasoning-capable, so the debug path must NOT send `reasoning_effort` (AI/ML rejects
# it for non-reasoning models). VERIFIED LIVE against the AI/ML catalog (2026-06-13): slugs
# are BARE (no `anthropic/` prefix), and Haiku alone carries its date suffix — opus/sonnet
# don't. See NOTES_AIML.md "VERIFIED LIVE".
DEBUG_MODEL = "claude-haiku-4-5-20251001"
# Balanced downshift target for the live demo: crisp output + reliable framework structured
# output, without the priciest opus tier on every run. opus→sonnet; sonnet/gpt-5.5 stay as-is.
BALANCED_MODEL = "claude-sonnet-4-6"


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
    def from_role(cls, spec: "RoleSpec", *, debug: bool = False, downshift: str | None = None) -> "LLMConfig":  # noqa: F821
        """Bind a declarative ``RoleSpec`` to a concrete config.

        Provider is chosen by the model slug's prefix (``featherless/`` → Featherless,
        everything else → AI/ML). ``reasoning_effort`` is read from ``spec.extra``.

        Downshift tier (cost/quality dial for the live loop): ``debug=True`` caps Anthropic
        roles at the cheap Haiku tier; ``downshift="claude-sonnet-4-6"`` caps them at Sonnet
        (the balanced live default). Either drops ``reasoning_effort`` (the cheaper tier can't
        take thinking, and it conflicts with the frameworks' structured output). ``downshift``
        wins over ``debug`` when both are given; neither → the role's declared model.
        """
        model = spec.model
        if model is None:
            raise ValueError(f"Role {spec.id!r} has no model (is it a HUMAN role?)")

        effort = spec.extra.get("reasoning_effort")
        target = downshift or (DEBUG_MODEL if debug else None)
        if target and model.startswith("claude") and model != target:  # AI/ML Claude slugs are bare
            model, effort = target, None

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


# ---- streaming + token accounting (AI/ML usage telemetry) -----------------------
# AI/ML API is OpenAI-compatible, so it streams token-by-token and reports usage on the
# final chunk via `stream_options.include_usage`. `stream_chat` exercises that genuinely
# and returns the accumulated text + the (input, output) token counts so the app can meter
# real consumption (surfaced in the console "AI/ML API" view).

def _usage_tokens(usage: Any) -> tuple[int, int]:
    """(input, output) token counts from an OpenAI-style usage object/dict, defensively."""
    if usage is None:
        return 0, 0
    get = usage.get if isinstance(usage, dict) else (lambda k: getattr(usage, k, None))
    return int(get("prompt_tokens") or 0), int(get("completion_tokens") or 0)


def stream_chat(client: Any, kwargs: dict[str, Any]) -> tuple[str, tuple[int, int]]:
    """Run a **streaming** chat completion and accumulate the reply. Forces
    ``stream``+``stream_options.include_usage`` so the final chunk carries the token usage.
    Returns ``(text, (input_tokens, output_tokens))``. Genuinely uses AI/ML's streaming API."""
    kwargs = {**kwargs, "stream": True, "stream_options": {"include_usage": True}}
    parts: list[str] = []
    usage: Any = None
    for chunk in client.chat.completions.create(**kwargs):
        for choice in (getattr(chunk, "choices", None) or []):
            piece = getattr(getattr(choice, "delta", None), "content", None)
            if piece:
                parts.append(piece)
        if getattr(chunk, "usage", None):
            usage = chunk.usage
    return "".join(parts), _usage_tokens(usage)


# ---- multimodal capability layer (one AI/ML gateway, every modality) ------------
# These wrap the AI/ML endpoints verified live in spikes/07 + NOTES_AIML.md. The pure
# request-shaping helpers (``_vision_messages`` / ``_ocr_payload`` / ``loads_json``) are
# split out so they're testable without a key or network.

def looks_like_blob(text: str) -> bool:
    """True if a (cleaned) message is actually a raw JSON object/array — a weak model sometimes
    packs an envelope into the message field. A narrow check (no length cap): callers reject a
    blob and fall back, but must NOT reject long-but-clean prose (that bug cost us real fallbacks)."""
    return text.lstrip().startswith(("{", "["))


def loads_json(text: str) -> dict[str, Any]:
    """Defensive JSON parse of a model reply: tolerate code fences / surrounding prose by
    extracting the outermost ``{...}``. Returns ``{}`` if nothing parses."""
    t = text or ""
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        return json.loads(t[i:j + 1])
    except (json.JSONDecodeError, ValueError):
        return {}


def _vision_messages(instruction: str, image_data_uri: str) -> list[dict[str, Any]]:
    """OpenAI multimodal message: an instruction + one image (base64 data URI or URL)."""
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": image_data_uri}},
        ],
    }]


def vision_extract(image_data_uri: str, *, schema: dict[str, Any], instruction: str,
                   model: str = VISION_MODEL, max_tokens: int = 600,
                   env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read an image with a vision model and return structured JSON (``response_format`` =
    json_schema). The default model is vision-verified; Claude is not (see NOTES_AIML)."""
    cfg = replace(LLMConfig(model=model, max_tokens=max_tokens), response_format=schema)
    client = make_client(cfg, env=env)
    text, _ = stream_chat(client, completion_kwargs(cfg, _vision_messages(instruction, image_data_uri)))
    return loads_json(text)


def extract_from_text(text: str, *, schema: dict[str, Any], instruction: str,
                      model: str = VISION_MODEL, max_tokens: int = 600,
                      env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Extract structured JSON from plain text (e.g. OCR'd document markdown) via a chat
    model + json_schema. Sibling of ``vision_extract`` for the non-image path."""
    cfg = replace(LLMConfig(model=model, max_tokens=max_tokens), response_format=schema)
    client = make_client(cfg, env=env)
    messages = [{"role": "user", "content": f"{instruction}\n\nDOCUMENT:\n{text[:8000]}"}]
    out, _ = stream_chat(client, completion_kwargs(cfg, messages))
    return loads_json(out)


def embed(texts: str | list[str], *, model: str = EMBED_MODEL,
          env: Mapping[str, str] | None = None) -> list[list[float]]:
    """Embed one or more strings via ``/v1/embeddings``. Returns a list of vectors."""
    client = make_client(LLMConfig(model=model), env=env)
    inputs = [texts] if isinstance(texts, str) else list(texts)
    resp = client.embeddings.create(model=model, input=inputs)
    return [d.embedding for d in resp.data]


def _ocr_payload(url: str, model: str, kind: str) -> dict[str, Any]:
    """Body for ``POST /v1/ocr`` — ``kind`` ∈ {document_url, image_url}; the key mirrors the type."""
    return {"model": model, "document": {"type": kind, kind: url}}


def ocr(url: str, *, model: str = OCR_MODEL, kind: str = "document_url",
        env: Mapping[str, str] | None = None) -> str:
    """OCR a document (PDF/image) at ``url`` → concatenated page markdown. URL input only
    (the OCR schema has no base64 field; for image bytes use ``vision_extract`` instead)."""
    env = os.environ if env is None else env
    key = env.get("AIML_API_KEY")
    if not key:
        raise LLMKeyMissing("AIML_API_KEY is not set — needed for /v1/ocr.")
    import httpx  # lazy: keep this module import-safe

    resp = httpx.post(
        f"{AIML_BASE_URL}/ocr",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=_ocr_payload(url, model, kind),
        timeout=120,
    )
    resp.raise_for_status()
    pages = resp.json().get("pages", [])
    return "\n\n".join(p.get("markdown", "") for p in pages).strip()
