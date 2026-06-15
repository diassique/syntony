"""Tests for the org-scoped audit persistence (control/ingest.py).

The invariant under test is the privacy moat: when a cross-org negotiation is persisted,
each org's audit trail shows every room message but only that org's own private reasoning —
never the counterparty's. Offline on in-memory SQLite.
"""

import os
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())

from control import ingest, service  # noqa: E402
from control.models import Event, Organization, UsageRecord  # noqa: E402


def _env(turn, author, kind, message, reasoning, outcome=None, pa_event=None, denial_reason=None):
    payload = {"message": message, "reasoning": reasoning}
    for k, v in (("outcome", outcome), ("pa_event", pa_event), ("denial_reason", denial_reason)):
        if v:
            payload[k] = v
    return SimpleNamespace(turn=turn, author=author, kind=SimpleNamespace(value=kind), payload=payload)


def _result():
    return SimpleNamespace(
        stopped="terminal",
        final_state=SimpleNamespace(value="DECIDE"),
        turns=2,
        history=[
            _env(0, "provider.counsel", "PROPOSAL", "Submitting the request.", "CLINIC_SECRET_STRATEGY",
                 pa_event="REQUEST_SUBMITTED"),
            _env(1, "payer.reviewer", "DECISION", "Approved.", "PAYER_SECRET_STRATEGY", outcome="APPROVE",
                 pa_event="DECISION_APPROVED"),
        ],
    )


def _author_side(author: str) -> str:
    return "payer" if author.startswith("payer") else "provider"


@pytest.fixture()
def sess():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _events_for(sess, org_id):
    return sess.exec(select(Event).where(Event.org_id == org_id)).all()


def test_room_messages_go_to_both_orgs_private_reasoning_stays_with_author(sess):
    clinic = Organization(name="Clinic", slug="clinic"); payer = Organization(name="Payer", slug="payer")
    sess.add(clinic); sess.add(payer); sess.commit(); sess.refresh(clinic); sess.refresh(payer)

    run = ingest.persist_result(
        sess, result=_result(), side_to_org={"provider": clinic.id, "payer": payer.id},
        author_side=_author_side, case_name="demo_case", room_id="room-xyz", urgency="expedited",
    )

    clinic_events = _events_for(sess, clinic.id)
    payer_events = _events_for(sess, payer.id)

    # PA audit semantics + SLA tier carried through
    assert run.urgency == "expedited"
    room_pa_events = {e.payload.get("pa_event") for e in clinic_events if e.visibility == "room"}
    assert room_pa_events == {"REQUEST_SUBMITTED", "DECISION_APPROVED"}

    # Both orgs see both room messages.
    for events in (clinic_events, payer_events):
        room = [e for e in events if e.visibility == "room"]
        assert {e.payload["message"] for e in room} == {"Submitting the request.", "Approved."}

    # Each org sees ONLY its own private reasoning.
    clinic_private = [e for e in clinic_events if e.visibility == "private_event"]
    payer_private = [e for e in payer_events if e.visibility == "private_event"]
    assert [e.payload["reasoning"] for e in clinic_private] == ["CLINIC_SECRET_STRATEGY"]
    assert [e.payload["reasoning"] for e in payer_private] == ["PAYER_SECRET_STRATEGY"]

    # The moat: the counterparty's secret never appears in my audit at all.
    assert all("PAYER_SECRET_STRATEGY" not in str(e.payload) for e in clinic_events)
    assert all("CLINIC_SECRET_STRATEGY" not in str(e.payload) for e in payer_events)

    # Run finished, decision captured, and metered per org.
    assert run.status == "succeeded" and run.final_state == "DECIDE" and run.turns == 2
    assert run.outcome == "APPROVE"  # last envelope carrying an outcome
    assert len(sess.exec(select(UsageRecord)).all()) == 2  # one run row per org


def test_room_outcome_is_preserved_for_both(sess):
    clinic = Organization(name="Clinic", slug="clinic"); payer = Organization(name="Payer", slug="payer")
    sess.add(clinic); sess.add(payer); sess.commit(); sess.refresh(clinic); sess.refresh(payer)
    ingest.persist_result(sess, result=_result(), side_to_org={"provider": clinic.id, "payer": payer.id},
                          author_side=_author_side, case_name="c", room_id=None)
    for org in (clinic, payer):
        decided = [e for e in _events_for(sess, org.id) if e.payload.get("outcome") == "APPROVE"]
        assert len(decided) == 1


def test_streaming_record_envelope_matches_batch_persist(sess):
    """The live "Run a case" path records each envelope as it lands via record_envelope; it must
    produce the same audit rows as the batch persist_result (so live and replayed runs agree)."""
    clinic = Organization(name="Clinic", slug="clinic"); payer = Organization(name="Payer", slug="payer")
    sess.add(clinic); sess.add(payer); sess.commit(); sess.refresh(clinic); sess.refresh(payer)
    side_to_org = {"provider": clinic.id, "payer": payer.id}
    org_ids = [clinic.id, payer.id]

    # Stream turn-by-turn into a freshly created RUNNING run (the live path).
    run = service.start_run(sess, org_id=clinic.id, case_name="streamed")
    for env in _result().history:
        ingest.record_envelope(sess, run=run, env=env, org_ids=org_ids,
                               side_to_org=side_to_org, author_side=_author_side)

    clinic_events = _events_for(sess, clinic.id)
    payer_events = _events_for(sess, payer.id)
    # same room/private distribution as the batch test
    assert {e.payload["message"] for e in clinic_events if e.visibility == "room"} == {"Submitting the request.", "Approved."}
    assert [e.payload["reasoning"] for e in clinic_events if e.visibility == "private_event"] == ["CLINIC_SECRET_STRATEGY"]
    assert [e.payload["reasoning"] for e in payer_events if e.visibility == "private_event"] == ["PAYER_SECRET_STRATEGY"]
    # moat holds under streaming too
    assert all("PAYER_SECRET_STRATEGY" not in str(e.payload) for e in clinic_events)
