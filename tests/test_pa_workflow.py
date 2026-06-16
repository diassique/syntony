"""Interactive PA workflow — orchestrator integration (offline).

Drives ``pa_workflow`` end to end against an in-memory SQLite control plane (no Band, no LLM
key → deterministic narration, no network). Verifies the run-status transitions, the audit
trail, and the cross-org attribution that the API depends on.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine, select

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())
os.environ.pop("AIML_API_KEY", None)  # force deterministic (no-network) narration

import control.db as cdb  # noqa: E402
import pa_workflow  # noqa: E402
from control import seed  # noqa: E402
from control.models import Event, Run  # noqa: E402


@pytest.fixture()
def orgs():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    cdb._engine = engine
    with cdb.session() as s:
        summary = seed.seed_demo(s)
    yield summary["provider"]["org_id"], summary["payer"]["org_id"]
    cdb._engine = None


def _form(**over):
    base = {
        "patient_ref": "synthetic-1", "member_id": "MBR-9", "health_plan": "Medicare Advantage",
        "procedure": {"system": "CPT", "code": "72148", "display": "MRI lumbar spine w/o contrast"},
        "diagnoses": [{"code": "M54.5", "display": "Low back pain"}],
        "clinical_justification": "6 weeks PT failed; persistent radiculopathy.",
        "supporting_docs": ["conservative_therapy_notes", "imaging_order"],
        "ordering_provider": {"npi": "1000000007", "name": "Dr X", "signed": True},
        "urgency": "routine",
    }
    base.update(over)
    return base


def _run(coro):
    return asyncio.run(coro)


def _events(run_id, org_id):
    with cdb.session() as s:
        return s.exec(select(Event).where(Event.run_id == run_id, Event.org_id == org_id)).all()


def test_submit_review_approve(orgs):
    provider_org, payer_org = orgs
    res = _run(pa_workflow.submit_request(_form(), submitter_org=provider_org))
    run_id = res["run_id"]
    assert res["status"] == "awaiting_payer"

    assert _run(pa_workflow.start_review(run_id))["status"] == "awaiting_payer_decision"
    assert _run(pa_workflow.decide(run_id, action="APPROVE"))["status"] == "succeeded"

    with cdb.session() as s:
        run = s.get(Run, run_id)
        assert run.outcome == "APPROVE" and run.mode == "interactive"
        assert run.workflow["side_to_org"] == {"provider": provider_org, "payer": payer_org}
    # both orgs see the room decision; the payer holds an APPROVE outcome
    assert any(e.payload.get("outcome") == "APPROVE" for e in _events(run_id, payer_org))
    assert any(e.payload.get("auth_number") for e in _events(run_id, provider_org))


def test_deny_then_appeal_overturns(orgs):
    provider_org, payer_org = orgs
    form = _form(procedure={"system": "HCPCS", "code": "J0135", "display": "Adalimumab (Humira)"},
                 diagnoses=[{"code": "M06.9", "display": "RA"}],
                 supporting_docs=["diagnosis_confirmation"])
    run_id = _run(pa_workflow.submit_request(form, submitter_org=provider_org))["run_id"]

    _run(pa_workflow.start_review(run_id))
    res = _run(pa_workflow.decide(run_id, action="DENY", reason_code="STEP_THERAPY_NOT_MET"))
    assert res["status"] == "awaiting_provider"  # appealable denial parks with the provider

    res = _run(pa_workflow.file_appeal(run_id, docs=["step_therapy_record"]))
    assert res["status"] == "awaiting_payer"      # reconsideration goes back to the payer

    _run(pa_workflow.start_review(run_id))
    res = _run(pa_workflow.decide(run_id, action="APPROVE"))
    assert res["status"] == "succeeded"
    with cdb.session() as s:
        assert s.get(Run, run_id).outcome == "APPROVE"
    assert any(e.payload.get("overturned") for e in _events(run_id, payer_org))


def test_pend_then_respond_approves(orgs):
    provider_org, _ = orgs
    run_id = _run(pa_workflow.submit_request(_form(supporting_docs=["imaging_order"]),
                                             submitter_org=provider_org))["run_id"]
    _run(pa_workflow.start_review(run_id))
    res = _run(pa_workflow.decide(run_id, action="REQUEST_INFO", reason_code="CONSERVATIVE_CARE_NOT_MET"))
    assert res["status"] == "awaiting_provider"

    res = _run(pa_workflow.respond_to_pend(run_id, docs=["conservative_therapy_notes"]))
    assert res["status"] == "awaiting_payer"
    _run(pa_workflow.start_review(run_id))
    assert _run(pa_workflow.decide(run_id, action="APPROVE"))["status"] == "succeeded"


def test_borderline_escalates_to_medical_director(orgs):
    provider_org, payer_org = orgs
    run_id = _run(pa_workflow.submit_request(
        _form(diagnoses=[{"code": "M79.1", "display": "Myalgia"}]), submitter_org=provider_org))["run_id"]
    _run(pa_workflow.start_review(run_id))
    res = _run(pa_workflow.decide(run_id, action="ESCALATE"))
    assert res["status"] == "awaiting_human"

    res = _run(pa_workflow.md_decide(run_id, outcome="APPROVE", note="approved on discretion"))
    assert res["status"] == "succeeded"
    with cdb.session() as s:
        assert s.get(Run, run_id).outcome == "APPROVE"
    assert any(e.payload.get("hitl") for e in _events(run_id, payer_org))


def test_action_preconditions_are_enforced(orgs):
    provider_org, _ = orgs
    run_id = _run(pa_workflow.submit_request(_form(), submitter_org=provider_org))["run_id"]
    # cannot decide before the payer has run the review
    with pytest.raises(ValueError):
        _run(pa_workflow.decide(run_id, action="APPROVE"))
    # cannot respond when nothing is pended
    with pytest.raises(ValueError):
        _run(pa_workflow.respond_to_pend(run_id, docs=[]))
