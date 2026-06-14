"""Database engine + session for the control plane.

``DATABASE_URL`` (from env) selects the backend — PostgreSQL in prod
(``postgresql+psycopg2://user:pass@host/db``), SQLite for offline tests
(``sqlite://`` in-memory). Importing this module imports ``models`` so every table is
registered on ``SQLModel.metadata`` before ``init_db`` / ``create_all``.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401 — registers all tables on SQLModel.metadata

DEFAULT_URL = "sqlite:///./syntony.db"

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", DEFAULT_URL)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, echo=False, pool_pre_ping=True, connect_args=connect_args)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    """Create all tables that don't yet exist (idempotent). Good enough for a fresh DB;
    use Alembic once the schema starts evolving in production."""
    SQLModel.metadata.create_all(engine or get_engine())


def session(engine: Engine | None = None) -> Session:
    return Session(engine or get_engine())
