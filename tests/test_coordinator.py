"""Tests for the domain-independent coordinator loop. Offline: a scripted fake runner
drives the FSM; Band traffic is verified through FakeAgentTools. No LLM, no real Band.
"""

import asyncio

import pytest
from band.testing import FakeAgentTools

from engine.coordinator import (
    CaseContext,
    CoordinatorResult,
    IllegalTransition,
    Move,
    run_case,
)
from protocol import Envelope, Kind, State, Visibility


def _env(ctx: CaseContext, kind: Kind, visibility: Visibility = Visibility.ROOM) -> Envelope:
    return Envelope(
        case_id=ctx.case_id, turn=ctx.turn, author="role.x", kind=kind, visibility=visibility, payload={}
    )


def _scripted(steps):
    """Build a runner that emits a fixed list of (next_state, kind, visibility, mentions),
    then returns None (stop)."""
    seq = list(steps)

    async def runner(ctx: CaseContext):
        if not seq:
            return None
        next_state, kind, visibility, mentions = seq.pop(0)
        return Move(_env(ctx, kind, visibility), next_state=next_state, mentions=mentions)

    return runner


def test_happy_path_reaches_terminal():
    runner = _scripted([
        (State.PROPOSE, Kind.CASE_OPEN, Visibility.ROOM, ()),
        (State.REVIEW, Kind.PROPOSAL, Visibility.ROOM, ("payer.reviewer",)),
        (State.DECIDE, Kind.DECISION, Visibility.ROOM, ()),
    ])
    res = asyncio.run(run_case(case_id="c1", start=State.FRAME, runner=runner))
    assert isinstance(res, CoordinatorResult)
    assert res.stopped == "terminal"
    assert res.final_state is State.DECIDE
    assert res.turns == 3
    assert [e.kind for e in res.history] == [Kind.CASE_OPEN, Kind.PROPOSAL, Kind.DECISION]


def test_emits_through_band_with_routing_and_audit():
    tools = FakeAgentTools()
    runner = _scripted([
        (State.REVIEW, Kind.PROPOSAL, Visibility.ROOM, ("payer.reviewer",)),  # msg: routed chat
        (State.INFO, Kind.INFO_REQUEST, Visibility.PRIVATE_EVENT, ()),        # event: audit channel
        (State.REVIEW, Kind.INFO_RESPONSE, Visibility.ROOM, ()),              # msg
        (State.DECIDE, Kind.DECISION, Visibility.ROOM, ()),                   # msg
    ])
    res = asyncio.run(run_case(case_id="c1", start=State.PROPOSE, runner=runner, tools=tools))
    assert res.stopped == "terminal"
    # three room messages (PROPOSAL, INFO_RESPONSE, DECISION), one private audit event
    tools.assert_message_sent(count=3)
    tools.assert_event_sent(message_type="thought", count=1)
    assert tools.messages_sent[0]["mentions"] == [{"id": "payer.reviewer"}]


def test_illegal_transition_raises():
    # FRAME -> DECIDE is not a declared edge.
    runner = _scripted([(State.DECIDE, Kind.DECISION, Visibility.ROOM, ())])
    with pytest.raises(IllegalTransition):
        asyncio.run(run_case(case_id="c1", start=State.FRAME, runner=runner))


def test_max_turns_guard_stops_runaway():
    # Ping-pong REVIEW <-> REVISE forever (both legal); the guard must cut it off.
    async def runner(ctx: CaseContext):
        nxt = State.REVISE if ctx.state is State.REVIEW else State.REVIEW
        return Move(_env(ctx, Kind.PROPOSAL), next_state=nxt)

    res = asyncio.run(run_case(case_id="c1", start=State.REVIEW, runner=runner, max_turns=5))
    assert res.stopped == "max_turns"
    assert res.turns == 5
    assert res.final_state is not State.DECIDE


def test_runner_none_stops_with_no_move():
    async def runner(ctx: CaseContext):
        return None

    res = asyncio.run(run_case(case_id="c1", start=State.PROPOSE, runner=runner))
    assert res.stopped == "no_move"
    assert res.turns == 0
    assert res.history == []


def test_case_id_mismatch_raises():
    async def runner(ctx: CaseContext):
        bad = Envelope(case_id="WRONG", turn=0, author="role.x", kind=Kind.PROPOSAL)
        return Move(bad, next_state=State.REVIEW)

    with pytest.raises(ValueError):
        asyncio.run(run_case(case_id="c1", start=State.PROPOSE, runner=runner))


def test_starting_at_terminal_stops_immediately():
    res = asyncio.run(run_case(case_id="c1", start=State.DECIDE, runner=_scripted([])))
    assert res.stopped == "terminal"
    assert res.turns == 0


def test_tools_for_routes_each_envelope_to_its_account():
    clinic, payer = FakeAgentTools(), FakeAgentTools()

    def tools_for(env):
        return clinic if env.author == "provider" else payer

    async def runner(ctx: CaseContext):
        if ctx.state is State.PROPOSE:
            env = Envelope(case_id=ctx.case_id, turn=ctx.turn, author="provider", kind=Kind.PROPOSAL)
            return Move(env, next_state=State.REVIEW)
        env = Envelope(case_id=ctx.case_id, turn=ctx.turn, author="payer", kind=Kind.DECISION)
        return Move(env, next_state=State.DECIDE)

    res = asyncio.run(run_case(case_id="c1", start=State.PROPOSE, runner=runner, tools_for=tools_for))
    assert res.final_state is State.DECIDE
    clinic.assert_message_sent(count=1)  # the provider move
    payer.assert_message_sent(count=1)   # the payer move


def test_pause_states_stop_the_loop_for_human_in_the_loop():
    """A move that lands the case in a pause state stops the loop (stopped='paused'), emitting
    that move but not advancing further — the basis for the human-in-the-loop decision."""
    runner = _scripted([
        (State.PROPOSE, Kind.CASE_OPEN, Visibility.ROOM, ()),
        (State.REVIEW, Kind.PROPOSAL, Visibility.ROOM, ()),
        (State.ESCALATE, Kind.ESCALATION, Visibility.ROOM, ()),
        (State.ARBITER, Kind.RECRUIT_REQUEST, Visibility.ROOM, ()),  # entering ARBITER pauses
        (State.DECIDE, Kind.DECISION, Visibility.ROOM, ()),          # never reached
    ])
    res = asyncio.run(run_case(case_id="c1", start=State.FRAME, runner=runner, pause_states={State.ARBITER}))
    assert res.stopped == "paused"
    assert res.final_state is State.ARBITER
    assert [e.kind for e in res.history][-1] is Kind.RECRUIT_REQUEST  # the pausing move was emitted


def test_on_turn_fires_once_per_turn_with_envelope_and_new_state():
    """The streaming hook lets a caller persist/observe each turn as it lands (live theater)."""
    seen: list[tuple[Kind, State]] = []

    async def on_turn(env, state):  # async hook is awaited
        seen.append((env.kind, state))

    runner = _scripted([
        (State.PROPOSE, Kind.CASE_OPEN, Visibility.ROOM, ()),
        (State.REVIEW, Kind.PROPOSAL, Visibility.ROOM, ()),
        (State.DECIDE, Kind.DECISION, Visibility.ROOM, ()),
    ])
    res = asyncio.run(run_case(case_id="c1", start=State.FRAME, runner=runner, on_turn=on_turn))
    # one callback per emitted envelope, in order, carrying the post-move state
    assert seen == [
        (Kind.CASE_OPEN, State.PROPOSE),
        (Kind.PROPOSAL, State.REVIEW),
        (Kind.DECISION, State.DECIDE),
    ]
    assert len(seen) == res.turns
