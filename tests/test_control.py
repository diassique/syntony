"""Tests for the control plane (auth, API keys, encrypted credentials, runs/audit/usage).

Offline: an in-memory SQLite DB (StaticPool so all connections share it). Verifies the
platform foundation without a live Postgres.
"""

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())

from control import security, service  # noqa: E402
from control.models import (  # noqa: E402
    CredentialKind,
    Event,
    Membership,
    MemberRole,
    RunStatus,
    UsageRecord,
)


@pytest.fixture()
def sess():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_signup_creates_user_org_and_owner_membership(sess):
    user, org = service.signup(sess, email="a@b.com", password="pw123456", name="Al")
    assert user.email == "a@b.com" and org.id
    m = sess.exec(select(Membership).where(Membership.user_id == user.id)).first()
    assert m is not None and m.org_id == org.id and m.role == MemberRole.OWNER.value


def test_password_is_hashed_not_plaintext(sess):
    user, _ = service.signup(sess, email="a@b.com", password="secret123")
    assert "secret123" not in user.password_hash
    assert user.password_hash.startswith("$argon2")


def test_duplicate_email_is_rejected(sess):
    service.signup(sess, email="a@b.com", password="pw123456")
    with pytest.raises(service.AuthError):
        service.signup(sess, email="a@b.com", password="other123")


def test_login_issues_scoped_token_and_rejects_bad_password(sess):
    user, org = service.signup(sess, email="a@b.com", password="secret123")
    assert service.login(sess, email="a@b.com", password="wrong") is None
    res = service.login(sess, email="a@b.com", password="secret123")
    assert res is not None
    got_user, token = res
    claims = security.verify_token(token)
    assert claims and claims["sub"] == got_user.id and claims["org"] == org.id


def test_api_key_verify_and_revoke(sess):
    _, org = service.signup(sess, email="a@b.com", password="pw123456")
    full, rec = service.create_api_key(sess, org_id=org.id, name="ci")
    assert full.startswith("syn_") and rec.prefix == full[:12]
    assert service.verify_api_key(sess, full).id == rec.id
    assert service.verify_api_key(sess, "syn_not_a_real_key") is None
    rec.revoked_at = service._now()
    sess.add(rec)
    sess.commit()
    assert service.verify_api_key(sess, full) is None  # revoked keys don't verify


def test_credentials_encrypted_at_rest(sess):
    _, org = service.signup(sess, email="a@b.com", password="pw123456")
    cred = service.store_credential(
        sess, org_id=org.id, kind=CredentialKind.LLM_PROVIDER.value, label="aiml", secret="sk-super-secret"
    )
    assert "sk-super-secret" not in cred.ciphertext          # not stored in the clear
    assert service.reveal_credential(cred) == "sk-super-secret"  # decryptable for use


def test_run_audit_trail_and_usage_metering(sess):
    _, org = service.signup(sess, email="a@b.com", password="pw123456")
    run = service.start_run(sess, org_id=org.id, case_name="mri_lumbar_dx_mismatch")
    assert run.status == RunStatus.RUNNING.value
    service.record_event(sess, run=run, turn=0, author="provider.intake", kind="CASE_OPEN",
                         visibility="room", payload={"message": "opening"})
    service.record_event(sess, run=run, turn=1, author="payer.medical_director", kind="DECISION",
                         visibility="room", payload={"outcome": "APPROVE"})
    service.record_usage(sess, org_id=org.id, run_id=run.id, kind="llm_call",
                         model="claude-haiku-4-5-20251001", input_tokens=16, output_tokens=8)
    service.finish_run(sess, run=run, final_state="DECIDE", turns=2)

    events = sess.exec(select(Event).where(Event.run_id == run.id)).all()
    assert len(events) == 2 and {e.kind for e in events} == {"CASE_OPEN", "DECISION"}
    assert run.status == RunStatus.SUCCEEDED.value and run.final_state == "DECIDE"
    usage = sess.exec(select(UsageRecord).where(UsageRecord.org_id == org.id)).all()
    assert sum(u.input_tokens for u in usage) == 16
