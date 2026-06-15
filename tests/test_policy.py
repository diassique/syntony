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
