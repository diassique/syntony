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
    assert again == {"doc_types": 0, "procedures": 0}


def test_catalogs_served_from_db_match_the_seed(sess):
    seed.seed_refdata(sess)
    tokens = {d.token for d in service.list_doc_types(sess)}
    assert tokens == {d["id"] for d in SUPPORTING_DOC_TYPES}
    codes = [p.code for p in service.list_procedures(sess)]
    assert codes == [p["code"] for p in KNOWN_PROCEDURES]  # sort_order preserved
