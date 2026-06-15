"""Tests for the framework dispatch (engine.frameworks). The live framework execution needs a
key/network (verified in spikes/08); here we test the pure wiring map."""

from engine.frameworks import langgraph_turn, pydantic_ai_turn, turn_fn


def test_turn_fn_maps_only_the_wired_frameworks():
    assert turn_fn("pydantic_ai") is pydantic_ai_turn
    assert turn_fn("langgraph") is langgraph_turn
    # not wired → None (caller uses the AI/ML gateway directly)
    assert turn_fn("human") is None
    assert turn_fn("crewai") is None
    assert turn_fn("letta") is None
