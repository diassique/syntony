"""Persist a finished negotiation into the org-scoped audit trail.

This is the bridge that turns a transcript (a coordinator ``CoordinatorResult`` — really any
object with a ``history`` of envelopes, a ``final_state`` and a ``stopped`` reason) into rows
in the control plane. It is deliberately domain-agnostic: the caller injects how to map an
envelope's author → side, and which org each side belongs to.

The privacy model is enforced here, by construction:

- a **room** message is recorded once per org (both sides see what's posted to the room);
- an envelope's private ``reasoning`` is recorded as a ``private_event`` for **only the
  author's side's org** — so "my org's audit" (events where ``org_id == mine``) shows my own
  strategy and never the counterparty's.

It also writes one ``run`` usage row per org (usage-based metering).
"""

from __future__ import annotations

from typing import Any, Callable

from sqlmodel import Session

from . import service
from .models import RunStatus


def record_envelope(
    sess: Session,
    *,
    run: Any,
    env: Any,
    org_ids: list[str],
    side_to_org: dict[str, str],
    author_side: Callable[[str], str],
) -> None:
    """Record one envelope into the audit trail, enforcing the privacy model:

    - the **room** message is recorded once per participating org (``org_ids``);
    - the envelope's private ``reasoning`` is recorded as a ``private_event`` for **only the
      author's side's org**.

    Shared by the batch ``persist_result`` and the live (streamed) run path so both produce
    byte-identical audit rows.
    """
    kind = env.kind.value if hasattr(env.kind, "value") else str(env.kind)
    message = (env.payload.get("message") or "").strip()
    room_payload: dict[str, Any] = {"message": message}
    for k in ("outcome", "pa_event", "denial_reason"):  # carry PA audit semantics through
        if env.payload.get(k):
            room_payload[k] = env.payload[k]

    for org_id in org_ids:  # room message → every participating org's audit
        service.record_event(sess, run=run, org_id=org_id, turn=env.turn, author=env.author,
                             kind=kind, visibility="room", payload=room_payload)

    reasoning = (env.payload.get("reasoning") or "").strip()
    author_org = side_to_org.get(author_side(env.author))
    if reasoning and author_org:  # private reasoning → only the author's side's org
        service.record_event(sess, run=run, org_id=author_org, turn=env.turn, author=env.author,
                             kind=kind, visibility="private_event", payload={"reasoning": reasoning})


def persist_result(
    sess: Session,
    *,
    result: Any,
    side_to_org: dict[str, str],
    author_side: Callable[[str], str],
    case_name: str,
    room_id: str | None = None,
    model: str = "",
    urgency: str | None = None,
) -> Any:
    """Persist ``result`` to the audit trail and return the created ``Run``.

    ``side_to_org`` maps a side string (e.g. "provider"/"payer") → org id. ``author_side``
    maps an envelope author (role id) → its side string. Orgs not in ``side_to_org`` are
    simply not audited.
    """
    org_ids = list(dict.fromkeys(side_to_org.values()))  # de-duped, order-preserving
    if not org_ids:
        raise ValueError("side_to_org is empty — nothing to attribute the audit to")

    run = service.start_run(sess, org_id=org_ids[0], case_name=case_name, room_id=room_id)
    run.urgency = urgency

    for env in result.history:
        record_envelope(sess, run=run, env=env, org_ids=org_ids,
                        side_to_org=side_to_org, author_side=author_side)

    for org_id in org_ids:
        service.record_usage(sess, org_id=org_id, run_id=run.id, kind="run", model=model, units=1)

    status = RunStatus.SUCCEEDED.value if result.stopped == "terminal" else RunStatus.FAILED.value
    final_state = result.final_state.value if hasattr(result.final_state, "value") else str(result.final_state)
    # the case's final decision = the last envelope that carried an outcome
    outcome = next((e.payload.get("outcome") for e in reversed(result.history) if e.payload.get("outcome")), None)
    return service.finish_run(sess, run=run, status=status, final_state=final_state,
                              turns=result.turns, outcome=outcome)
