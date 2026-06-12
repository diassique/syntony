"""Spike 00 — preflight: confirm BOTH accounts authenticate before the risky contact dance.

Uses only CONFIRMED, side-effect-free REST calls:
  - system.health_check()             (no auth)
  - test.authentication()             (validates the key)
  - human_api_profile.get_my_profile()(prints this account's handle/id)
  - human_api_agents.list_my_agents() (prints registered agents)

Run from repo root:  python spikes/00_preflight.py
"""

from _common import REST_URL, account, human_client
from band.client.rest import RestClient


def main() -> None:
    print("== health (no auth) ==")
    hc = RestClient(api_key="none", base_url=REST_URL).system.health_check()
    print(f"  status={hc.status} env={hc.environment} server={hc.version}")

    for name in ("clinic", "payer"):
        print(f"\n== account: {name} ==")
        acc = account(name)
        c = human_client(acc)
        try:
            print("  auth:", c.test.authentication())
        except Exception as e:  # noqa: BLE001
            print(f"  AUTH FAILED: {type(e).__name__}: {str(e)[:160]}")
            continue
        try:
            prof = c.human_api_profile.get_my_profile()
            print("  profile:", prof)
        except Exception as e:  # noqa: BLE001
            print(f"  profile err: {type(e).__name__}: {str(e)[:160]}")
        try:
            agents = c.human_api_agents.list_my_agents()
            print("  agents:", agents)
        except Exception as e:  # noqa: BLE001
            print(f"  agents err: {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    main()
