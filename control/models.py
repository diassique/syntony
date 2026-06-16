"""Control-plane data model (SQLModel → PostgreSQL).

Multi-tenant: an **Organization** is the unit of ownership, isolation, and billing; **Users**
join orgs via **Membership** (owner/admin/member). Within an org: **Projects** (a customer's
domain pack) hold **AgentConfigs** (their agent cast); **Credentials** store encrypted Band/LLM
keys; **ApiKeys** grant programmatic access. Each negotiation is a **Run** whose envelopes are
mirrored append-only into **Event** (the audit moat) — and metered into **UsageRecord**
(runs + tokens) for usage-based billing.

JSON columns use SQLAlchemy's portable ``JSON`` type (JSON on Postgres, works on SQLite for
offline tests). Enum-like fields are plain strings; the classes below are code-side constants.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    # naive UTC — uniform across Postgres/SQLite, no tz-column juggling
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class CredentialKind(str, Enum):
    BAND_AGENT = "band_agent"
    BAND_USER = "band_user"
    LLM_PROVIDER = "llm_provider"


class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"  # paused at a borderline case for the human Medical Director
    # interactive two-sided workflow: the run is parked waiting for one side's human to act
    AWAITING_PAYER = "awaiting_payer"            # submitted; in the payer worklist to be opened
    AWAITING_PAYER_DECISION = "awaiting_payer_decision"  # UM review done; payer must commit a verdict
    AWAITING_PROVIDER = "awaiting_provider"      # pended/denied; provider must respond or appeal
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunMode(str, Enum):
    AUTO = "auto"               # the "Sample run" — the runner auto-drives both sides end-to-end
    INTERACTIVE = "interactive"  # the real flow — humans on each side act through the workflow API


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    name: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=_now)


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"
    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    slug: str = Field(index=True, unique=True)
    plan: str = Field(default=Plan.FREE.value)
    created_at: datetime = Field(default_factory=_now)


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_membership_user_org"),)
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    role: str = Field(default=MemberRole.MEMBER.value)
    created_at: datetime = Field(default_factory=_now)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"
    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    name: str = "default"
    prefix: str  # first chars, for display
    key_hash: str = Field(index=True, unique=True)  # sha256 of the full key
    created_at: datetime = Field(default_factory=_now)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class Session(SQLModel, table=True):
    """A refresh-token session. We store only the sha256 of the opaque refresh token;
    rotation revokes the old row and issues a new one. Revocation = setting ``revoked_at``."""

    __tablename__ = "sessions"
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    org_id: str | None = None
    token_hash: str = Field(index=True, unique=True)  # sha256 of the opaque refresh token
    user_agent: str = ""
    created_at: datetime = Field(default_factory=_now)
    last_used_at: datetime = Field(default_factory=_now)
    expires_at: datetime
    revoked_at: datetime | None = None


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_project_org_slug"),)
    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    name: str
    slug: str
    domain: str = "authbridge"  # which domain pack this project builds on
    config: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)


class AgentConfig(SQLModel, table=True):
    __tablename__ = "agent_configs"
    id: str = Field(default_factory=_uuid, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    role_id: str
    display_name: str
    side: str = "neutral"
    framework: str = "pydantic_ai"
    model: str = ""
    system_prompt: str = ""
    extra: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)


class Credential(SQLModel, table=True):
    __tablename__ = "credentials"
    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    kind: str  # CredentialKind
    label: str
    ciphertext: str  # Fernet-encrypted secret — never plaintext
    meta: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)


class Run(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)
    case_name: str = ""
    status: str = Field(default=RunStatus.RUNNING.value)
    mode: str = Field(default=RunMode.AUTO.value)  # "auto" (Sample run) | "interactive" (real flow)
    final_state: str | None = None
    outcome: str | None = None  # the case's final decision (APPROVE/DENY/…), for metrics
    urgency: str | None = None  # "standard" (7d) | "expedited" (72h) — CMS-0057-F SLA
    turns: int = 0
    room_id: str | None = None
    #: Resumable working state of an interactive run (serialized AuthBridgeState + FSM state).
    #: Empty for autoplay runs. The interactive workflow reads it to resume the next segment.
    workflow: dict = Field(default_factory=dict, sa_type=JSON)
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None


class Event(SQLModel, table=True):
    """Append-only mirror of one protocol ``Envelope`` — the durable audit trail."""

    __tablename__ = "events"
    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    turn: int = 0
    author: str = ""
    kind: str = ""
    visibility: str = "room"
    payload: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_now)


class UsageRecord(SQLModel, table=True):
    """Metering for usage-based billing: one row per billable event (a run, an LLM call)."""

    __tablename__ = "usage_records"
    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    run_id: str | None = Field(default=None, foreign_key="runs.id", index=True)
    kind: str = "run"  # "run" | "llm_call"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    units: int = 1
    created_at: datetime = Field(default_factory=_now)
