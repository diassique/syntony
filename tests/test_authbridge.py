"""Tests for the AuthBridge domain pack: schema validation, completeness checks,
and the necessity decision across all policy paths. Pure logic, no Band, no LLM.
"""

from domains.authbridge import cases
from domains.authbridge.policy import Outcome, completeness_issues, necessity_decision
from domains.authbridge.schema import PriorAuthRequest


def test_cases_are_valid_payloads():
    for name, factory in cases.ALL_CASES.items():
        req = factory()
        assert isinstance(req, PriorAuthRequest)
        # round-trips through the opaque-dict form the protocol uses
        assert PriorAuthRequest.model_validate(req.model_dump()) == req


def test_completeness_catches_missing_code_and_signature():
    issues = completeness_issues(cases.mri_lumbar_raw_intake())
    joined = " ".join(issues).lower()
    assert "cpt" in joined and "signature" in joined
    # the fully-formed case has no issues
    assert completeness_issues(cases.mri_lumbar_complete()) == []


def test_necessity_approve():
    d = necessity_decision(cases.mri_lumbar_complete())
    assert d.outcome is Outcome.APPROVE and not d.escalate


def test_necessity_request_info_when_docs_missing():
    d = necessity_decision(cases.mri_lumbar_missing_docs())
    assert d.outcome is Outcome.REQUEST_INFO
    assert any("documentation" in r.lower() for r in d.reasons)


def test_necessity_dx_mismatch_denies_and_escalates():
    d = necessity_decision(cases.mri_lumbar_dx_mismatch())
    assert d.outcome is Outcome.DENY and d.escalate is True


def test_unknown_procedure_requests_info():
    req = cases.mri_lumbar_complete()
    req.procedure.code = "99999"
    d = necessity_decision(req)
    assert d.outcome is Outcome.REQUEST_INFO
