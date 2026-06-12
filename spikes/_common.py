"""Shared helpers for throwaway connectivity spikes. NOT production code.

Confirmed against band-sdk 1.0.0 (see ../NOTES_BAND.md). Loads .env and builds a
synchronous Band REST client per account. Two accounts: 'clinic' and 'payer'.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from band.client.rest import RestClient

load_dotenv()  # reads ../.env when run from the repo root

REST_URL = os.environ.get("BAND_REST_URL", "https://app.band.ai")


@dataclass(frozen=True)
class Account:
    name: str
    user_api_key: str
    handle: str
    agent_id: str
    agent_api_key: str


def _require(var: str) -> str:
    val = os.environ.get(var, "").strip()
    if not val:
        raise SystemExit(f"Missing required env var: {var} (copy .env.example -> .env and fill it)")
    return val


def account(name: str) -> Account:
    """name in {'clinic','payer'} -> credentials from env."""
    p = name.upper()
    return Account(
        name=name,
        user_api_key=_require(f"{p}_USER_API_KEY"),
        handle=os.environ.get(f"{p}_HANDLE", "").strip(),
        agent_id=os.environ.get(f"{p}_AGENT_ID", "").strip(),
        agent_api_key=os.environ.get(f"{p}_AGENT_API_KEY", "").strip(),
    )


def human_client(acc: Account) -> RestClient:
    """REST client authenticated with the account's Human/User key (human_api_* calls)."""
    return RestClient(api_key=acc.user_api_key, base_url=REST_URL)


def agent_client(acc: Account) -> RestClient:
    """REST client authenticated with the account's Agent key (agent_api_* calls)."""
    return RestClient(api_key=acc.agent_api_key, base_url=REST_URL)
