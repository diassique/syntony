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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from control.api import get_session, router  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _session_override():
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = _session_override
    with TestClient(app) as c:
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
