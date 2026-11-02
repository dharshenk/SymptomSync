Status: ready-for-agent

# Layer the /webhook chat flow

## Problem Statement

The `/webhook` route is thin, but the coupling has moved into the chat flow behind it. As a maintainer I find that:

- Handling an Incoming Message or a Decision mixes Telegram types, Patient lookup, history persistence, building the agent's input, running the agent, and sending the Reply, all in one function.
- Persisting a finished run and sending it to Telegram happen in the same step.
- Every flow receives one bundle holding the agent, the database services and the Telegram client.
- Telegram-specific values (button callback strings, the Telegram button layout of the Approval Prompt) leak into the core flow.
- The agent runtime mixes prompt building, run execution, and tool-context assembly that needs the database.
- `HTTPException` is raised from deep inside the flow.

This makes the flow hard to test without Telegram, and makes bringing back WhatsApp (currently commented out) a change to the core.

## Solution

Split the flow into four layers, each depending only on the one below it, so the core is channel-agnostic and Telegram is one adapter. The Patient-facing behavior does not change, with one exception: new user messages are stored without a date prefix (see Implementation Decisions).

| Layer | Owns | Must not know about |
|---|---|---|
| 1. Transport (`POST /webhook` + Telegram adapter) | Parsing the payload into an Incoming Message or Decision. Mapping callback strings to a Decision. Removing buttons and acknowledging the press before the run. The typing indicator. Rendering a Reply (text, or choices as an inline keyboard) and sending it. A 422 for unknown payloads. A small acknowledgement as the HTTP body. | The agent, the database, the Pending Approval lifecycle |
| 2. Application (`ChatApplication`: `handle_message`, `handle_decision`) | Resolving Sender ID to Patient and Chat Session (get-or-create). Persisting messages and agent items. The Pending Approval lifecycle. Building the tool context. Building the Approval Prompt text. Returning a neutral Reply. | Telegram, FastAPI, SDK types |
| 3. Agent runtime (`AgentRuntime`) | Rendering the system prompt. Assembling the input. Running or resuming a serialized state. Returning `Finished` or `NeedsApproval`. Tracing the run. | The database, Patient, Telegram |
| 4. Persistence | Existing services and Postgres client, unchanged. | Everything above |

## User Stories

1. As a maintainer, I want the core chat flow to know nothing about Telegram, so that I can add or restore another Channel without touching it.
2. As a maintainer, I want the transport layer to turn a Telegram update into an Incoming Message or a Decision, so that the core only sees channel-neutral inputs.
3. As a maintainer, I want button callback strings mapped to a `Decision` enum in the Telegram adapter, so that `approve` / `changes_needed` never appear in the core.
4. As a maintainer, I want the use cases to return a Reply instead of sending it, so that I can test them without a Telegram client.
5. As a maintainer, I want a Reply to carry optional choices (label plus Decision), so that an Approval Prompt is expressed without Telegram's keyboard format.
6. As a maintainer, I want the Telegram adapter to render choices as an inline keyboard, so that the Patient still sees Go Ahead and Changes needed buttons.
7. As a Patient, I want the Approval Prompt to still show my booking summary with Go Ahead and Changes needed buttons, so that I can confirm or correct before booking.
8. As a Patient, I want the typing indicator to keep showing while the assistant works, so that I know it has not stalled.
9. As a Patient, I want my button press acknowledged and the buttons removed before the agent runs, so that I cannot press twice and the spinner stops promptly.
10. As a Patient, I want a repeated press on the same buttons to do nothing the second time, so that my booking is never made twice.
11. As a Patient, I want a message sent while a Decision is pending to get the Approval Prompt again, so that I know what the assistant is waiting for.
12. As a Patient, I want a message sent while my Decision is being applied to get a "still working" reply, so that a second run does not start.
13. As a maintainer, I want one component to own the Pending Approval lifecycle (save when paused, claim on Decision, restore on error, ignore messages while pending), so that the rules live in one place.
14. As a maintainer, I want the agent runtime to be stateless about approvals, so that it only turns a stored state string into a run and back.
15. As a maintainer, I want the SDK types to stay behind `AgentRuntime`, so that the use cases can be tested with a fake runtime and no LLM.
16. As a maintainer, I want `AgentRuntime` to return `Finished` or `NeedsApproval`, so that the use cases branch on a domain outcome rather than SDK result fields.
17. As a maintainer, I want one shared `resolve_conversation` that gets or creates the Patient and Chat Session, so that both flows use the same lookup.
18. As a Patient, I want a Decision from a sender the system has not seen to be handled gracefully rather than an HTTP 404, so that stray presses do not produce errors.
19. As a maintainer, I want building the tool context (latest appointment, Intake State creation) in the application layer, so that DB-backed logic is not in the agent runtime.
20. As an operator, I want the doctor ID read from configuration rather than hardcoded, so that it can change without a code edit.
21. As a maintainer, I want the legacy transcript seeding isolated as a small, clearly marked function, so that I can delete it once old sessions are gone.
22. As a maintainer, I want dependencies passed to `ChatApplication` explicitly (DB services plus an `AgentRuntime`), so that it does not receive the Telegram client or the agent bundle.
23. As a maintainer, I want `HTTPException` raised only in the transport layer, so that the core can be reused outside FastAPI.
24. As a maintainer, I want the webhook to return a small acknowledgement instead of the reply text, so that the HTTP body is not mistaken for the channel's delivery.
25. As a maintainer, I want a failed Telegram send to be logged, not raised, so that Telegram does not redeliver the update and re-run the agent (existing behavior, preserved).
26. As a maintainer, I want unknown payloads to still return 422, so that malformed updates are rejected.
27. As a Patient, I want the assistant to still know today's date, so that "tomorrow" and "next Monday" resolve correctly.
28. As an operator, I want the prompt cache to stay valid within a day, so that cost stays low; invalidation at the day boundary is acceptable.
29. As a maintainer, I want each migration step to leave the test suite green, so that the refactor can ship incrementally.
30. As a maintainer, I want the neutral vocabulary (Incoming Message, Reply, Channel) in `GLOSSARY.md`, so that code and docs use the same terms.

## Implementation Decisions

- **Four layers** as in the table above. Dependencies point downward only.
- **Neutral types**: `IncomingMessage` (Sender ID, text), `IncomingDecision` (Sender ID, `Decision`), `Decision` enum (`GO_AHEAD`, `CHANGES_NEEDED`), and `Reply` (text plus an optional list of `Choice(label, decision)`; an empty list means plain text).
- **Use cases return a Reply and never send.** Only the transport layer sends to the Channel. The Telegram client is not available to the application layer.
- **Ordering lives in the transport adapter.** For a button press: parse, remove buttons and acknowledge, run the use case under the typing indicator, then send the Reply. The use case never calls back into the adapter.
- **HTTP body**: a small acknowledgement; replies are asserted on the use-case result, not the HTTP body. Existing tests that assert on the body must be updated.
- **Pending Approval lifecycle** is owned by a single application-layer unit: save when a run pauses, claim on a Decision (so a repeat finds nothing), restore on error, and short-circuit incoming messages while a row exists (re-send the Approval Prompt, or a "still working" reply if processing).
- **`AgentRuntime`** wraps the OpenAI Agents SDK: renders the system prompt, assembles the input, runs or resumes from a stored state string, and returns `Finished(text, items)` or `NeedsApproval(state)`. When resuming, the runtime must not pass a context to the run (it would drop the approval decisions); the application layer supplies the rebuilt context when restoring state.
- **Conversation resolution**: one `resolve_conversation(sender_id)` does get-or-create for the Patient and the Chat Session, used by both flows. A Decision from an unknown sender now creates a Patient instead of returning 404; the subsequent claim finds nothing and the flow ends with "nothing waiting for your approval".
- **Tool context** assembly (latest appointment, Intake State creation if missing) moves to the application layer; the doctor ID comes from configuration instead of a hardcoded constant.
- **Date handling (changes behavior)**: the date lives only in the system prompt, rendered per run at day granularity, e.g. "Thursday, October 29, 2026", with no time of day. New user messages are persisted as the raw text with no `[Current date: ...]` prefix. Existing rows that already carry the prefix are left as they are (no backfill), so history may mix stamped and unstamped messages. The prompt cache invalidates once a day; this was accepted. No ADR: the decision is easy to reverse and not surprising.
- **Legacy transcript seeding** (building agent items from the text transcript for sessions that predate agent item storage) is kept as an isolated, removable function in the application layer.
- **Dependency injection**: the transport layer builds a `ChatApplication` holding only the DB services and an `AgentRuntime`. The `ChatServices` bundle is removed. `HTTPException` appears only in the transport layer.
- **Migration order** (each step ships on its own with the suite green):
  1. Add the neutral types.
  2. Extract `resolve_conversation` and move tool-context building into the application layer, with the doctor ID from config.
  3. Wrap the SDK in `AgentRuntime`, with prompt building behind it, and move the date out of the user message and into the system prompt only.
  4. Make the use cases return a Reply and move all sending out of them.
  5. Build the Telegram adapter (parse, ack, typing, render) and thin the route.
  6. Replace `ChatServices` with the injected `ChatApplication` and remove `HTTPException` below the transport layer.
- **Glossary**: Incoming Message, Reply and Channel are already in `GLOSSARY.md`.

## Testing Decisions

- A good test exercises external behavior at a seam (what comes back, what is persisted, what is sent), not which internal functions were called.
- **Seams** (agreed during the design session):
  1. **Application seam**: `ChatApplication.handle_message` / `handle_decision` against a fake `AgentRuntime` and the real `test_db`. No LLM, no Telegram. Covers: a run that finishes, a run that pauses and saves a Pending Approval, Go Ahead, Changes needed, a repeated press, a message while pending, a message while processing, an unknown sender, and error restore.
  2. **Adapter seam**: the Telegram adapter against a fake Telegram client. Covers callback parsing and mapping to a Decision, ack-before-run ordering, rendering choices as an inline keyboard, and logged-not-raised send failures.
  3. **One end-to-end smoke test** of `POST /webhook` (message and button press) with the fake runtime.
- The `AgentRuntime` itself is covered by the existing format-and-resume tests, adapted to its new interface.
- **Prior art**: `tests/api/unit/test_hitl_approval.py` and `test_hitl_resume.py` (HITL and dispatcher), `test_agent_tools_context.py` (context fixtures), `test_telegram_client.py` (client fakes), and the service tests that use `test_db`. `test_hitl_approval.py` is split along the application and adapter seams.
- Tests that assert on the stored user text with a date prefix, or on the HTTP body being the reply text, are updated in the steps that change those behaviors.

## Out of Scope

- Bringing WhatsApp back; only the layering that makes it possible.
- Changes to the system prompt wording or agent tools.
- Schema changes or backfilling stored messages that carry the date prefix.
- Wiring the Redis client.
- Changing the approval flow itself (the Decision semantics stay the same).
- Writing an ADR for the layering or the date handling.

## Further Notes

- Terms follow `GLOSSARY.md` (Patient, Sender ID, Chat Session, Intake State, Agent Run, Approval Prompt, Pending Approval, Decision, Incoming Message, Reply, Channel).
- Design session decisions were all accepted as recommended, except that date stamping in the stored user message was dropped in favor of the system prompt only.
