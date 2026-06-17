"""Scenario launcher — run a live AuthBridge negotiation over real Band into the dashboard.

Drives one synthetic prior-auth case through the coordinator with the LLM narrator (AI/ML
gateway), posting each move from the correct Band account: provider roles speak as the clinic
agent, payer roles as the payer agent, in one shared room. The spectator dashboard
(https://syntony.live) renders that room from each account's side, so the privacy model is
visible (a private `thought` shows only on its author's column).

Each role posts under its OWN Band identity (9 distinct agents: the 2 account primaries +
7 provisioned specialists; the human Medical Director has no agent) — falling back to the side
primary if a specialist isn't provisioned. Mentions map logical role ids → real Band agent UUIDs.
(The mesh-wiring mirrors ``live_run._build_tools_for`` — dedupe into one helper is a TODO.)

Usage:
    PYTHONPATH=. .venv/bin/python run_all.py [--case NAME] [--room ID|--fresh] [--full] [--no-llm]
    For the pitch video: ``--full --fresh`` (strong tier, fresh room with all 9 agents).
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from domains.authbridge.roles import ROLES
from domains.authbridge.runner import llm_narrator, run_authbridge
from engine.agent_base import Side
from engine.band_room import RestRoomTools, add_participants, agent_client, ensure_room
from protocol import Envelope


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Run a live AuthBridge negotiation over Band.")
    ap.add_argument("--case", default="mri_lumbar_dx_mismatch")
    ap.add_argument("--room", default=os.environ.get("SYNTONY_VIEW_ROOM", "").strip() or None)
    ap.add_argument("--fresh", action="store_true", help="create a new room even if one is configured")
    ap.add_argument("--full", action="store_true", help="use the strong model tier (default: cheap Haiku)")
    ap.add_argument("--no-llm", action="store_true", help="deterministic narration, no LLM calls")
    ap.add_argument("--no-persist", action="store_true", help="skip writing the run to the control-plane audit")
    args = ap.parse_args()

    rest_url = os.environ.get("BAND_REST_URL", "https://app.band.ai")
    clinic_id = os.environ["CLINIC_AGENT_ID"]            # provider primary (Clinic Intake)
    clinic_key = os.environ["CLINIC_AGENT_API_KEY"]
    payer_id = os.environ["PAYER_AGENT_ID"]              # payer primary (Payer Reviewer)
    payer_key = os.environ["PAYER_AGENT_API_KEY"]

    # Resolve each role to its OWN Band identity (env stem PROVIDER_COUNSEL_AGENT_ID/…), falling
    # back to the side primary if a specialist isn't provisioned.
    def resolve(rid: str, spec) -> tuple[str, str]:
        stem = rid.upper().replace(".", "_")
        aid = os.environ.get(f"{stem}_AGENT_ID", "").strip()
        akey = os.environ.get(f"{stem}_AGENT_API_KEY", "").strip()
        if aid and akey:
            return aid, akey
        return (payer_id, payer_key) if spec.side is Side.PAYER else (clinic_id, clinic_key)

    ident = {rid: resolve(rid, spec) for rid, spec in ROLES.items() if not spec.is_human}
    mention_map = {rid: aid for rid, (aid, _) in ident.items()}
    for rid, spec in ROLES.items():
        if spec.is_human:
            mention_map[rid] = payer_id if spec.side is Side.PAYER else clinic_id

    agents: dict[str, str] = {clinic_id: clinic_key, payer_id: payer_key}
    for aid, akey in ident.values():
        agents.setdefault(aid, akey)
    clinic = agent_client(clinic_key, rest_url)
    clients = {clinic_id: clinic}
    for aid, akey in agents.items():
        clients.setdefault(aid, agent_client(akey, rest_url))

    # each primary adds its own-account specialists (same-account add; cross-account needs a contact)
    provider_specialists = [aid for rid, (aid, _) in ident.items()
                            if ROLES[rid].side is Side.PROVIDER and aid != clinic_id]
    payer_specialists = [aid for rid, (aid, _) in ident.items()
                         if ROLES[rid].side is Side.PAYER and aid != payer_id]
    room_id = None if args.fresh else args.room
    room = ensure_room(clinic, *provider_specialists, payer_id, room_id=room_id)
    if room_id is None:
        add_participants(clients[payer_id], room, payer_specialists)
    print(f"room: {room} | {len(agents)} band identities")

    tools_by_role = {}
    for rid, (aid, _) in ident.items():
        default = clinic_id if ROLES[rid].side is Side.PAYER else payer_id
        tools_by_role[rid] = RestRoomTools(clients[aid], room, mention_map=mention_map,
                                           self_id=aid, default_mention=default)
    clinic_primary = RestRoomTools(clinic, room, mention_map=mention_map, self_id=clinic_id, default_mention=payer_id)
    payer_primary = RestRoomTools(clients[payer_id], room, mention_map=mention_map, self_id=payer_id, default_mention=clinic_id)

    def tools_for(env: Envelope):
        if env.author in tools_by_role:
            return tools_by_role[env.author]
        spec = ROLES.get(env.author)
        return payer_primary if (spec and spec.side is Side.PAYER) else clinic_primary

    narrate = None if args.no_llm else llm_narrator(debug=not args.full)
    tier = "deterministic" if args.no_llm else ("strong" if args.full else "cheap/Haiku")
    print(f"case: {args.case} | narration: {tier}\n")

    res = asyncio.run(
        run_authbridge(args.case, tools_for=tools_for, narrate=narrate, case_id=f"live-{args.case}")
    )

    for e in res.history:
        out = f" [{e.payload.get('outcome')}]" if e.payload.get("outcome") else ""
        print(f"  turn {e.turn} | {e.author} | {e.kind.value}{out}")
        print(f"      {e.payload.get('message', '')}")
    print(f"\nended: state={res.final_state.value}, turns={res.turns}, stop={res.stopped}")

    if not args.no_persist:
        _persist(args.case, room, res)

    print(f"watch it: https://syntony.live/?room={room}#/live  (or set SYNTONY_VIEW_ROOM={room} + restart syntony)")


def _persist(case_name: str, room_id: str, res) -> None:
    """Record the negotiation into the org-scoped control-plane audit (best-effort)."""
    try:
        from control import ingest, seed
        from control.db import session as open_session
        from domains.authbridge.cases import ALL_CASES
        from domains.authbridge.schema import Urgency

        def author_side(author: str) -> str:
            spec = ROLES.get(author)
            return spec.side.value if spec else "neutral"

        # CMS-0057-F SLA tier from the case's urgency: URGENT → expedited (72h), else standard (7d).
        req = ALL_CASES[case_name]()
        urgency = "expedited" if req.urgency is Urgency.URGENT else "standard"

        with open_session() as sess:
            seed.seed_demo(sess)  # idempotent — ensures the Clinic/Payer orgs exist
            side_to_org = seed.demo_side_orgs(sess)
            run = ingest.persist_result(
                sess, result=res, side_to_org=side_to_org, author_side=author_side,
                case_name=case_name, room_id=room_id, urgency=urgency,
            )
        print(f"audit: persisted run {run.id} (sign in as clinic@demo.syntony / payer@demo.syntony)")
    except Exception as e:  # noqa: BLE001 — persistence must never break the live demo
        print(f"audit: skipped ({type(e).__name__}: {str(e)[:120]})")


if __name__ == "__main__":
    main()
