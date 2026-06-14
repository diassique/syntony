"""Scenario launcher — run a live AuthBridge negotiation over real Band into the dashboard.

Drives one synthetic prior-auth case through the coordinator with the LLM narrator (AI/ML
gateway), posting each move from the correct Band account: provider roles speak as the clinic
agent, payer roles as the payer agent, in one shared room. The spectator dashboard
(https://syntony.live) renders that room from each account's side, so the privacy model is
visible (a private `thought` shows only on its author's column).

Two Band agents play several logical roles each (clinic = intake+counsel, payer = reviewer+MD);
mentions are mapped from logical role ids to the real Band agent UUIDs so routing works.

Usage:
    PYTHONPATH=. .venv/bin/python run_all.py [--case NAME] [--room ID|--fresh] [--full] [--no-llm]
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv

from domains.authbridge.roles import ROLES
from domains.authbridge.runner import llm_narrator, run_authbridge
from engine.agent_base import Side
from engine.band_room import RestRoomTools, agent_client, ensure_room
from protocol import Envelope


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Run a live AuthBridge negotiation over Band.")
    ap.add_argument("--case", default="mri_lumbar_dx_mismatch")
    ap.add_argument("--room", default=os.environ.get("SYNTONY_VIEW_ROOM", "").strip() or None)
    ap.add_argument("--fresh", action="store_true", help="create a new room even if one is configured")
    ap.add_argument("--full", action="store_true", help="use the strong model tier (default: cheap Haiku)")
    ap.add_argument("--no-llm", action="store_true", help="deterministic narration, no LLM calls")
    args = ap.parse_args()

    rest_url = os.environ.get("BAND_REST_URL", "https://app.band.ai")
    clinic_id = os.environ["CLINIC_AGENT_ID"]
    payer_id = os.environ["PAYER_AGENT_ID"]
    clinic = agent_client(os.environ["CLINIC_AGENT_API_KEY"], rest_url)
    payer = agent_client(os.environ["PAYER_AGENT_API_KEY"], rest_url)

    room = ensure_room(clinic, payer_id, room_id=None if args.fresh else args.room)
    print(f"room: {room}")

    # logical role id -> Band agent UUID (for @mention routing)
    mention_map = {
        rid: (payer_id if spec.side is Side.PAYER else clinic_id) for rid, spec in ROLES.items()
    }
    clinic_tools = RestRoomTools(clinic, room, mention_map=mention_map, self_id=clinic_id, default_mention=payer_id)
    payer_tools = RestRoomTools(payer, room, mention_map=mention_map, self_id=payer_id, default_mention=clinic_id)

    def tools_for(env: Envelope):
        spec = ROLES.get(env.author)
        return payer_tools if (spec and spec.side is Side.PAYER) else clinic_tools

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
    print(f"watch it: https://syntony.live/?room={room}#/live  (or set SYNTONY_VIEW_ROOM={room} + restart syntony)")


if __name__ == "__main__":
    main()
