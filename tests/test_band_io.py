"""Tests for the Band I/O seam using Band's own test double, FakeAgentTools.
Verifies envelope (de)serialization and that visibility routes to message vs event.
"""

import asyncio

from band.testing import FakeAgentTools

from engine import band_io
from protocol import Envelope, Kind, Visibility


def _envelope(**kw) -> Envelope:
    base = dict(case_id="case-1", turn=1, author="provider.counsel", kind=Kind.PROPOSAL, payload={"x": 1})
    base.update(kw)
    return Envelope(**base)


def test_serialize_parse_roundtrip():
    env = _envelope()
    assert band_io.parse(band_io.serialize(env)) == env


def test_parse_returns_none_on_free_text():
    assert band_io.parse("hi, can someone look at this?") is None
    assert band_io.parse("{not valid json") is None


def test_emit_room_sends_readable_message_with_mentions():
    tools = FakeAgentTools()
    env = _envelope(visibility=Visibility.ROOM, payload={"message": "Please review this case.", "reasoning": "x"})
    asyncio.run(band_io.emit(tools, env, mentions=["payer.reviewer"]))
    tools.assert_message_sent(count=1)
    sent = tools.messages_sent[0]
    # Band gets the human-readable message, NOT the wire envelope JSON.
    assert sent["content"] == "Please review this case."
    assert band_io.parse(sent["content"]) is None
    assert sent["mentions"] == [{"id": "payer.reviewer"}]


def test_emit_unwraps_a_nested_json_blob():
    tools = FakeAgentTools()
    blob = '{"message": "Authorization approved.", "reasoning": "criteria met"}'
    env = _envelope(visibility=Visibility.ROOM, payload={"message": blob})
    asyncio.run(band_io.emit(tools, env))
    assert tools.messages_sent[0]["content"] == "Authorization approved."


def test_emit_private_event_uses_audit_channel():
    tools = FakeAgentTools()
    env = _envelope(visibility=Visibility.PRIVATE_EVENT, kind=Kind.INFO_REQUEST)
    asyncio.run(band_io.emit(tools, env))
    tools.assert_event_sent(message_type="thought", count=1)
    # nothing leaked into the routed chat
    assert tools.messages_sent == []
    ev = tools.events_sent[0]
    assert ev["metadata"]["case_id"] == "case-1" and ev["metadata"]["kind"] == "INFO_REQUEST"
