"""Provision the balanced-mesh Band agents from code — no dashboard clicks needed.

Background: Syntony's 10 logical roles previously collapsed onto the 2 account agents
(clinic ↔ payer). To make the cross-org mesh *visible on Band* (multiple real agent
participants per side), we register a few more external agents per account. Band's
``human_api_agents.register_my_agent`` does this from code with the account's **Human API
key** and returns the new agent's id + API key (shown once) — verified against the installed
``thenvoi-client-rest``. See NOTES_BAND.md.

Balanced mesh = reuse the existing 2 agents as the side *primaries* (provider.intake,
payer.reviewer) and register **4 new** specialist agents:
  provider account → counsel, eligibility   payer account → pharmacy, guidelines
Non-promoted roles (appeals, compliance, notification) keep posting as the side primary.

Prereqs in .env: ``CLINIC_USER_API_KEY`` + ``PAYER_USER_API_KEY`` (the two account Human keys).
Run:  .venv/bin/python provision_agents.py    → prints the env lines to paste into .env.
Idempotent by name: re-running skips agents that already exist (Band shows the key only once,
so to rotate a key, delete the agent in the dashboard and re-run).
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from thenvoi_rest import AgentRegisterRequest, RestClient

#: role_id → (account Human-key env var, agent display name, description).
NEW_AGENTS: dict[str, tuple[str, str, str]] = {
    "provider.counsel": ("CLINIC_USER_API_KEY", "Clinic Counsel",
                         "Provider-side medical-necessity counsel agent (Syntony prior-auth mesh)."),
    "provider.eligibility": ("CLINIC_USER_API_KEY", "Clinic Eligibility & Benefits",
                             "Provider-side eligibility/benefits agent (Syntony prior-auth mesh)."),
    "payer.pharmacy": ("PAYER_USER_API_KEY", "Payer Pharmacy & Formulary",
                       "Payer-side pharmacy/formulary agent (Syntony prior-auth mesh)."),
    "payer.guidelines": ("PAYER_USER_API_KEY", "Payer Clinical Guidelines",
                         "Payer-side clinical-guidelines agent (Syntony prior-auth mesh)."),
}


def env_key(role_id: str) -> str:
    """provider.counsel → PROVIDER_COUNSEL (the env-var stem the live wiring reads)."""
    return role_id.upper().replace(".", "_")


def main() -> None:
    load_dotenv()
    base = os.environ.get("BAND_REST_URL", "https://app.band.ai")
    clients: dict[str, RestClient] = {}

    def client_for(human_env: str) -> RestClient:
        key = os.environ.get(human_env, "").strip()
        if not key:
            sys.exit(f"ERROR: {human_env} not set in .env — add the account's Human API key first "
                     f"(app.band.ai → Settings → API keys).")
        if human_env not in clients:
            clients[human_env] = RestClient(api_key=key, base_url=base)
        return clients[human_env]

    env_lines: list[str] = []
    for role_id, (human_env, name, desc) in NEW_AGENTS.items():
        client = client_for(human_env)
        try:
            existing = {a.name: a for a in client.human_api_agents.list_my_agents(page_size=100).data}
        except Exception as e:  # noqa: BLE001 — listing is best-effort idempotency, not critical
            print(f"  (could not list existing agents on {human_env}: {type(e).__name__}; will register)")
            existing = {}
        if name in existing:
            print(f"• {name}: already registered (id={existing[name].id}); key not re-shown.")
            env_lines.append(f"{env_key(role_id)}_AGENT_ID={existing[name].id}")
            continue
        resp = client.human_api_agents.register_my_agent(
            agent=AgentRegisterRequest(name=name, description=desc))
        agent_id = resp.data.agent.id
        api_key = resp.data.credentials.api_key
        print(f"✓ registered {name}: id={agent_id}")
        env_lines.append(f"{env_key(role_id)}_AGENT_ID={agent_id}")
        env_lines.append(f"{env_key(role_id)}_AGENT_API_KEY={api_key}")

    print("\n# ---- paste these into .env (then I wire the mesh + run the cross-account contact dance) ----")
    print("\n".join(env_lines))


if __name__ == "__main__":
    main()
