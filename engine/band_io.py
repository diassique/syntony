"""L2 — Band I/O seam: the ONE place that turns ``Envelope``s into Band traffic and back.

Keeps the Band SDK out of the rest of the engine. Two pure functions (serialize/parse)
plus one async ``emit`` that honors ``visibility``:

- ``Visibility.ROOM``         -> ``tools.send_message(content, mentions=...)`` (routed chat)
- ``Visibility.PRIVATE_EVENT`` -> ``tools.send_event(content, message_type, metadata=...)`` (audit channel)

``tools`` is anything implementing Band's AgentToolsProtocol — the real ``AgentTools`` in
production, or ``band.testing.FakeAgentTools`` in tests. We never import a concrete Band
client here; we only call the documented Band tool methods.
"""

from __future__ import annotations

import json
from typing import Any

from protocol import Envelope, Visibility

#: Band event ``message_type`` we use for private protocol traffic on the audit channel.
#: Band's enum is {tool_call, tool_result, thought, error, task}; protocol/strategy notes
#: ride as 'thought' so they surface in the audit view but never as routed chat.
PRIVATE_EVENT_TYPE = "thought"

#: Marker so a parser can tell a Syntony envelope apart from free-form human chat.
_MARKER = "syntony.envelope"


def serialize(env: Envelope) -> str:
    """Envelope -> wire string (a JSON object carrying a marker + the envelope)."""
    return Envelope.model_dump_json(env)  # the marker lives in metadata on private events


def parse(content: str) -> Envelope | None:
    """Wire string -> Envelope, or None if it isn't a well-formed Syntony envelope
    (e.g. a human typed free text into the room)."""
    try:
        return Envelope.model_validate_json(content)
    except (ValueError, TypeError):
        return None


def mentions_for(*identifiers: str) -> list[dict[str, str]]:
    """Build Band mention items from participant ids. (Band mention item: {'id': ...})."""
    return [{"id": i} for i in identifiers if i]


def _readable(text: str | None) -> str:
    """Best-effort plain text for the human-facing Band surface. If a field accidentally holds a
    JSON blob (a weak model occasionally nests its structured output), pull the inner
    message/reasoning so Band never shows raw JSON."""
    s = (text or "").strip()
    if s[:1] in ("{", "["):
        try:
            obj = json.loads(s)
        except (ValueError, TypeError):
            return s
        if isinstance(obj, dict):
            return str(obj.get("message") or obj.get("reasoning") or "").strip() or s
    return s


async def emit(
    tools: Any,
    env: Envelope,
    *,
    mentions: list[str] | None = None,
) -> Any:
    """Send an envelope through Band, honoring its visibility.

    Band is the **human-facing** cross-org surface, so we post the readable message/reasoning —
    NOT our wire envelope (the structured envelope is persisted to our own audit trail). The
    machine-readable details ride in event ``metadata`` on the private channel. ``mentions`` are
    participant ids to @mention (room messages only); routing is the coordinator's decision.
    """
    payload = env.payload or {}
    if env.visibility is Visibility.PRIVATE_EVENT:
        # audit/thought channel: readable reasoning as content; structure travels in metadata
        content = _readable(payload.get("reasoning")) or _readable(payload.get("message")) or serialize(env)
        meta = {"marker": _MARKER, "case_id": env.case_id, "kind": env.kind.value, "turn": env.turn}
        for k in ("pa_event", "outcome", "denial_reason", "model", "via", "auth_number"):
            if payload.get(k):
                meta[k] = payload[k]
        return await tools.send_event(content, message_type=PRIVATE_EVENT_TYPE, metadata=meta)
    # routed chat: the human-readable message, never the raw envelope
    content = _readable(payload.get("message")) or serialize(env)
    return await tools.send_message(content, mentions=mentions_for(*(mentions or [])))
