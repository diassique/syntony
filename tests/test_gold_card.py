"""Gold carding (provider PA exemption; Texas HB 3459/3812). Offline (in-memory SQLite)."""

from __future__ import annotations

import asyncio
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine, select

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())
os.environ.pop("AIML_API_KEY", None)

import control.db as cdb  # noqa: E402
import pa_workflow  # noqa: E402
from control import seed, service  # noqa: E402
from control.models import Event, GoldCard, Run, RunMode, RunStatus  # noqa: E402


@pytest.fixture()
def orgs():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    cdb._engine = engine
    with cdb.session() as s:
        summary = seed.seed_demo(s)
    yield summary["provider"]["org_id"], summary["payer"]["org_id"]
    cdb._engine = None


def _form(npi="1000000007", code="72148"):
    return {
        "patient_ref": "p", "procedure": {"system": "CPT", "code": code, "display": "MRI"},
        "diagnoses": [{"code": "M54.5"}], "clinical_justification": "documented",
        "supporting_docs": ["conservative_therapy_notes", "imaging_order"],
        "ordering_provider": {"npi": npi, "name": "Dr Rivera", "signed": True},
    }


def test_seed_issues_a_gold_card(orgs):
    clinic, _ = orgs
    with cdb.session() as s:
        cards = service.list_gold_cards(s, org_id=clinic)
        assert any(c.provider_npi == "1000000007" and c.procedure_code == "72148" for c in cards)
        gc = service.active_gold_card(s, org_id=clinic, npi="1000000007", code="72148")
        assert gc is not None and gc.rate >= 0.9


def test_gold_carded_request_auto_approves_without_review(orgs):
    clinic, payer = orgs
    res = asyncio.run(pa_workflow.submit_request(_form(), submitter_org=clinic))
    assert res["status"] == "succeeded" and res["outcome"] == "APPROVE" and res.get("gold_card") is True
    with cdb.session() as s:
        run = s.get(Run, res["run_id"])
        assert run.outcome == "APPROVE" and run.turns == 1  # one decision, no review round-trip
        evs = s.exec(select(Event).where(Event.run_id == run.id, Event.org_id == payer)).all()
        assert any(e.payload.get("pa_event") == "GOLD_CARD_EXEMPTION" for e in evs)
        # no UM-review consult turns happened
        assert not any(e.payload.get("pa_event", "").startswith("CONSULT") for e in evs)


def test_non_gold_carded_service_takes_the_normal_path(orgs):
    clinic, _ = orgs
    # MRI knee (73721) is not gold-carded → normal flow, parks for the payer
    res = asyncio.run(pa_workflow.submit_request(_form(code="73721"), submitter_org=clinic))
    assert res["status"] == "awaiting_payer"


def test_recompute_derives_a_card_from_approval_history(orgs):
    clinic, _ = orgs
    npi, code = "9999999999", "73721"
    with cdb.session() as s:
        for i in range(6):
            run = service.start_run(s, org_id=clinic, case_name="knee")
            run.mode = RunMode.INTERACTIVE.value
            run.status = RunStatus.SUCCEEDED.value
            run.outcome = "APPROVE" if i < 6 else "DENY"
            run.workflow = {"state": {"req": {"ordering_provider": {"npi": npi, "name": "Dr Knee"},
                                              "procedure": {"code": code, "display": "MRI knee"}}}}
            s.add(run)
        s.commit()
        created = service.recompute_gold_cards(s, org_id=clinic)
        assert created == 1
        assert service.active_gold_card(s, org_id=clinic, npi=npi, code=code) is not None


def test_recompute_skips_below_threshold(orgs):
    clinic, _ = orgs
    npi, code = "8888888888", "70551"
    with cdb.session() as s:
        for _ in range(3):  # only 3 decided → below the 5-request minimum
            run = service.start_run(s, org_id=clinic, case_name="brain")
            run.mode = RunMode.INTERACTIVE.value
            run.status = RunStatus.SUCCEEDED.value
            run.outcome = "APPROVE"
            run.workflow = {"state": {"req": {"ordering_provider": {"npi": npi},
                                              "procedure": {"code": code}}}}
            s.add(run)
        s.commit()
        assert service.recompute_gold_cards(s, org_id=clinic) == 0
        assert service.active_gold_card(s, org_id=clinic, npi=npi, code=code) is None
