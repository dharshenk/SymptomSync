# 05: Remove the old structure and finish the transport

**What to build:** Finish the cleanup so the layering is real. The transport layer builds an injected `ChatApplication` holding only the DB services and an `AgentRuntime`, replacing the `ChatServices` bundle. `HTTPException` appears only in the transport layer (the 422 for unknown payloads stays). `POST /webhook` returns a small acknowledgement instead of the reply text. The old flow and delivery modules are deleted, and the existing HITL tests are split along the application and adapter seams. One end-to-end `POST /webhook` smoke test (a message and a button press, with the fake runtime) stays.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] `ChatServices` is removed, and `ChatApplication` receives no Telegram client and no agent bundle
- [ ] No `HTTPException` is raised below the transport layer
- [ ] An unknown payload still returns 422
- [ ] The webhook returns a small acknowledgement, and tests assert replies on the use-case result
- [ ] The old flow and delivery modules are deleted, with no remaining references
- [ ] The existing HITL tests are split along the application and adapter seams
- [ ] An end-to-end `POST /webhook` smoke test passes for a message and a button press
- [ ] The full test suite is green
