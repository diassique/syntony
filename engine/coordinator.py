"""L2 — ``Coordinator``.

Drives a case through the L1 state machine. Validates that each move
is a legal transition, decides when to request info, when to recruit another
specialist (``lookup_peers`` + ``add_participant``), and when to escalate to a human
(``ARBITER``). Domain thresholds/policies are injected from L3; the FSM itself lives
in ``protocol.state_machine`` and is only *read* here.
"""
