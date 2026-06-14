"""Tests for the control-plane HTTP API (control/api.py).

Offline: a fresh in-memory SQLite DB per test (StaticPool so all connections share it),
the FastAPI auth router mounted on a bare app, and the per-request session dependency
overridden to that engine. Exercises the signup/login/me surface end to end.
"""

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("SYNTONY_COOKIE_SECURE", "0")  # TestClient speaks http; allow the cookie

from types import SimpleNamespace  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from control import ingest  # noqa: E402
from control.api import get_session, router, runs_router  # noqa: E402


def _make_app(engine):
    def _session_override():
        with Session(engine) as s:
            yield s
    app = FastAPI()
    app.include_router(router)
    app.include_router(runs_router)
    app.dependency_overrides[get_session] = _session_override
    return app


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with TestClient(_make_app(engine)) as c:
        yield c


def _signup(client, email="ada@example.com", password="hunter2hunter", **kw):
    return client.post("/api/auth/signup", json={"email": email, "password": password, **kw})


def test_signup_returns_token_user_and_org(client):
    r = _signup(client, name="Ada", org_name="Acme")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"]
    assert body["user"]["email"] == "ada@example.com" and body["user"]["name"] == "Ada"
    assert body["org"]["name"] == "Acme" and body["org"]["plan"] == "free" and body["org"]["slug"]


def test_signup_normalizes_email_and_rejects_duplicates(client):
    assert _signup(client, email="Ada@Example.com").status_code == 201
    dup = _signup(client, email="ada@example.com")  # same address, different case
    assert dup.status_code == 409


def test_signup_validates_email_and_password(client):
    assert _signup(client, email="not-an-email").status_code == 422
    assert _signup(client, password="short").status_code == 422  # < 8 chars


def test_login_succeeds_and_rejects_bad_password(client):
    _signup(client)
    ok = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "hunter2hunter"})
    assert ok.status_code == 200 and ok.json()["token"]
    assert ok.json()["org"] is not None  # token is org-scoped
    bad = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope"})
    assert bad.status_code == 401


def test_me_requires_a_valid_bearer_token(client):
    token = _signup(client).json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "ada@example.com"
    assert me.json()["org"]["slug"]  # resolved from the user's membership

    assert client.get("/api/auth/me").status_code == 401  # missing token
    assert client.get("/api/auth/me",
                      headers={"Authorization": "Bearer garbage"}).status_code == 401  # invalid token


# ---- refresh / rotation / revoke ----------------------------------------------
def test_signup_sets_refresh_cookie(client):
    r = _signup(client)
    assert r.status_code == 201
    assert client.cookies.get('syntony_refresh')  # httpOnly refresh cookie issued
    assert r.json()['expires_in'] > 0


def test_refresh_rotates_token_and_logout_revokes(client):
    _signup(client)  # sets the refresh cookie in the client jar
    first = client.cookies.get('syntony_refresh')

    r1 = client.post('/api/auth/refresh')
    assert r1.status_code == 200 and r1.json()['token']
    rotated = client.cookies.get('syntony_refresh')
    assert rotated and rotated != first  # rotation: a new refresh token each time

    # the new access token actually works
    assert client.get('/api/auth/me', headers={'Authorization': f"Bearer {r1.json()['token']}"}).status_code == 200

    # logout revokes server-side; a subsequent refresh is rejected
    assert client.post('/api/auth/logout').status_code == 204
    client.cookies.set('syntony_refresh', rotated)  # even presenting the (revoked) token fails
    assert client.post('/api/auth/refresh').status_code == 401


def test_refresh_without_cookie_is_unauthorized(client):
    assert client.post('/api/auth/refresh').status_code == 401


# ---- org-scoped run audit ------------------------------------------------------
def _env(turn, author, kind, message, reasoning, outcome=None):
    payload = {"message": message, "reasoning": reasoning}
    if outcome:
        payload["outcome"] = outcome
    return SimpleNamespace(turn=turn, author=author, kind=SimpleNamespace(value=kind), payload=payload)


def test_run_audit_is_scoped_to_the_callers_org():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with TestClient(_make_app(engine)) as c:
        clinic = c.post("/api/auth/signup", json={"email": "c@x.com", "password": "clinicpass1"}).json()
        payer = c.post("/api/auth/signup", json={"email": "p@x.com", "password": "payerpass12"}).json()

        result = SimpleNamespace(
            stopped="terminal", final_state=SimpleNamespace(value="DECIDE"), turns=2,
            history=[
                _env(0, "provider.counsel", "PROPOSAL", "Submitting.", "CLINIC_SECRET"),
                _env(1, "payer.reviewer", "DECISION", "Approved.", "PAYER_SECRET", outcome="APPROVE"),
            ],
        )
        with Session(engine) as s:
            ingest.persist_result(
                s, result=result,
                side_to_org={"provider": clinic["org"]["id"], "payer": payer["org"]["id"]},
                author_side=lambda a: "payer" if a.startswith("payer") else "provider",
                case_name="mri_case", room_id="room-1",
            )

        clinic_h = {"Authorization": f"Bearer {clinic['token']}"}
        payer_h = {"Authorization": f"Bearer {payer['token']}"}

        # both orgs see the one shared run, with 2 room messages each
        c_runs = c.get("/api/runs", headers=clinic_h).json()
        p_runs = c.get("/api/runs", headers=payer_h).json()
        assert len(c_runs) == 1 and len(p_runs) == 1
        assert c_runs[0]["events"] == 2 and c_runs[0]["private_events"] == 1
        run_id = c_runs[0]["id"]

        c_detail = c.get(f"/api/runs/{run_id}", headers=clinic_h).json()
        p_detail = c.get(f"/api/runs/{run_id}", headers=payer_h).json()
        c_blob, p_blob = str(c_detail), str(p_detail)

        # the moat, through the API: each side sees only its own private reasoning
        assert "CLINIC_SECRET" in c_blob and "PAYER_SECRET" not in c_blob
        assert "PAYER_SECRET" in p_blob and "CLINIC_SECRET" not in p_blob
        # both still see the public room messages and the decision
        assert "Submitting." in c_blob and "Approved." in c_blob

        # unauthenticated access is refused
        assert c.get("/api/runs").status_code == 401
