"""Control-plane HTTP API — the auth surface the SPA talks to.

A thin FastAPI ``APIRouter`` over ``control.service``: signup, login, and "who am I".
It owns no business logic — it validates input, opens a DB session, calls the service
layer, and shapes JSON. Sessions are per-request (a dependency); auth is a Bearer JWT
(issued at signup/login, verified by ``control.security``).

Mounted by ``ui/server.py`` under ``/api`` so the SPA and API ship as one unit.
"""

from __future__ import annotations

import os
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from . import security, service
from .db import session as _open_session
from .models import Event, Membership, Organization, Run, User

router = APIRouter(prefix="/api/auth", tags=["auth"])
runs_router = APIRouter(prefix="/api/runs", tags=["runs"])

_bearer = HTTPBearer(auto_error=False)

# Refresh token travels in an httpOnly cookie scoped to the auth endpoints only.
REFRESH_COOKIE = "syntony_refresh"
_COOKIE_PATH = "/api/auth"


def _cookie_secure() -> bool:
    # Secure cookies require HTTPS; disable only for local/dev or tests via env.
    return os.environ.get("SYNTONY_COOKIE_SECURE", "1") != "0"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, raw,
        max_age=security.REFRESH_TTL_DAYS * 86400,
        httponly=True, secure=_cookie_secure(), samesite="strict", path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=_COOKIE_PATH)


def _ua(request: Request) -> str:
    return request.headers.get("user-agent", "")


ACCESS_TTL_SECONDS = security.ACCESS_TTL_MINUTES * 60


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


def current_org_id(user: User = Depends(current_user), sess: Session = Depends(get_session)) -> str:
    """The org the signed-in user belongs to — the audit scope for all run queries."""
    org_id = sess.exec(select(Membership.org_id).where(Membership.user_id == user.id)).first()
    if not org_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user has no organization")
    return org_id


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
    token: str             # short-lived access token (kept in memory by the client)
    expires_in: int = ACCESS_TTL_SECONDS
    user: UserOut
    org: OrgOut | None = None


def _org_out(sess: Session, org_id: str | None) -> OrgOut | None:
    if not org_id:
        return None
    org = sess.get(Organization, org_id)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, plan=org.plan) if org else None


# ---- endpoints -----------------------------------------------------------------
def _issue(sess: Session, response: Response, user: User, org_id: str | None, request: Request) -> AuthOut:
    """Mint an access token, open a refresh session, set the refresh cookie, and shape the body."""
    access = security.issue_token(user_id=user.id, org_id=org_id)
    raw_refresh, _ = service.create_session(sess, user=user, org_id=org_id, user_agent=_ua(request))
    _set_refresh_cookie(response, raw_refresh)
    return AuthOut(token=access, user=UserOut(id=user.id, email=user.email, name=user.name),
                   org=_org_out(sess, org_id))


@router.post("/signup", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, request: Request, response: Response, sess: Session = Depends(get_session)) -> AuthOut:
    if "@" not in body.email or "." not in body.email.split("@")[-1]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email address")
    try:
        user, org = service.signup(
            sess, email=body.email.strip().lower(), password=body.password,
            name=body.name.strip(), org_name=body.org_name,
        )
    except service.AuthError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return _issue(sess, response, user, org.id, request)


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, response: Response, sess: Session = Depends(get_session)) -> AuthOut:
    user = service.login(sess, email=body.email.strip().lower(), password=body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return _issue(sess, response, user, service.primary_org_id(sess, user.id), request)


@router.post("/refresh", response_model=AuthOut)
def refresh(request: Request, response: Response, sess: Session = Depends(get_session)) -> AuthOut:
    """Exchange a valid refresh cookie for a new access token, rotating the refresh token."""
    raw = request.cookies.get(REFRESH_COOKIE)
    rotated = service.rotate_session(sess, raw, user_agent=_ua(request)) if raw else None
    if rotated is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    new_raw, user, org_id = rotated
    sess.commit()  # persist the rotation (old revoked + new created)
    access = security.issue_token(user_id=user.id, org_id=org_id)
    _set_refresh_cookie(response, new_raw)
    return AuthOut(token=access, user=UserOut(id=user.id, email=user.email, name=user.name),
                   org=_org_out(sess, org_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, sess: Session = Depends(get_session)) -> Response:
    """Revoke the current refresh session server-side and clear the cookie."""
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        service.revoke_session(sess, raw)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(response: Response, user: User = Depends(current_user), sess: Session = Depends(get_session)) -> Response:
    """Revoke every session for the signed-in user (sign out everywhere)."""
    service.revoke_all_sessions(sess, user_id=user.id)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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


# ---- runs / audit (org-scoped) -------------------------------------------------
class RunOut(BaseModel):
    id: str
    case_name: str
    status: str
    final_state: str | None
    outcome: str | None  # final decision (APPROVE/DENY/…)
    urgency: str | None  # standard (7d) | expedited (72h) — CMS-0057-F SLA tier
    turns: int
    room_id: str | None
    started_at: str
    ended_at: str | None
    events: int          # room messages visible to my org
    private_events: int  # private reasoning events that belong to my org


class EventOut(BaseModel):
    turn: int
    author: str
    kind: str
    visibility: str
    payload: dict
    created_at: str


class RunDetailOut(BaseModel):
    run: RunOut
    events: list[EventOut]


def _run_out(run: Run, events: list[Event]) -> RunOut:
    return RunOut(
        id=run.id, case_name=run.case_name, status=run.status, final_state=run.final_state,
        outcome=run.outcome, urgency=run.urgency, turns=run.turns, room_id=run.room_id,
        started_at=run.started_at.isoformat(),
        ended_at=run.ended_at.isoformat() if run.ended_at else None,
        events=sum(1 for e in events if e.visibility == "room"),
        private_events=sum(1 for e in events if e.visibility == "private_event"),
    )


@runs_router.get("", response_model=list[RunOut])
def list_runs(org_id: str = Depends(current_org_id), sess: Session = Depends(get_session)) -> list[RunOut]:
    """Runs my org took part in (it has at least one audited event), newest first."""
    run_ids = sess.exec(select(Event.run_id).where(Event.org_id == org_id).distinct()).all()
    if not run_ids:
        return []
    runs = sess.exec(select(Run).where(Run.id.in_(run_ids)).order_by(Run.started_at.desc())).all()
    out: list[RunOut] = []
    for run in runs:
        events = sess.exec(select(Event).where(Event.run_id == run.id, Event.org_id == org_id)).all()
        out.append(_run_out(run, events))
    return out


@runs_router.get("/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str, org_id: str = Depends(current_org_id),
            sess: Session = Depends(get_session)) -> RunDetailOut:
    """A run's audit trail, scoped to my org: room messages plus only my own private events."""
    run = sess.get(Run, run_id)
    events = sess.exec(
        select(Event).where(Event.run_id == run_id, Event.org_id == org_id)
        .order_by(Event.turn, Event.created_at)
    ).all()
    if run is None or not events:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found for this organization")
    return RunDetailOut(
        run=_run_out(run, events),
        events=[EventOut(turn=e.turn, author=e.author, kind=e.kind, visibility=e.visibility,
                         payload=e.payload, created_at=e.created_at.isoformat()) for e in events],
    )
