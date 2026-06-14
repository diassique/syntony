"""Control-plane HTTP API — the auth surface the SPA talks to.

A thin FastAPI ``APIRouter`` over ``control.service``: signup, login, and "who am I".
It owns no business logic — it validates input, opens a DB session, calls the service
layer, and shapes JSON. Sessions are per-request (a dependency); auth is a Bearer JWT
(issued at signup/login, verified by ``control.security``).

Mounted by ``ui/server.py`` under ``/api`` so the SPA and API ship as one unit.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import security, service
from .db import session as _open_session
from .models import Membership, Organization, User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


# ---- dependencies --------------------------------------------------------------
def get_session() -> Iterator[Session]:
    """One DB session per request; closed when the request finishes."""
    with _open_session() as sess:
        yield sess


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    sess: Session = Depends(get_session),
) -> User:
    """Resolve the Bearer JWT to its active ``User`` or raise 401."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    claims = security.verify_token(creds.credentials)
    if not claims or "sub" not in claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = sess.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


# ---- schemas -------------------------------------------------------------------
class SignupIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = ""
    org_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str


class AuthOut(BaseModel):
    token: str
    user: UserOut
    org: OrgOut | None = None


def _org_out(sess: Session, org_id: str | None) -> OrgOut | None:
    if not org_id:
        return None
    org = sess.get(Organization, org_id)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, plan=org.plan) if org else None


# ---- endpoints -----------------------------------------------------------------
@router.post("/signup", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, sess: Session = Depends(get_session)) -> AuthOut:
    if "@" not in body.email or "." not in body.email.split("@")[-1]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email address")
    try:
        user, org = service.signup(
            sess, email=body.email.strip().lower(), password=body.password,
            name=body.name.strip(), org_name=body.org_name,
        )
    except service.AuthError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    token = security.issue_token(user_id=user.id, org_id=org.id)
    return AuthOut(token=token, user=UserOut(id=user.id, email=user.email, name=user.name),
                   org=OrgOut(id=org.id, name=org.name, slug=org.slug, plan=org.plan))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, sess: Session = Depends(get_session)) -> AuthOut:
    result = service.login(sess, email=body.email.strip().lower(), password=body.password)
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    user, token = result
    claims = security.verify_token(token) or {}
    return AuthOut(token=token, user=UserOut(id=user.id, email=user.email, name=user.name),
                   org=_org_out(sess, claims.get("org")))


@router.get("/me", response_model=AuthOut)
def me(user: User = Depends(current_user), sess: Session = Depends(get_session)) -> AuthOut:
    """Echo the authenticated identity. The SPA calls this on load to restore a session."""
    org_id = sess.exec(
        select(Membership.org_id).where(Membership.user_id == user.id)
    ).first()
    return AuthOut(
        token="",  # /me does not re-issue; the client already holds its token
        user=UserOut(id=user.id, email=user.email, name=user.name),
        org=_org_out(sess, org_id),
    )
