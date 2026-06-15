"""Tests for the AuthBridge agent runner — fully offline (narrate=None → deterministic).

Drives the synthetic cases end-to-end through the real coordinator + FSM, asserting the
multi-agent pipeline (intake → eligibility → counsel → reviewer ⇄ specialists → notification
→ decision), the golden appeal→overturn loop, and the human escalation path. Also checks the
narrator seam: LLM roles are narrated, the human (HITL) role is not.
"""

import asyncio

from band.testing import FakeAgentTools

from domains.authbridge.cases import ALL_CASES
from domains.authbridge.runner import AuthBridgeState, build_runner, plan, run_authbridge
from engine.coordinator import run_case
from protocol import Kind, State


def _run(case_name, **kw):
    return asyncio.run(run_authbridge(case_name, **kw))


def _authors(res):
    return {e.author for e in res.history}


def _pa(res):
    return [e.payload.get("pa_event") for e in res.history if e.payload.get("pa_event")]


def _final(res):
    return res.history[-1]


def _is_subsequence(sub, seq):
    """True if every item of ``sub`` appears in ``seq`` in order (gaps allowed)."""
    it = iter(seq)
    return all(item in it for item in sub)


def test_complete_case_runs_the_full_specialist_pipeline_and_approves():
    res = _run("mri_lumbar_complete")
    assert res.stopped == "terminal" and res.final_state is State.DECIDE
    assert _final(res).author == "payer.reviewer" and _final(res).payload["outcome"] == "APPROVE"
    # every specialist on the happy path took a real turn
    assert {"provider.intake", "provider.eligibility", "provider.counsel",
            "payer.reviewer", "payer.guidelines", "payer.compliance",
            "payer.notification"} <= _authors(res)
    # and the audit vocabulary reflects each one
    assert _is_subsequence(
        ["PA_INITIATED", "ELIGIBILITY_VERIFIED", "REQUEST_SUBMITTED", "GUIDELINES_APPLIED",
         "COMPLIANCE_VERIFIED", "NOTICE_DRAFTED", "DECISION_APPROVED"],
        _pa(res),
    )


def test_raw_intake_is_repaired_by_counsel_then_approved():
    st = AuthBridgeState(req=ALL_CASES["mri_lumbar_raw_intake"]())
    assert st.req.procedure.code == "" and st.req.ordering_provider.signed is False
    res = asyncio.run(run_case(case_id="c", start=State.FRAME, runner=build_runner(), domain=st))
    assert res.final_state is State.DECIDE and _final(res).payload["outcome"] == "APPROVE"
    # Counsel filled the blank CPT and obtained the signature before submission.
    assert st.req.procedure.code == "72148" and st.req.ordering_provider.signed is True


def test_missing_docs_triggers_info_round_then_approves():
    res = _run("mri_lumbar_missing_docs")
    assert res.final_state is State.DECIDE and _final(res).payload["outcome"] == "APPROVE"
    assert Kind.INFO_REQUEST in [e.kind for e in res.history]
    assert "DOCUMENTATION_COLLECTED" in _pa(res)


def test_step_therapy_denial_is_appealed_and_overturned_with_pharmacy_consult():
    res = _run("humira_step_therapy_denied")
    assert res.final_state is State.DECIDE and res.stopped == "terminal"
    # the golden loop survives inside the richer pipeline (subsequence, not exact match)
    assert _is_subsequence(
        ["REQUEST_SUBMITTED", "FORMULARY_CHECKED", "DECISION_DENIED",
         "APPEAL_PACKET_ASSEMBLED", "DECISION_OVERTURNED"],
        _pa(res),
    )
    assert "payer.pharmacy" in _authors(res)  # drug case → pharmacy consulted
    denied = next(e for e in res.history if e.payload.get("pa_event") == "DECISION_DENIED")
    assert denied.payload["denial_reason"] == "STEP_THERAPY_NOT_MET"
    assert _final(res).payload["outcome"] == "APPROVE" and _final(res).payload.get("overturned") is True


def test_dx_mismatch_escalates_to_human_who_decides():
    res = _run("mri_lumbar_dx_mismatch")
    assert res.final_state is State.DECIDE
    assert "ESCALATED_TO_MD" in _pa(res)
    # the binding decision is the human Medical Director's (offline: labelled simulated)
    assert _final(res).author == "payer.medical_director"
    assert "simulated" in _final(res).payload.get("note", "").lower()


def test_dx_mismatch_pauses_for_human_in_the_loop():
    # With ARBITER as a pause state (the live HITL path), the run stops awaiting the human.
    res = _run("mri_lumbar_dx_mismatch", pause_states={State.ARBITER})
    assert res.stopped == "paused" and res.final_state is State.ARBITER
    assert "payer.medical_director" not in _authors(res)  # human hasn't decided yet


def test_emits_over_band_as_room_messages_only():
    tools = FakeAgentTools()
    res = _run("mri_lumbar_dx_mismatch", tools=tools)
    assert res.final_state is State.DECIDE
    tools.assert_message_sent(count=len(res.history))  # every move is a room message
    assert tools.events_sent == []


def test_narrator_runs_for_llm_roles_but_not_for_human():
    calls = []

    def fake_narrate(role_id, facts, kind, history):
        calls.append(role_id)
        return {"message": f"MSG[{role_id}]", "reasoning": "R"}

    res = _run("mri_lumbar_dx_mismatch", narrate=fake_narrate)
    assert {"payer.reviewer", "payer.guidelines", "payer.compliance"} <= set(calls)
    assert "payer.medical_director" not in calls  # human is never narrated
    reviewer_env = next(e for e in res.history if e.author == "payer.reviewer")
    assert reviewer_env.payload["message"] == "MSG[payer.reviewer]"
    md_env = _final(res)
    assert md_env.payload["message"] == md_env.payload["facts"]  # human uses deterministic text


def test_plan_is_pure_and_offline():
    st = AuthBridgeState(req=ALL_CASES["mri_lumbar_complete"]())
    p = plan(State.FRAME, st)
    assert p.role_id == "provider.intake" and p.next_state is State.PROPOSE
