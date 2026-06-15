"""Policy reason-code coverage: every adverse outcome carries a canonical, machine-typed
DenialReason (the CMS-0057-F "specific reason" contract the Appeals agent acts on)."""

from domains.authbridge.cases import ALL_CASES
from domains.authbridge.policy import DenialReason, Outcome, necessity_decision


def test_complete_case_approves_with_no_reason_code():
    d = necessity_decision(ALL_CASES["mri_lumbar_complete"]())
    assert d.outcome is Outcome.APPROVE and d.reason_code is None


def test_missing_conservative_care_is_typed():
    d = necessity_decision(ALL_CASES["mri_lumbar_missing_docs"]())
    assert d.outcome is Outcome.REQUEST_INFO
    assert d.reason_code is DenialReason.CONSERVATIVE_CARE_NOT_MET


def test_dx_mismatch_is_not_medically_necessary_and_escalates():
    d = necessity_decision(ALL_CASES["mri_lumbar_dx_mismatch"]())
    assert d.outcome is Outcome.DENY and d.escalate
    assert d.reason_code is DenialReason.NOT_MEDICALLY_NECESSARY


def test_step_therapy_is_a_hard_appealable_denial():
    d = necessity_decision(ALL_CASES["humira_step_therapy_denied"]())
    assert d.outcome is Outcome.DENY and d.escalate is False  # hard deny, but appealable
    assert d.reason_code is DenialReason.STEP_THERAPY_NOT_MET


def test_red_flag_emergent_case_approves_without_conservative_care():
    """Cauda equina (G83.4) is a surgical red flag → approve emergently even though the usual
    conservative-care notes are absent (an emergency is never pended for paperwork)."""
    req = ALL_CASES["cauda_equina_urgent"]()
    assert "conservative_therapy_notes" not in req.supporting_docs  # docs absent on purpose
    d = necessity_decision(req)
    assert d.outcome is Outcome.APPROVE and d.reason_code is None
    assert req.urgency.value == "urgent"  # → expedited 72h SLA tier in the audit
