"""Scenario launcher.

Boots every agent in a scenario as its own long-lived task (each
``Agent.create(...).run()`` on its own Band account/key), wires them into one room, and
sends the opening @mention.

Usage:  python run_all.py --domain authbridge --scenario mri_lumbar
"""

if __name__ == "__main__":
    raise SystemExit("No scenario wired yet. See engine/ and domains/ to add one.")
