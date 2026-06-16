"""Synthetic patient charts (EHR layer) — seeding, chart queries, org isolation, and the
chart→request linkage that makes eligibility cite real Coverage. Offline (in-memory SQLite)."""

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
from control.models import Event, Patient, Run  # noqa: E402


@pytest.fixture()
def ctx():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    cdb._engine = engine
    with cdb.session() as s:
        summary = seed.seed_demo(s)
    yield summary["provider"]["org_id"], summary["payer"]["org_id"]
    cdb._engine = None


def test_seed_creates_a_curated_roster(ctx):
    clinic_org, _ = ctx
    with cdb.session() as s:
        roster = service.list_patients(s, org_id=clinic_org)
        assert len(roster) == 8
        p = next(x for x in roster if x.mrn == "NS-100003")  # Diane Foster — Humira/step-therapy
        assert service.patient_coverage(s, p.id).plan_type == "Commercial"
        tokens = {t.doc_token for t in service.patient_treatments(s, p.id)}
        assert "step_therapy_record" in tokens and "tb_hepb_screening" in tokens
        assert any(c.code == "M06.9" for c in service.patient_conditions(s, p.id))


def test_chart_is_org_scoped(ctx):
    clinic_org, payer_org = ctx
    with cdb.session() as s:
        pid = service.list_patients(s, org_id=clinic_org)[0].id
        assert service.get_patient(s, org_id=clinic_org, patient_id=pid) is not None
        assert service.get_patient(s, org_id=payer_org, patient_id=pid) is None  # tenant isolation
        assert service.list_patients(s, org_id=payer_org) == []


def _by_mrn(org_id, mrn):
    with cdb.session() as s:
        return service.list_patients(s, org_id=org_id), next(
            p for p in service.list_patients(s, org_id=org_id) if p.mrn == mrn)


def test_submit_from_patient_links_run_and_cites_real_coverage(ctx):
    clinic_org, _ = ctx
    with cdb.session() as s:
        maria = next(p for p in service.list_patients(s, org_id=clinic_org) if p.mrn == "NS-100001")
        pid = maria.id
    form = {
        "patient_ref": maria.mrn, "urgency": "routine",
        "procedure": {"system": "CPT", "code": "72148", "display": "MRI lumbar spine w/o contrast"},
        "diagnoses": [{"code": "M54.5", "display": "Low back pain"}],
        "clinical_justification": "8 wks PT failed; radiculopathy",
        "supporting_docs": ["conservative_therapy_notes", "imaging_order"],
        "ordering_provider": {"npi": "1000000007", "name": "Dr Rivera", "signed": True},
    }
    res = asyncio.run(pa_workflow.submit_request(form, submitter_org=clinic_org, patient_id=pid))
    run_id = res["run_id"]
    with cdb.session() as s:
        run = s.get(Run, run_id)
        assert run.patient_id == pid
        evs = s.exec(select(Event).where(Event.run_id == run_id, Event.author == "provider.eligibility")).all()
        # the eligibility step cites the patient's real Coverage (270/271-style)
        assert any("MA1029384701" in (e.payload.get("message") or "") for e in evs)


def test_submit_rejects_an_unknown_patient(ctx):
    clinic_org, _ = ctx
    form = {"procedure": {"system": "CPT", "code": "72148"},
            "diagnoses": [{"code": "M54.5"}], "clinical_justification": "x",
            "supporting_docs": ["conservative_therapy_notes"],
            "ordering_provider": {"npi": "1", "name": "Dr", "signed": True}}
    with pytest.raises(ValueError):  # patient not on this org's roster
        asyncio.run(pa_workflow.submit_request(form, submitter_org=clinic_org, patient_id="does-not-exist"))
