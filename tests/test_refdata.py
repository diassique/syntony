"""Reference catalogs (doc types, procedures) seeded from code, served from the DB."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

os.environ.setdefault("SYNTONY_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SYNTONY_FERNET_KEY", Fernet.generate_key().decode())

import control.db as cdb  # noqa: E402
from control import seed, service  # noqa: E402
from domains.authbridge.workflow import SUPPORTING_DOC_TYPES, KNOWN_PROCEDURES  # noqa: E402


@pytest.fixture()
def sess():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    cdb._engine = engine
    with cdb.session() as s:
        yield s
    cdb._engine = None


def test_seed_refdata_populates_and_is_idempotent(sess):
    first = seed.seed_refdata(sess)
    assert first["doc_types"] == len(SUPPORTING_DOC_TYPES)
    assert first["procedures"] == len(KNOWN_PROCEDURES)
    again = seed.seed_refdata(sess)  # idempotent — nothing new the second time
    assert again == {"doc_types": 0, "procedures": 0, "criteria": 0, "policy_rules": 0}


def test_agent_cast_seeds_into_agentconfig_and_serves_from_db(sess):
    from domains.authbridge.roles import ROLES
    summary = seed.seed_demo(sess)
    provider_org = summary["provider"]["org_id"]
    cfgs = service.list_agent_configs(sess, org_id=provider_org)
    assert {c.role_id for c in cfgs} == set(ROLES)
    md = next(c for c in cfgs if c.role_id == "payer.medical_director")
    assert md.framework == "human" and md.extra.get("human") is True
    assert "acts_in" in md.extra


def test_policy_loads_from_db_and_matches_the_constant(sess):
    from domains.authbridge.policy import POLICY_TABLE
    seed.seed_refdata(sess)
    policy = service.load_policy(sess)
    assert set(policy) == set(POLICY_TABLE)
    # the J0135 step-therapy rule round-trips through the DB
    assert policy["J0135"].step_therapy_docs == POLICY_TABLE["J0135"].step_therapy_docs
    assert policy["72148"].red_flag_prefixes == POLICY_TABLE["72148"].red_flag_prefixes


def test_catalogs_served_from_db_match_the_seed(sess):
    seed.seed_refdata(sess)
    tokens = {d.token for d in service.list_doc_types(sess)}
    assert tokens == {d["id"] for d in SUPPORTING_DOC_TYPES}
    codes = [p.code for p in service.list_procedures(sess)]
    assert codes == [p["code"] for p in KNOWN_PROCEDURES]  # sort_order preserved


def test_criteria_corpus_seeds_and_retrieves_from_db(sess, monkeypatch):
    from domains.authbridge.criteria import CRITERIA, retrieve
    seed.seed_refdata(sess)
    corpus = service.criteria_corpus(sess)
    assert [c["id"] for c in corpus] == [c["id"] for c in CRITERIA]

    # offline embedding stub: identical text → identical vector (cosine 1)
    def fake_embed(x):
        items = x if isinstance(x, list) else [x]
        return [[float(sum(ord(ch) for ch in t) % 97), float(len(t))] for t in items]
    monkeypatch.setattr("engine.llm.embed", fake_embed)

    target = corpus[2]  # step-therapy biologic
    hits = retrieve(target["text"], 1, corpus)
    assert hits[0][0] == target["id"]  # the DB-backed corpus drove retrieval
