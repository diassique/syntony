"""Smoke tests for L1 protocol types: Envelope (de)serialization + validation,
and the state-machine transition table as data. No Band, no I/O.
"""

import pytest
from pydantic import ValidationError

from protocol import Envelope, Kind, State, Visibility, is_allowed
from protocol.state_machine import TERMINAL, TRANSITIONS


def test_envelope_roundtrip():
    env = Envelope(
        case_id="case-001",
        turn=0,
        author="provider.intake",
        kind=Kind.CASE_OPEN,
        payload={"procedure": "MRI lumbar spine", "cpt": "72148"},
    )
    # default visibility is room
    assert env.visibility is Visibility.ROOM
    # serialize -> json -> back, value-equal
    dumped = env.model_dump_json()
    restored = Envelope.model_validate_json(dumped)
    assert restored == env
    # enums survive as their string values in dict form
    assert env.model_dump()["kind"] == "CASE_OPEN"


def test_envelope_rejects_bad_kind_and_negative_turn():
    with pytest.raises(ValidationError):
        Envelope(case_id="c", turn=0, author="a", kind="NOPE", payload={})
    with pytest.raises(ValidationError):
        Envelope(case_id="c", turn=-1, author="a", kind=Kind.PROPOSAL, payload={})


def test_private_event_visibility_explicit():
    env = Envelope(
        case_id="c",
        turn=3,
        author="provider.counsel",
        kind=Kind.PROPOSAL,
        visibility=Visibility.PRIVATE_EVENT,
        payload={"note": "internal strategy"},
    )
    assert env.visibility is Visibility.PRIVATE_EVENT


def test_transition_table_is_consistent():
    # every state appears as a key
    assert set(TRANSITIONS) == set(State)
    # every destination is a real State
    for dsts in TRANSITIONS.values():
        assert dsts <= set(State)
    # DECIDE is terminal
    assert TRANSITIONS[State.DECIDE] == frozenset()
    assert TERMINAL == frozenset({State.DECIDE})
    # a known-legal and a known-illegal edge
    assert is_allowed(State.FRAME, State.PROPOSE)
    assert not is_allowed(State.FRAME, State.DECIDE)
    # you can only reach DECIDE from REVIEW or ARBITER
    reachers = {s for s in State if State.DECIDE in TRANSITIONS[s]}
    assert reachers == {State.REVIEW, State.ARBITER}
