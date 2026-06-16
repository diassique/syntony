"""Control-plane services — the operations the API/CLI call, tying models + security.

Auth (signup/login/api-keys), encrypted credential storage, and the run+audit+metering
writes that make a negotiation a billable, auditable unit. Functions take an open
``Session`` so the caller controls the transaction boundary.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from . import security
from .models import (
    ApiKey,
    Condition,
    Coverage,
    Credential,
    DocType,
    Event,
    GoldCard,
    Procedure,
    Membership,
    MemberRole,
    Organization,
    Patient,
    Run,
    RunStatus,
    Session as AuthSession,
    TreatmentRecord,
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


def login(sess: Session, *, email: str, password: str) -> User | None:
    """Verify credentials and return the active ``User`` (or ``None``). Token/session
    issuance is the API layer's job (it owns the cookie + access-token response)."""
    user = sess.exec(select(User).where(User.email == email)).first()
    if not user or not user.is_active or not security.verify_password(password, user.password_hash):
        return None
    return user


def primary_org_id(sess: Session, user_id: str) -> str | None:
    """The org a user's session is scoped to (their first membership)."""
    return sess.exec(select(Membership.org_id).where(Membership.user_id == user_id)).first()


# ---- refresh-token sessions (server-side, revocable, rotated) ------------------
def create_session(sess: Session, *, user: User, org_id: str | None, user_agent: str = ""
                   ) -> tuple[str, AuthSession]:
    """Open a refresh session. Returns ``(raw_refresh_token, record)``; only the hash is stored."""
    raw, token_hash = security.new_refresh_token()
    rec = AuthSession(user_id=user.id, org_id=org_id, token_hash=token_hash,
                      user_agent=user_agent[:300],
                      expires_at=_now() + timedelta(days=security.REFRESH_TTL_DAYS))
    sess.add(rec)
    sess.commit()
    sess.refresh(rec)
    return raw, rec


def _live_session(sess: Session, raw: str) -> AuthSession | None:
    rec = sess.exec(select(AuthSession).where(AuthSession.token_hash == security.hash_refresh(raw))).first()
    if not rec or rec.revoked_at is not None or rec.expires_at <= _now():
        return None
    return rec


def rotate_session(sess: Session, raw: str, *, user_agent: str = ""
                   ) -> tuple[str, User, str | None] | None:
    """Validate a refresh token, revoke it (rotation), and issue a fresh one. Returns
    ``(new_raw_token, user, org_id)`` or ``None`` if the presented token is invalid."""
    rec = _live_session(sess, raw)
    if rec is None:
        return None
    user = sess.get(User, rec.user_id)
    if user is None or not user.is_active:
        return None
    rec.revoked_at = _now()  # one-time use: the old token is dead the moment it's rotated
    sess.add(rec)
    new_raw, _ = create_session(sess, user=user, org_id=rec.org_id, user_agent=user_agent)
    return new_raw, user, rec.org_id


def revoke_session(sess: Session, raw: str) -> bool:
    """Revoke a single session by its raw token (logout). Idempotent."""
    rec = sess.exec(select(AuthSession).where(AuthSession.token_hash == security.hash_refresh(raw))).first()
    if rec is None or rec.revoked_at is not None:
        return False
    rec.revoked_at = _now()
    sess.add(rec)
    sess.commit()
    return True


def revoke_all_sessions(sess: Session, *, user_id: str) -> int:
    """Revoke every live session for a user (sign out everywhere). Returns count revoked."""
    rows = sess.exec(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).all()
    for r in rows:
        r.revoked_at = _now()
        sess.add(r)
    sess.commit()
    return len(rows)


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
                 visibility: str, payload: dict, org_id: str | None = None) -> Event:
    """Append one envelope to the durable audit trail (and never mutate it afterwards).

    ``org_id`` defaults to the run's owning org. For a cross-org run the same envelope is
    recorded once per org that may see it (a room message → both orgs; a private event →
    only its author's org), so callers pass an explicit ``org_id`` per audited copy.
    """
    ev = Event(run_id=run.id, org_id=org_id or run.org_id, turn=turn, author=author, kind=kind,
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


# ---- synthetic patient charts (EHR layer) -------------------------------------
def list_patients(sess: Session, *, org_id: str) -> list[Patient]:
    """The clinic org's patient roster, ordered by name."""
    return list(sess.exec(
        select(Patient).where(Patient.org_id == org_id).order_by(Patient.family_name, Patient.given_name)
    ).all())


def get_patient(sess: Session, *, org_id: str, patient_id: str) -> Patient | None:
    """A patient, scoped to the owning org (tenant isolation)."""
    p = sess.get(Patient, patient_id)
    return p if (p is not None and p.org_id == org_id) else None


def patient_coverage(sess: Session, patient_id: str) -> Coverage | None:
    return sess.exec(select(Coverage).where(Coverage.patient_id == patient_id)).first()


def patient_conditions(sess: Session, patient_id: str) -> list[Condition]:
    return list(sess.exec(select(Condition).where(Condition.patient_id == patient_id)).all())


def patient_treatments(sess: Session, patient_id: str) -> list[TreatmentRecord]:
    return list(sess.exec(select(TreatmentRecord).where(TreatmentRecord.patient_id == patient_id)).all())


def patient_runs(sess: Session, patient_id: str) -> list[Run]:
    """Prior-auth cases linked to a patient, newest first."""
    return list(sess.exec(
        select(Run).where(Run.patient_id == patient_id).order_by(Run.started_at.desc())
    ).all())


def coverage_summary(cov: Coverage | None) -> str:
    """A one-line eligibility summary the provider Eligibility agent cites (270/271-style)."""
    if cov is None:
        return ""
    return f"{cov.payer_name} — {cov.plan_type}, member {cov.member_id} ({cov.status})"


# ---- reference catalogs (served from the DB, seeded from code) -----------------
def list_doc_types(sess: Session) -> list[DocType]:
    return list(sess.exec(select(DocType).order_by(DocType.sort_order)).all())


def list_procedures(sess: Session) -> list[Procedure]:
    return list(sess.exec(select(Procedure).order_by(Procedure.sort_order)).all())


def criteria_corpus(sess: Session) -> list[dict[str, str]]:
    """The medical-necessity criteria corpus in retrieve()'s shape ({"id","text"}). Empty list
    if unseeded — the caller then falls back to the built-in corpus."""
    from .models import Criterion
    rows = sess.exec(select(Criterion).order_by(Criterion.sort_order)).all()
    return [{"id": c.slug, "text": c.text} for c in rows]


def list_agent_configs(sess: Session, *, org_id: str) -> list:
    """The agent cast (AgentConfig rows) for an org's authbridge project, in seed order.
    Empty if the project/cast isn't seeded — the caller then falls back to the code roster."""
    from .models import AgentConfig, Project
    proj = sess.exec(
        select(Project).where(Project.org_id == org_id, Project.slug == "authbridge")
    ).first()
    if proj is None:
        return []
    return list(sess.exec(
        select(AgentConfig).where(AgentConfig.project_id == proj.id).order_by(AgentConfig.created_at)
    ).all())


def upsert_policy_rule(sess: Session, *, procedure_code: str, required_diagnosis_prefixes: list,
                       required_docs: list, step_therapy_docs: list, red_flag_prefixes: list,
                       auto_approve: bool):
    """Create or update a payer policy rule for a procedure code (edited from the UI)."""
    from .models import PolicyRuleRow
    code = procedure_code.strip().upper()
    row = sess.exec(select(PolicyRuleRow).where(PolicyRuleRow.procedure_code == code)).first()
    if row is None:
        row = PolicyRuleRow(procedure_code=code)
    row.required_diagnosis_prefixes = list(required_diagnosis_prefixes)
    row.required_docs = list(required_docs)
    row.step_therapy_docs = list(step_therapy_docs)
    row.red_flag_prefixes = list(red_flag_prefixes)
    row.auto_approve = bool(auto_approve)
    sess.add(row)
    sess.commit()
    sess.refresh(row)
    return row


def delete_policy_rule(sess: Session, *, procedure_code: str) -> bool:
    from .models import PolicyRuleRow
    row = sess.exec(select(PolicyRuleRow).where(
        PolicyRuleRow.procedure_code == procedure_code.strip().upper())).first()
    if row is None:
        return False
    sess.delete(row)
    sess.commit()
    return True


def list_policy_rules(sess: Session) -> list:
    from .models import PolicyRuleRow
    return list(sess.exec(select(PolicyRuleRow).order_by(PolicyRuleRow.procedure_code)).all())


def upsert_criterion(sess: Session, *, slug: str, text: str):
    """Create or update a medical-necessity criterion (edited from the UI)."""
    from .models import Criterion
    slug = slug.strip()
    row = sess.exec(select(Criterion).where(Criterion.slug == slug)).first()
    if row is None:
        nxt = sess.exec(select(Criterion).order_by(Criterion.sort_order.desc())).first()
        row = Criterion(slug=slug, sort_order=(nxt.sort_order + 1) if nxt else 0)
    row.text = text.strip()
    sess.add(row)
    sess.commit()
    sess.refresh(row)
    return row


def delete_criterion(sess: Session, *, slug: str) -> bool:
    from .models import Criterion
    row = sess.exec(select(Criterion).where(Criterion.slug == slug.strip())).first()
    if row is None:
        return False
    sess.delete(row)
    sess.commit()
    return True


def list_criteria(sess: Session) -> list:
    from .models import Criterion
    return list(sess.exec(select(Criterion).order_by(Criterion.sort_order)).all())


def load_policy(sess: Session) -> dict:
    """The payer policy as the domain's ``{code: PolicyRule}`` map, read from the DB. Falls back
    to the built-in ``POLICY_TABLE`` when the table is empty (offline / unseeded)."""
    from .models import PolicyRuleRow
    from domains.authbridge.policy import POLICY_TABLE, PolicyRule
    rows = sess.exec(select(PolicyRuleRow)).all()
    if not rows:
        return POLICY_TABLE
    return {r.procedure_code: PolicyRule(
        required_diagnosis_prefixes=tuple(r.required_diagnosis_prefixes),
        required_docs=tuple(r.required_docs),
        step_therapy_docs=tuple(r.step_therapy_docs),
        red_flag_prefixes=tuple(r.red_flag_prefixes),
        auto_approve=r.auto_approve,
    ) for r in rows}


# ---- gold carding (provider PA exemption; Texas HB 3459/3812) ------------------
GOLD_MIN_TOTAL = 5      # minimum decided requests to qualify
GOLD_MIN_RATE = 0.9     # ≥90% approvals


def active_gold_card(sess: Session, *, org_id: str, npi: str, code: str) -> GoldCard | None:
    """An active exemption for this provider + procedure, if any."""
    if not npi or not code:
        return None
    return sess.exec(
        select(GoldCard).where(GoldCard.org_id == org_id, GoldCard.provider_npi == npi,
                               GoldCard.procedure_code == code, GoldCard.status == "active")
    ).first()


def list_gold_cards(sess: Session, *, org_id: str) -> list[GoldCard]:
    return list(sess.exec(
        select(GoldCard).where(GoldCard.org_id == org_id, GoldCard.status == "active")
    ).all())


def issue_gold_card(sess: Session, *, org_id: str, provider_npi: str, provider_name: str,
                    procedure_code: str, procedure_display: str, approvals: int, total: int,
                    basis: str) -> GoldCard:
    """Issue (or return the existing) gold card for a provider + procedure. Idempotent."""
    existing = sess.exec(
        select(GoldCard).where(GoldCard.org_id == org_id, GoldCard.provider_npi == provider_npi,
                               GoldCard.procedure_code == procedure_code)
    ).first()
    if existing is not None:
        return existing
    gc = GoldCard(org_id=org_id, provider_npi=provider_npi, provider_name=provider_name,
                  procedure_code=procedure_code, procedure_display=procedure_display,
                  approvals=approvals, total=total, rate=round(approvals / total, 3) if total else 0.0,
                  status="active", basis=basis)
    sess.add(gc)
    sess.commit()
    sess.refresh(gc)
    return gc


def recompute_gold_cards(sess: Session, *, org_id: str) -> int:
    """Derive gold cards from the org's decided interactive runs (per provider NPI + procedure):
    ≥``GOLD_MIN_TOTAL`` decided and ≥``GOLD_MIN_RATE`` approved → an active exemption. Additive —
    updates derived stats and creates new cards, never deactivates a previously-issued one.
    Returns the number of NEW cards created."""
    from collections import defaultdict
    runs = sess.exec(
        select(Run).where(Run.org_id == org_id, Run.mode == "interactive",
                          Run.status == RunStatus.SUCCEEDED.value)
    ).all()
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: {"approvals": 0, "total": 0, "name": "", "display": ""})
    for r in runs:
        req = (r.workflow or {}).get("state", {}).get("req", {})
        npi = (req.get("ordering_provider") or {}).get("npi", "")
        code = (req.get("procedure") or {}).get("code", "")
        if not npi or not code or r.outcome not in ("APPROVE", "DENY"):
            continue
        g = groups[(npi, code)]
        g["total"] += 1
        if r.outcome == "APPROVE":
            g["approvals"] += 1
        g["name"] = (req.get("ordering_provider") or {}).get("name", "") or g["name"]
        g["display"] = (req.get("procedure") or {}).get("display", "") or g["display"]
    created = 0
    for (npi, code), g in groups.items():
        rate = g["approvals"] / g["total"] if g["total"] else 0.0
        if g["total"] < GOLD_MIN_TOTAL or rate < GOLD_MIN_RATE:
            continue
        existing = active_gold_card(sess, org_id=org_id, npi=npi, code=code)
        if existing is not None:
            existing.approvals, existing.total, existing.rate = g["approvals"], g["total"], round(rate, 3)
            sess.add(existing)
        else:
            sess.add(GoldCard(org_id=org_id, provider_npi=npi, provider_name=g["name"],
                              procedure_code=code, procedure_display=g["display"],
                              approvals=g["approvals"], total=g["total"], rate=round(rate, 3),
                              status="active", basis=f"{round(100 * rate)}% approvals over {g['total']} requests"))
            created += 1
    sess.commit()
    return created


def finish_run(sess: Session, *, run: Run, status: str = RunStatus.SUCCEEDED.value,
               final_state: str | None = None, turns: int = 0, outcome: str | None = None) -> Run:
    run.status = status
    run.final_state = final_state
    run.outcome = outcome
    run.turns = turns
    run.ended_at = _now()
    sess.add(run)
    sess.commit()
    sess.refresh(run)
    return run
