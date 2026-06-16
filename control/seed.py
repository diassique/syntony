"""Seed the two demo organizations for the AuthBridge showcase.

Creates (idempotently) a **Clinic** org and a **Payer** org, each with a loginable owner
user, an AuthBridge project, and — when the Band agent keys are present in the env — that
side's agent key stored as an encrypted ``Credential``. These are the accounts a judge
signs into to see the *same* negotiation from each side: the audit trail is org-scoped, so
the clinic sees its own private strategy and the payer never does.

Run it:  ``PYTHONPATH=. .venv/bin/python -m control.seed``

The demo password comes from ``SYNTONY_DEMO_PASSWORD`` (default below). Slugs are fixed so
``demo_side_orgs`` can map a negotiation side → org id when persisting a run.
"""

from __future__ import annotations

import os

from sqlmodel import Session, select

from . import security
from .db import session as _open_session
from .models import (
    Credential,
    CredentialKind,
    Membership,
    MemberRole,
    Organization,
    Project,
    User,
)

DEFAULT_PASSWORD = "syntonydemo24"  # >= 8 chars; override via SYNTONY_DEMO_PASSWORD

#: side ("provider"/"payer") → demo account definition. Slugs are stable on purpose.
DEMO_ACCOUNTS: dict[str, dict[str, str]] = {
    "provider": {
        "email": "clinic@demo.syntony",
        "name": "Clinic Admin",
        "org_name": "Northside Clinic",
        "org_slug": "northside-clinic",
        "env_prefix": "CLINIC",
        "cred_kind": CredentialKind.BAND_AGENT.value,
    },
    "payer": {
        "email": "payer@demo.syntony",
        "name": "Payer Admin",
        "org_name": "Meridian Health Plan",
        "org_slug": "meridian-health",
        "env_prefix": "PAYER",
        "cred_kind": CredentialKind.BAND_AGENT.value,
    },
}


def _get_or_create_org(sess: Session, *, name: str, slug: str) -> Organization:
    org = sess.exec(select(Organization).where(Organization.slug == slug)).first()
    if org is None:
        org = Organization(name=name, slug=slug)
        sess.add(org)
        sess.commit()
        sess.refresh(org)
    return org


def _get_or_create_owner(sess: Session, *, email: str, name: str, password: str, org: Organization) -> User:
    user = sess.exec(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email, password_hash=security.hash_password(password), name=name)
        sess.add(user)
        sess.commit()
        sess.refresh(user)
    membership = sess.exec(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org.id)
    ).first()
    if membership is None:
        sess.add(Membership(user_id=user.id, org_id=org.id, role=MemberRole.OWNER.value))
        sess.commit()
    return user


def _ensure_project(sess: Session, *, org: Organization) -> None:
    existing = sess.exec(
        select(Project).where(Project.org_id == org.id, Project.slug == "authbridge")
    ).first()
    if existing is None:
        sess.add(Project(org_id=org.id, name="Prior Authorization", slug="authbridge", domain="authbridge"))
        sess.commit()


def _ensure_credential(sess: Session, *, org: Organization, side: str, env_prefix: str, kind: str) -> bool:
    """Store the side's Band agent key (encrypted) if present in the env and not already stored."""
    api_key = os.environ.get(f"{env_prefix}_AGENT_API_KEY", "").strip()
    agent_id = os.environ.get(f"{env_prefix}_AGENT_ID", "").strip()
    if not api_key:
        return False
    label = f"{side} band agent"
    existing = sess.exec(
        select(Credential).where(Credential.org_id == org.id, Credential.label == label)
    ).first()
    if existing is not None:
        return True
    sess.add(Credential(org_id=org.id, kind=kind, label=label,
                        ciphertext=security.encrypt_secret(api_key),
                        meta={"agent_id": agent_id, "side": side}))
    sess.commit()
    return True


def seed_refdata(sess: Session) -> dict:
    """Seed the global reference catalogs (doc types, known procedures) from the domain constants.
    Idempotent — keyed by token/code. Served from the DB thereafter."""
    from .models import DocType, Procedure
    from domains.authbridge.workflow import SUPPORTING_DOC_TYPES, KNOWN_PROCEDURES
    n_docs = n_proc = 0
    for i, d in enumerate(SUPPORTING_DOC_TYPES):
        if sess.exec(select(DocType).where(DocType.token == d["id"])).first() is None:
            sess.add(DocType(token=d["id"], label=d["label"], sort_order=i)); n_docs += 1
    for i, p in enumerate(KNOWN_PROCEDURES):
        if sess.exec(select(Procedure).where(Procedure.code == p["code"])).first() is None:
            sess.add(Procedure(system=p["system"], code=p["code"], display=p["display"], sort_order=i)); n_proc += 1
    sess.commit()
    return {"doc_types": n_docs, "procedures": n_proc}


def seed_demo(sess: Session, *, password: str | None = None) -> dict:
    """Create/repair the two demo orgs. Returns a summary (slugs, org ids, which creds were stored)."""
    pw = password or os.environ.get("SYNTONY_DEMO_PASSWORD", DEFAULT_PASSWORD)
    summary: dict[str, dict] = {}
    for side, acc in DEMO_ACCOUNTS.items():
        org = _get_or_create_org(sess, name=acc["org_name"], slug=acc["org_slug"])
        _get_or_create_owner(sess, email=acc["email"], name=acc["name"], password=pw, org=org)
        _ensure_project(sess, org=org)
        has_cred = _ensure_credential(sess, org=org, side=side, env_prefix=acc["env_prefix"], kind=acc["cred_kind"])
        summary[side] = {"org_id": org.id, "slug": org.slug, "email": acc["email"], "credential": has_cred}
    summary["refdata"] = seed_refdata(sess)  # global reference catalogs
    # Curated synthetic patient roster lives on the provider (clinic) org.
    from .seed_patients import seed_patients
    from . import service
    provider_org_id = summary.get("provider", {}).get("org_id")
    if provider_org_id:
        summary["patients"] = {"created": seed_patients(sess, clinic_org_id=provider_org_id)}
        # One issued gold card so the exemption is demonstrable out of the box (TX HB 3459 ≥90%).
        service.issue_gold_card(
            sess, org_id=provider_org_id, provider_npi="1000000007",
            provider_name="Dr. Rivera (synthetic)", procedure_code="72148",
            procedure_display="MRI lumbar spine w/o contrast", approvals=16, total=17,
            basis="94% approvals over 17 requests (rolling 6 months)",
        )
    return summary


def demo_side_orgs(sess: Session) -> dict[str, str]:
    """Map negotiation side → org id for the seeded demo orgs (``{}`` if not seeded yet)."""
    out: dict[str, str] = {}
    for side, acc in DEMO_ACCOUNTS.items():
        org = sess.exec(select(Organization).where(Organization.slug == acc["org_slug"])).first()
        if org is not None:
            out[side] = org.id
    return out


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    with _open_session() as sess:
        summary = seed_demo(sess)
    pw = os.environ.get("SYNTONY_DEMO_PASSWORD", DEFAULT_PASSWORD)
    print("Seeded demo orgs:")
    for side, info in summary.items():
        if side == "patients":
            print(f"  patients  roster on clinic org ({info['created']} created)")
            continue
        if side == "refdata":
            print(f"  refdata   catalogs ({info['doc_types']} doc types, {info['procedures']} procedures)")
            continue
        cred = "✓ band key" if info["credential"] else "— no band key in env"
        print(f"  {side:9} {info['email']:22} org={info['slug']:18} {cred}")
    print(f"\nLogin password for all demo accounts: {pw!r}")


if __name__ == "__main__":
    main()
