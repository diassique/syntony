"""Interactive PA workflow — the two-sided, form-driven flow (domain level, no DB/Band/LLM).

Drives the FSM in segments exactly as the orchestrator does, simulating each human action by
mutating the working state between segments. Asserts the case pauses at every court-change and
reaches the right determination. Deterministic: ``narrate=None``, ``tools_for=None``.
"""

from __future__ import annotations

import asyncio

from domains.authbridge import workflow as wf
from protocol import State


def _run(st, start):
    """Run one segment from ``start`` (pauses at ARBITER; ``no_move`` at other court-changes)."""
    return asyncio.run(wf.run_segment(st, start_state=start, case_id="pa-test"))


def _last_outcome(history):
    return next((e.payload.get("outcome") for e in reversed(history) if e.payload.get("outcome")), None)


# ---- form → request + precheck -------------------------------------------------

def test_build_request_infers_system_and_validates():
    req = wf.build_request({
        "patient_ref": "p1", "member_id": "MBR-1", "health_plan": "Medicare Advantage", "units": 2,
        "procedure": {"code": "j0135"},  # lowercase, system omitted → inferred HCPCS, upper-cased
        "diagnoses": [{"code": "m06.9", "display": "RA"}],
        "clinical_justification": "biologic indicated",
        "supporting_docs": ["diagnosis_confirmation"],
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True},
        "urgency": "routine",
    })
    assert req.procedure.system == "HCPCS" and req.procedure.code == "J0135"
    assert req.diagnoses[0].code == "M06.9" and req.units == 2 and req.member_id == "MBR-1"


def test_precheck_flags_blocking_and_advisory_gaps():
    # blank code + no dx + unsigned + empty justification → blocking; not ready.
    bad = wf.build_request({"patient_ref": "p", "procedure": {"system": "CPT", "code": "999"},
                            "ordering_provider": {"npi": "1", "name": "Dr", "signed": False}})
    rep = wf.precheck(bad)
    assert rep["ready"] is False
    assert any("5-digit" in i for i in rep["coding_issues"])
    assert rep["completeness_issues"]  # missing dx / signature / justification

    # structurally fine MRI but missing the conservative-care notes → advisory PEND, still ready.
    ok = wf.build_request({"patient_ref": "p", "procedure": {"system": "CPT", "code": "72148"},
                           "diagnoses": [{"code": "M54.5"}], "clinical_justification": "PT failed",
                           "supporting_docs": ["imaging_order"],
                           "ordering_provider": {"npi": "1", "name": "Dr", "signed": True}})
    rep = wf.precheck(ok)
    assert rep["ready"] is True and rep["missing_required_docs"] == ["conservative_therapy_notes"]
    assert any("pended" in a.lower() for a in rep["advisories"])


# ---- the happy path: submit → payer opens → approve ----------------------------

def _complete_mri():
    return wf.new_state(wf.build_request({
        "patient_ref": "p1", "procedure": {"system": "CPT", "code": "72148"},
        "diagnoses": [{"code": "M54.5"}], "clinical_justification": "6 wks PT failed; radiculopathy",
        "supporting_docs": ["conservative_therapy_notes", "imaging_order"],
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True}}))


def test_submit_parks_in_payer_worklist_then_approves():
    st = _complete_mri()
    r = _run(st, State.FRAME)
    assert r.stopped == "no_move" and r.final_state is State.REVIEW
    assert st.submitted and not st.payer_review_started  # AWAITING_PAYER

    st.payer_review_started = True
    r = _run(st, State.REVIEW)
    assert r.stopped == "no_move" and r.final_state is State.REVIEW  # AWAITING_PAYER_DECISION
    assert st.recommendation["outcome"] == "APPROVE" and st.payer_action is None

    st.payer_action = "APPROVE"
    r = _run(st, State.REVIEW)
    assert r.stopped == "terminal" and r.final_state is State.DECIDE
    assert _last_outcome(r.history) == "APPROVE" and st.auth_number.startswith("AUTH-")


# ---- deny → appeal → overturn (the golden scenario, now genuinely data-driven) --

def test_step_therapy_denied_then_appealed_and_overturned():
    st = wf.new_state(wf.build_request({
        "patient_ref": "p2", "procedure": {"system": "HCPCS", "code": "J0135"},
        "diagnoses": [{"code": "M06.9"}], "clinical_justification": "moderate-severe RA",
        "supporting_docs": ["diagnosis_confirmation"],  # NB: no step_therapy_record
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True}}))

    _run(st, State.FRAME)                       # → AWAITING_PAYER
    st.payer_review_started = True
    r = _run(st, State.REVIEW)                  # consults incl pharmacy → recommendation
    assert st.pharmacy_done and st.recommendation["reason_code"] == "STEP_THERAPY_NOT_MET"

    st.payer_action = "DENY"
    st.payer_action_reason = "STEP_THERAPY_NOT_MET"
    r = _run(st, State.REVIEW)                  # appealable deny → REVISE, awaiting provider
    assert r.stopped == "no_move" and r.final_state is State.REVISE
    assert _last_outcome(r.history) == "DENY"

    st.provider_appeal_ready = True
    st.new_docs = ("step_therapy_record",)      # the provider supplies the curing doc
    r = _run(st, State.REVISE)                  # appeal cures + resubmits → back to AWAITING_PAYER
    assert r.final_state is State.REVIEW and st.appealed and not st.payer_review_started
    assert "step_therapy_record" in st.req.supporting_docs

    st.payer_review_started = True
    r = _run(st, State.REVIEW)                  # reconsideration → now APPROVE recommended
    assert st.recommendation["outcome"] == "APPROVE"
    st.payer_action = "APPROVE"
    r = _run(st, State.REVIEW)
    assert r.stopped == "terminal" and _last_outcome(r.history) == "APPROVE"
    assert any(e.payload.get("overturned") for e in r.history)


# ---- pend → provider responds → approve ----------------------------------------

def test_pend_for_info_then_provider_responds_and_approves():
    st = wf.new_state(wf.build_request({
        "patient_ref": "p3", "procedure": {"system": "CPT", "code": "72148"},
        "diagnoses": [{"code": "M54.5"}], "clinical_justification": "low back pain",
        "supporting_docs": ["imaging_order"],  # missing conservative_therapy_notes
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True}}))

    _run(st, State.FRAME)
    st.payer_review_started = True
    r = _run(st, State.REVIEW)
    assert st.recommendation["outcome"] == "REQUEST_INFO"

    st.payer_action = "REQUEST_INFO"
    r = _run(st, State.REVIEW)                  # pend → INFO, awaiting provider
    assert r.stopped == "no_move" and r.final_state is State.INFO

    st.provider_response_ready = True
    st.new_docs = ("conservative_therapy_notes",)
    r = _run(st, State.INFO)                     # provider answers → back to AWAITING_PAYER
    assert r.final_state is State.REVIEW and not st.payer_review_started
    assert "conservative_therapy_notes" in st.req.supporting_docs

    st.payer_review_started = True
    _run(st, State.REVIEW)
    assert st.recommendation["outcome"] == "APPROVE"
    st.payer_action = "APPROVE"
    r = _run(st, State.REVIEW)
    assert r.stopped == "terminal" and _last_outcome(r.history) == "APPROVE"


# ---- borderline → escalate → pause for the human Medical Director --------------

def test_borderline_escalates_and_pauses_for_medical_director():
    st = wf.new_state(wf.build_request({
        "patient_ref": "p4", "procedure": {"system": "CPT", "code": "72148"},
        "diagnoses": [{"code": "M79.1"}], "clinical_justification": "myalgia",  # dx mismatch
        "supporting_docs": ["conservative_therapy_notes", "imaging_order"],
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True}}))

    _run(st, State.FRAME)
    st.payer_review_started = True
    r = _run(st, State.REVIEW)
    assert st.recommendation["escalate"] is True and st.recommendation["suggested_action"] == "ESCALATE"

    st.payer_action = "ESCALATE"
    r = _run(st, State.REVIEW)                  # → ESCALATE → ARBITER, paused for the MD
    assert r.stopped == "paused" and r.final_state is State.ARBITER


# ---- state survives a serialize / resume round-trip ----------------------------

def test_state_roundtrips_through_dump_and_load():
    st = _complete_mri()
    _run(st, State.FRAME)
    st.payer_review_started = True
    _run(st, State.REVIEW)  # consults done, recommendation present
    revived = wf.load_state(wf.dump_state(st))
    assert revived.submitted and revived.guidelines_done and revived.payer_review_started
    assert revived.recommendation == st.recommendation
    assert revived.req.procedure.code == "72148"
    # the revived state continues correctly
    revived.payer_action = "APPROVE"
    r = _run(revived, State.REVIEW)
    assert r.stopped == "terminal" and _last_outcome(r.history) == "APPROVE"
