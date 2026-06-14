"""Tests for the LLM seam (`engine.llm`). Offline: no `openai`, no API key needed.

Validates the provider-agnostic binding and the request-body assembly — the two pure,
testable halves of the seam. `make_client` (which touches `openai` + a real key) is
exercised only for its missing-key guard.
"""

import pytest

from domains.authbridge.roles import ROLES
from engine.llm import (
    AIML_BASE_URL,
    DEBUG_MODEL,
    FEATHERLESS_BASE_URL,
    LLMConfig,
    LLMKeyMissing,
    completion_kwargs,
    make_client,
)


def test_from_role_anthropic_routes_to_aiml_with_effort():
    cfg = LLMConfig.from_role(ROLES["payer.reviewer"])
    assert cfg.model == "claude-opus-4-8"   # bare slug — AI/ML has no anthropic/ prefix
    assert cfg.base_url == AIML_BASE_URL
    assert cfg.api_key_env == "AIML_API_KEY"
    assert cfg.reasoning_effort == "high"


def test_debug_downshifts_to_haiku_and_drops_effort():
    # The 'cheap first' decision: Reviewer starts on Haiku; Haiku isn't reasoning-capable,
    # so reasoning_effort must be dropped or AI/ML rejects the request.
    cfg = LLMConfig.from_role(ROLES["payer.reviewer"], debug=True)
    assert cfg.model == DEBUG_MODEL
    assert cfg.reasoning_effort is None
    assert "reasoning_effort" not in completion_kwargs(cfg, [{"role": "user", "content": "x"}])


def test_from_role_featherless_prefix_routes_to_featherless():
    cfg = LLMConfig.from_role(ROLES["appeals.audit"])
    assert cfg.base_url == FEATHERLESS_BASE_URL
    assert cfg.api_key_env == "FEATHERLESS_API_KEY"


def test_debug_does_not_touch_open_model_role():
    # debug only downshifts anthropic/* — the open-model role stays put.
    cfg = LLMConfig.from_role(ROLES["appeals.audit"], debug=True)
    assert cfg.model.startswith("featherless/")


def test_from_role_rejects_human():
    with pytest.raises(ValueError):
        LLMConfig.from_role(ROLES["payer.medical_director"])


def test_completion_kwargs_omits_unset_params():
    cfg = LLMConfig(model="claude-haiku-4-5-20251001")  # nothing else set
    kw = completion_kwargs(cfg, [{"role": "user", "content": "hi"}])
    assert kw == {"model": "claude-haiku-4-5-20251001", "messages": [{"role": "user", "content": "hi"}]}


def test_completion_kwargs_surfaces_aiml_features():
    cfg = LLMConfig(
        model="claude-opus-4-8",
        reasoning_effort="high",
        max_tokens=512,
        response_format={"type": "json_schema", "json_schema": {"name": "verdict"}},
    )
    tools = [{"type": "function", "function": {"name": "emit_verdict"}}]
    kw = completion_kwargs(cfg, [], stream=True, tools=tools, tool_choice="required")
    assert kw["reasoning_effort"] == "high"
    assert kw["max_tokens"] == 512
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["tools"] == tools
    assert kw["tool_choice"] == "required"
    assert kw["stream"] is True
    assert kw["stream_options"] == {"include_usage": True}


def test_with_model_reroutes_provider():
    cfg = LLMConfig(model="claude-opus-4-8")
    rerouted = cfg.with_model("featherless/some-open-model")
    assert rerouted.base_url == FEATHERLESS_BASE_URL
    assert rerouted.api_key_env == "FEATHERLESS_API_KEY"


def test_make_client_raises_with_hint_when_key_missing():
    cfg = LLMConfig(model="claude-opus-4-8")
    with pytest.raises(LLMKeyMissing) as exc:
        make_client(cfg, env={})  # empty env → no AIML_API_KEY
    assert "AIML_API_KEY" in str(exc.value)
