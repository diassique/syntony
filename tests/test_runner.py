"""Tests for the AuthBridge agent runner — fully offline (narrate=None → deterministic).

Drives all four synthetic cases end-to-end through the real coordinator + FSM, asserting
the negotiation path each takes and the final decision. Also checks the narrator seam:
LLM roles are narrated, the human (HITL) role is not.
"""

import asyncio

import pytest
from band.testing import FakeAgentTools

from domains.authbridge.cases import ALL_CASES
from domains.authbridge.runner import AuthBridgeState, build_runner, plan, run_authbridge
from engine.coordinator import run_case
from protocol import Kind, State


def _run(case_name, **kw):
    return asyncio.run(run_authbridge(case_name, **kw))


def _kinds(res):
    return [e.kind for e in res.history]


def _final(res):
    return res.history[-1]


def test_complete_case_approves():
    res = _run("mri_lumbar_complete")
    assert res.stopped == "terminal" and res.final_state is State.DECIDE
    assert _kinds(res) == [Kind.CASE_OPEN, Kind.PROPOSAL, Kind.DECISION]
    assert _final(res).payload["outcome"] == "APPROVE"
    assert _final(res).author == "payer.reviewer"


def test_raw_intake_is_repaired_by_counsel_then_approved():
    # Drive manually so we can inspect the working request after Counsel's fix.
    st = AuthBridgeState(req=ALL_CASES["mri_lumbar_raw_intake"]())
    assert st.req.procedure.code == "" and st.req.ordering_provider.signed is False
    res = asyncio.run(
        run_case(case_id="c", start=State.FRAME, runner=build_runner(), domain=st)
    )
    assert _kinds(res) == [Kind.CASE_OPEN, Kind.PROPOSAL, Kind.DECISION]
    assert _final(res).payload["outcome"] == "APPROVE"
    # Counsel filled the blank CPT and obtained the signature before submission.
    assert st.req.procedure.code == "72148" and st.req.ordering_provider.signed is True


def test_missing_docs_triggers_info_round_then_approves():
    res = _run("mri_lumbar_missing_docs")
    assert res.final_state is State.DECIDE
    assert _kinds(res) == [
        Kind.CASE_OPEN, Kind.PROPOSAL, Kind.INFO_REQUEST, Kind.INFO_RESPONSE, Kind.DECISION
    ]
    assert _final(res).payload["outcome"] == "APPROVE"


def test_step_therapy_denial_is_appealed_and_overturned():
    res = _run("humira_step_therapy_denied")
    assert res.final_state is State.DECIDE and res.stopped == "terminal"
    pa = [e.payload.get("pa_event") for e in res.history]
    # the golden loop: submitted → denied (step therapy) → appeal → overturned
    assert pa == ["PA_INITIATED", "REQUEST_SUBMITTED", "DECISION_DENIED",
                  "APPEAL_PACKET_ASSEMBLED", "DECISION_OVERTURNED"]
    denied = next(e for e in res.history if e.payload.get("pa_event") == "DECISION_DENIED")
    assert denied.payload["denial_reason"] == "STEP_THERAPY_NOT_MET"
    appeal = next(e for e in res.history if e.payload.get("pa_event") == "APPEAL_PACKET_ASSEMBLED")
    assert appeal.author == "provider.appeals"
    assert _final(res).payload["outcome"] == "APPROVE" and _final(res).payload.get("overturned") is True


def test_dx_mismatch_escalates_to_human_who_decides():
    res = _run("mri_lumbar_dx_mismatch")
    assert res.final_state is State.DECIDE
    assert _kinds(res) == [
        Kind.CASE_OPEN, Kind.PROPOSAL, Kind.ESCALATION, Kind.RECRUIT_REQUEST, Kind.DECISION
    ]
    # the binding decision is the human Medical Director's, and it's labelled simulated
    assert _final(res).author == "payer.medical_director"
    assert "simulated" in _final(res).payload.get("note", "").lower()


def test_emits_over_band_with_audit_isolation():
    tools = FakeAgentTools()
    res = _run("mri_lumbar_dx_mismatch", tools=tools)
    assert res.final_state is State.DECIDE
    # every move in this path is a room message (5), none are private events here
    tools.assert_message_sent(count=5)
    assert tools.events_sent == []


def test_narrator_runs_for_llm_roles_but_not_for_human():
    calls = []

    def fake_narrate(role_id, facts, kind, history):
        calls.append(role_id)
        return {"message": f"MSG[{role_id}]", "reasoning": "R"}

    res = _run("mri_lumbar_dx_mismatch", narrate=fake_narrate)
    # LLM roles were narrated; the human Medical Director was NOT sent to the narrator.
    assert "payer.reviewer" in calls
    assert "payer.medical_director" not in calls
    # narrated text landed in the envelope payload for an LLM role…
    reviewer_env = next(e for e in res.history if e.author == "payer.reviewer")
    assert reviewer_env.payload["message"] == "MSG[payer.reviewer]"
    # …while the human decision used the deterministic local text (facts), not the narrator.
    md_env = _final(res)
    assert md_env.payload["message"] == md_env.payload["facts"]


def test_plan_is_pure_and_offline():
    # plan() never touches I/O — a smoke check that it returns a legal first move.
    st = AuthBridgeState(req=ALL_CASES["mri_lumbar_complete"]())
    p = plan(State.FRAME, st)
    assert p.role_id == "provider.intake" and p.next_state is State.PROPOSE
