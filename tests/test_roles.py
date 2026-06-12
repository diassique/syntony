"""Tests for the AuthBridge role cast (declarative data) and the adapter-factory guards.
No frameworks/keys needed — this validates the spec, not live agents.
"""

import pytest

from domains.authbridge.roles import ROLES
from engine.agent_base import Framework, build_adapter
from protocol import State


def test_role_ids_consistent_and_prompts_present():
    for key, spec in ROLES.items():
        assert spec.id == key
        assert spec.system_prompt.strip()
        assert spec.display_name and "bot" not in spec.display_name.lower()


def test_human_has_no_model_others_do():
    for spec in ROLES.values():
        if spec.framework is Framework.HUMAN:
            assert spec.model is None
        else:
            assert spec.model, f"{spec.id} needs a model slug"


def test_every_protocol_state_has_an_actor():
    covered = {s for spec in ROLES.values() for s in spec.acts_in}
    assert covered == set(State), f"states with no role: {set(State) - covered}"


def test_build_adapter_guards():
    human = ROLES["payer.medical_director"]
    with pytest.raises(ValueError):
        build_adapter(human, provider_key="x")
    # frameworks not yet wired raise NotImplementedError (intentional, Day-2 incremental)
    with pytest.raises(NotImplementedError):
        build_adapter(ROLES["provider.counsel"], provider_key="x")
