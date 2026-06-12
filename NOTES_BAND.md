# NOTES_BAND.md — confirmed facts about Band (L0 transport)

> Source of truth: **inspection of the installed `band-sdk` 1.0.0** (`from band import ...`)
> and its REST dependency `thenvoi-client-rest` (imported as `thenvoi_rest`), plus a live
> `health_check` against `https://app.band.ai`. Anything not verified this way is marked
> **UNCONFIRMED**. Do **not** invent names beyond this file.
>
> ⚠️ The old `thenvoi-sdk` / `from thenvoi import` package and the `legal-demo` repo predate
> the Thenvoi→Band rebrand. Tool names there use a `thenvoi_` prefix — **that prefix is wrong
> for our SDK**. Our installed tools use the **`band_`** prefix (see below).

## Package & versions (confirmed)

- pip package: **`band-sdk`**, version **1.0.0** (released 2026-06-11). Import as `band`.
- Depends on: `cryptography`, `phoenix-channels-python-client`, `python-dotenv`, `pyyaml`,
  **`thenvoi-client-rest`** (the generated REST client, imported as `thenvoi_rest`).
- Framework adapters are optional extras / submodules under `band.adapters.*`:
  `anthropic, claude_sdk, langgraph, pydantic_ai, crewai, crewai_flow, gemini, letta,
  google_adk, codex, opencode, parlant, slack, a2a, a2a_gateway, acp`.
  Install per-need, e.g. `pip install 'band-sdk[langgraph,anthropic,pydantic-ai]'`.
- Live server: `app.band.ai` → `environment='prod'`, `api_version='2.0'`, server `0.13.0`. Reachable from this VPS.

## Endpoints (confirmed)

- WebSocket default: `wss://app.band.ai/api/v1/socket/websocket` (Phoenix Channels).
- REST default in `band.Agent.create`: `https://app.band.ai`.
- ⚠️ The low-level `RestClient` default `environment` is `https://platform.dev.thenvoi.com`
  (a **dev** box). **Always pass `base_url="https://app.band.ai"`** (or set `BAND_REST_URL`).

## Authentication (confirmed)

- **LLM keys never touch Band.** The SDK only takes a Band agent key / user key. The LLM
  (AI/ML API, Anthropic, Featherless, …) is called *inside our adapter*, with our own key
  from `.env`. Band only sees messages/events we choose to send. (Confirmed by architecture:
  `Agent.create(api_key=...)` is the *Band* key; the adapter holds the LLM client separately.)
- Two key types, two REST surfaces on the same `RestClient`:
  - **Agent key** → `agent_api_*` methods (act as one agent).
  - **User/Human key** → `human_api_*` methods (account-level setup: rooms, contacts, transcript).
- Header: `X-API-Key` (or `Authorization: Bearer` / JWT for human). (per docs; SDK handles it.)

### Env var names the SDK reads (confirmed by grep of package)

| var | meaning |
|---|---|
| `BAND_AGENT_ID` | this agent's id |
| `BAND_API_KEY` | this agent's Band key (Agent API) |
| `BAND_USER_API_KEY` | account/Human Band key (Human API: setup, transcript) |
| `BAND_WS_URL` | override websocket url |
| `BAND_REST_URL` | override REST base url |
| `BAND_AUTH_MODE` | agent vs user auth selection |
| `BAND_TARGET_HANDLE`, `BAND_MESSAGE`, `BAND_TRIGGER_TIMEOUT` | used by the `band` CLI one-shot send |
| `BAND_ALL_TOOLS`/`BAND_BASE_TOOLS`/`BAND_CHAT_TOOLS`/`BAND_MEMORY_TOOLS`/`BAND_TOOLS` | which tool sets to expose |

(Our own non-Band keys, e.g. `AIML_API_KEY`, `FEATHERLESS_API_KEY`, `ANTHROPIC_API_KEY`,
are app-level — exact names are **our** choice; see `.env.example`.)

## Core concepts (confirmed)

- **Account** owns agents + a Human key. **Agent** = a registered identity with its own key.
- **Room (chatroom)** = the coordination surface; mixed humans + agents.
- **`@mention` routing**: only mentioned participants receive/process a message; others see nothing.
  → mentions are by participant **id** (handle/name optional). See `ChatMessageRequestMentionsItem`.
- **Messages vs Events**: messages are visible chat (`message_type='text'`); **events** are typed
  side-channel entries (`thought | tool_call | tool_result | error | task`). We use events as the
  **private audit channel** (the other side doesn't get them routed as chat).
- **Contacts**: mutual, permission-controlled. Cross-account room participation requires a
  **bilateral contact** (request → approve) first. Within one account, contacts don't apply.
- **Peers**: discoverable agents/users you may add (`lookup_peers` / `list_*_peers`,
  with `not_in_chat=<room_id>` filter).

## Tool names exposed to agents (CONFIRMED — `band_` prefix)

From `band.ALL_TOOL_NAMES`. MCP-exposed form is prefixed `mcp__band__` (`band.MCP_TOOL_PREFIX`).

- Chat: `band_send_message`, `band_send_event`, `band_create_chatroom`,
  `band_add_participant`, `band_remove_participant`, `band_get_participants`, `band_lookup_peers`
- Contacts: `band_add_contact`, `band_remove_contact`, `band_list_contacts`,
  `band_list_contact_requests`, `band_respond_contact_request`
- Memory: `band_store_memory`, `band_get_memory`, `band_list_memories`,
  `band_supersede_memory`, `band_archive_memory`

## Registering & running an agent (confirmed)

Agents are **registered in the dashboard** (`app.band.ai`, "External Agent / brings its own
reasoning loop") → you get an **agent UUID + agent API key**. Then run from code:

```python
from band import Agent
from band.core.simple_adapter import SimpleAdapter

class IntakeAdapter(SimpleAdapter):
    async def on_message(self, msg, tools, history, participants_msg, contacts_msg,
                         *, is_session_bootstrap, room_id):
        # tools.send_message(...) / tools.send_event(...) live here
        ...

agent = Agent.create(adapter=IntakeAdapter(), agent_id="<uuid>", api_key="<agent key>",
                     ws_url="wss://app.band.ai/api/v1/socket/websocket",
                     rest_url="https://app.band.ai")
await agent.run()   # opens WS, listens until shutdown
```

- Low-level alt: `BandLink(agent_id, api_key, ws_url, rest_url)` + `AgentRuntime(link, agent_id, on_execute=...)`.
- In-room tools come from `AgentTools.from_context(ctx)` (an `AgentToolsProtocol`). For tests:
  `band.testing.FakeAgentTools` / `fake_tools`.

### `AgentTools` methods (confirmed signatures)

- `send_message(content, mentions=None)` — mentions: `list[str] | list[{handle/id/name}]`
- `send_event(content, message_type, metadata=None)` — message_type ∈ thought|tool_call|tool_result|error|task
- `create_chatroom(task_id=None) -> room_id`
- `add_participant(identifier, role='member')` ; `get_participants()` ; `remove_participant(...)`
- `lookup_peers(page=1, page_size=50)`
- `add_contact(handle, message=None)` ; `respond_contact_request(action, handle=None, request_id=None)`
  ; `list_contact_requests(page, page_size, sent_status='pending')`
- memory: `store_memory/get_memory/list_memories/supersede_memory/archive_memory`

## Cross-account contact flow (CONFIRMED via REST surface)

Two distinct surfaces on `band.client.rest.RestClient` (sync) / `AsyncRestClient`:

**Side A (clinic) initiates** — using A's key:
- agent-level: `agent_api_contacts.add_agent_contact(handle=..., message=...)`, or
- human-level: `human_api_contacts.create_contact_request(contact_request={recipient_handle, message})`
- resolve a handle first if needed: `human_api_contacts.resolve_handle(handle=...)`

**Side B (payer) approves** — using B's key:
- list: `human_api_contacts.list_received_contact_requests()` → get request `id`
- approve: `human_api_contacts.approve_contact_request(id)` (or `reject_/cancel_`)
- agent-level equivalent: `agent_api_contacts.respond_to_agent_contact_request(action='approve', handle=.. | request_id=..)`

➡️ **Key finding:** if we hold **both accounts' user keys** in `.env`, the approve step can be done
**from code** — no manual UI click required. If we only have account A's key, side B must click
**Approve** in the Contacts tab at `app.band.ai`. (To be verified live once keys exist.)

## Rooms / participants / messages / events (CONFIRMED REST shapes)

- Create room (human): `human_api_chats.create_my_chat_room(chat={task_id?})` → room id.
  Rooms have no name field; you add participants after.
- Add participant: `human_api_participants.add_my_chat_participant(chat_id, participant={participant_id, role})`
  (role ∈ owner|admin|member). Agent-side: `agent_api_participants.add_agent_chat_participant(...)`.
- Send message (human): `human_api_messages.send_my_chat_message(chat_id, message={content, mentions:[{id,...}]})`.
  Agent-side: `agent_api_messages.create_agent_chat_message(...)`.
- Send event (agent only): `agent_api_events.create_agent_chat_event(chat_id, event={content, message_type, metadata?})`.
- **Audit / transcript retrieval (human):** `human_api_messages.list_my_chat_messages(chat_id, message_type=...)`
  where `message_type ∈ text|tool_call|tool_result|thought|error` + `since=<datetime>` for streaming tail.
- Agent rehydration: `agent_api_context.get_agent_chat_context(chat_id)`.

## Streaming "thoughts/tool-calls" into the room (for the demo) — CONFIRMED mechanism

- thoughts/tool-calls are first-class typed entries (`message_type='thought'|'tool_call'`),
  creatable via `agent_api_events.create_agent_chat_event`, readable via
  `human_api_messages.list_my_chat_messages(message_type=...)`.
- **The auto-emit flag is `Emit.EXECUTION`** in `AdapterFeatures`: construct an adapter with
  `features=AdapterFeatures(emit={Emit.EXECUTION})` and it reports its reasoning/tool-calls as
  events. (Older boolean alias `enable_execution_reporting=True` is deprecated → maps to this.)
  → This is our demo "live thoughts" stream. Still to verify end-to-end live (Day 2/3).

## Agent frameworks / adapters (CONFIRMED from source)

Every framework adapter subclasses `band.core.simple_adapter.SimpleAdapter` and is passed to
`Agent.create(adapter=..., agent_id=<band uuid>, api_key=<band agent key>)`. **Two key separation:**
`Agent.create(api_key=...)` is the *Band transport* key; the LLM key is the adapter's
**`provider_key`** (param `api_key`/`<vendor>_api_key` on adapters is deprecated). Adapters live
in `band.adapters.*` and need the matching pip extra installed.

| Adapter | class | key ctor args (confirmed) |
|---|---|---|
| Anthropic SDK | `AnthropicAdapter` | `model="claude-sonnet-4-5-..."`, `provider_key`, `system_prompt`, `max_tokens`, `additional_tools`, `features` |
| LangGraph | `LangGraphAdapter` | `llm=<BaseChatModel>` (+`checkpointer`) **or** `graph_factory`/`graph`; `prompt_template`, `additional_tools`, `features` |
| Pydantic AI | `PydanticAIAdapter` | `model="openai:gpt-..."` / `"anthropic:claude-..."`, `system_prompt`, `additional_tools`, `features` |
| CrewAI | `CrewAIAdapter` | crew/model config + `features` |
| Letta | `LettaAdapter` | `config=LettaAdapterConfig(provider_key=..., ...)` |
| Gemini | `GeminiAdapter` | `model`, `provider_key`, `features` |

- `AdapterFeatures(capabilities={Capability.MEMORY}, emit={Emit.EXECUTION}, ...)` toggles memory
  tools + execution streaming + tool filters per agent.
- Custom tools beyond the Band toolset: `additional_tools=[...]` (framework-native tool signature).
- **UNCONFIRMED:** how to point an adapter at the **AI/ML API** base_url (OpenAI/Anthropic-compatible
  gateway) vs the native vendor. AnthropicAdapter shows no `base_url` param. Options to check:
  pass a pre-configured client (LangGraph `llm=`, PydanticAI model/provider), or env base_url. Verify Day 2.

## Things still UNCONFIRMED (verify before relying on them)

- [ ] Exact `.env` var the SDK uses for the **Human** key in agent runtime vs `BAND_USER_API_KEY` (named consistently? CLI uses it).
- [ ] Whether approve-from-code works with a Human key for the *recipient* account (the cross-account hypothesis). **This is the Day-1 spike.**
- [x] Auto-emit-thoughts flag → `AdapterFeatures(emit={Emit.EXECUTION})` (confirmed; live-verify Day 2/3).
- [ ] How to route adapters through the AI/ML API gateway base_url vs native vendor — Day 2.
- [ ] Whether `create_my_chat_room` lets the creator pre-add cross-account participants, or each side must add via contact. **Spike.**
- [ ] Header/JWT specifics — handled by SDK, not hand-rolled.
