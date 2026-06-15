"""Tests for the framework dispatch (engine.frameworks). The pure wiring map runs offline; the
live smoke (real Pydantic AI + LangGraph turns over AI/ML) is gated behind RUN_LIVE=1 so it can
catch framework/SDK API churn after a dependency upgrade without slowing the default suite."""

import os

import pytest

from engine.frameworks import langgraph_turn, pydantic_ai_turn, turn_fn


def test_turn_fn_maps_only_the_wired_frameworks():
    assert turn_fn("pydantic_ai") is pydantic_ai_turn
    assert turn_fn("langgraph") is langgraph_turn
    # not wired → None (caller uses the AI/ML gateway directly)
    assert turn_fn("human") is None
    assert turn_fn("crewai") is None
    assert turn_fn("letta") is None


def test_frameworks_execute_live():
    """Run one real turn through each framework — catches API churn after a deps bump.
    Skipped unless RUN_LIVE=1 (needs AIML_API_KEY). Run: RUN_LIVE=1 pytest -k execute_live."""
    if not os.environ.get("RUN_LIVE"):
        pytest.skip("set RUN_LIVE=1 (with AIML_API_KEY in .env) to run the live framework smoke")
    from dotenv import load_dotenv
    load_dotenv()
    from domains.authbridge.roles import ROLES
    from engine.llm import BALANCED_MODEL, LLMConfig, looks_like_blob

    pcfg = LLMConfig.from_role(ROLES["payer.reviewer"], downshift=BALANCED_MODEL)
    p = pydantic_ai_turn(cfg=pcfg, system_prompt="You are a payer reviewer.",
                         user="Phrase for the room: APPROVE — meets medical-necessity criteria.")
    assert p["message"] and not looks_like_blob(p["message"])

    lcfg = LLMConfig.from_role(ROLES["provider.intake"], downshift=BALANCED_MODEL)
    g = langgraph_turn(cfg=lcfg, system_prompt="You are clinic intake.",
                       user="Phrase: opening a prior-auth case for MRI lumbar spine.")
    assert g["message"] and not looks_like_blob(g["message"])
