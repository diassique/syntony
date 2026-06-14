"""Control-plane services — the operations the API/CLI call, tying models + security.

Auth (signup/login/api-keys), encrypted credential storage, and the run+audit+metering
writes that make a negotiation a billable, auditable unit. Functions take an open
``Session`` so the caller controls the transaction boundary.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlmodel import Session, select

from . import security
from .models import (
    ApiKey,
    Credential,
    Event,
    Membership,
    MemberRole,
    Organization,
    Run,
    RunStatus,
    UsageRecord,
    User,
)


class AuthError(Exception):
    """Signup/login failure (duplicate email, bad credentials, …)."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "org"
    return f"{base}-{security.secrets.token_hex(3)}"  # short suffix keeps slugs unique


# ---- auth ---------------------------------------------------------------------
def signup(sess: Session, *, email: str, password: str, name: str = "", org_name: str | None = None
           ) -> tuple[User, Organization]:
    """Create a user, a personal org, and an owner membership. Raises ``AuthError`` on dup email."""
    if sess.exec(select(User).where(User.email == email)).first():
        raise AuthError(f"email already registered: {email}")
    user = User(email=email, password_hash=security.hash_password(password), name=name)
    sess.add(user)
    org = Organization(name=org_name or f"{name or email.split('@')[0]}'s org",
                       slug=_slugify(org_name or email.split("@")[0]))
    sess.add(org)
    sess.flush()  # populate ids
    sess.add(Membership(user_id=user.id, org_id=org.id, role=MemberRole.OWNER.value))
    sess.commit()
    sess.refresh(user)
    sess.refresh(org)
    return user, org


def login(sess: Session, *, email: str, password: str) -> tuple[User, str] | None:
    """Verify credentials → ``(user, jwt)`` scoped to the user's first org, or ``None``."""
    user = sess.exec(select(User).where(User.email == email)).first()
    if not user or not user.is_active or not security.verify_password(password, user.password_hash):
        return None
    m = sess.exec(select(Membership).where(Membership.user_id == user.id)).first()
    return user, security.issue_token(user_id=user.id, org_id=m.org_id if m else None)


def create_api_key(sess: Session, *, org_id: str, name: str = "default") -> tuple[str, ApiKey]:
    """Mint an org-scoped API key. Returns ``(full_key, record)`` — the full key is shown ONCE."""
    full, prefix, key_hash = security.generate_api_key()
    rec = ApiKey(org_id=org_id, name=name, prefix=prefix, key_hash=key_hash)
    sess.add(rec)
    sess.commit()
    sess.refresh(rec)
    return full, rec


def verify_api_key(sess: Session, full_key: str) -> ApiKey | None:
    """Resolve a presented API key to its (active) record, stamping ``last_used_at``."""
    rec = sess.exec(select(ApiKey).where(ApiKey.key_hash == security.hash_api_key(full_key))).first()
    if not rec or rec.revoked_at is not None:
        return None
    rec.last_used_at = _now()
    sess.add(rec)
    sess.commit()
    return rec


# ---- encrypted credentials ----------------------------------------------------
def store_credential(sess: Session, *, org_id: str, kind: str, label: str, secret: str,
                     meta: dict | None = None) -> Credential:
    """Store a provider secret encrypted at rest (Band/LLM key). Plaintext never persisted."""
    cred = Credential(org_id=org_id, kind=kind, label=label,
                      ciphertext=security.encrypt_secret(secret), meta=meta or {})
    sess.add(cred)
    sess.commit()
    sess.refresh(cred)
    return cred


def reveal_credential(cred: Credential) -> str:
    """Decrypt a stored credential for use (e.g. handing a Band key to the adapter)."""
    return security.decrypt_secret(cred.ciphertext)


# ---- runs + audit + metering --------------------------------------------------
def start_run(sess: Session, *, org_id: str, project_id: str | None = None, case_name: str = "",
              room_id: str | None = None) -> Run:
    run = Run(org_id=org_id, project_id=project_id, case_name=case_name, room_id=room_id)
    sess.add(run)
    sess.commit()
    sess.refresh(run)
    return run


def record_event(sess: Session, *, run: Run, turn: int, author: str, kind: str,
                 visibility: str, payload: dict) -> Event:
    """Append one envelope to the durable audit trail (and never mutate it afterwards)."""
    ev = Event(run_id=run.id, org_id=run.org_id, turn=turn, author=author, kind=kind,
               visibility=visibility, payload=payload)
    sess.add(ev)
    sess.commit()
    return ev


def record_usage(sess: Session, *, org_id: str, run_id: str | None = None, kind: str = "run",
                 model: str = "", input_tokens: int = 0, output_tokens: int = 0, units: int = 1
                 ) -> UsageRecord:
    rec = UsageRecord(org_id=org_id, run_id=run_id, kind=kind, model=model,
                      input_tokens=input_tokens, output_tokens=output_tokens, units=units)
    sess.add(rec)
    sess.commit()
    return rec


def finish_run(sess: Session, *, run: Run, status: str = RunStatus.SUCCEEDED.value,
               final_state: str | None = None, turns: int = 0) -> Run:
    run.status = status
    run.final_state = final_state
    run.turns = turns
    run.ended_at = _now()
    sess.add(run)
    sess.commit()
    sess.refresh(run)
    return run
