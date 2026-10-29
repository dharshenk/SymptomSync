# 03: Message path through the layers

**What to build:** A Patient's plain chat message flows through the new layers end to end. `ChatApplication.handle_message` returns a Reply and sends nothing: it resolves the conversation, persists the message, builds the tool context (latest appointment, Intake State created if missing) in the application layer, runs the `AgentRuntime`, persists the outcome, and returns the Reply. The legacy transcript seeding for old sessions stays as an isolated, removable function. The Telegram adapter parses the message into an Incoming Message, runs the use case under the typing indicator, and sends the Reply. A failed send is logged, not raised.

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] `handle_message` returns a Reply, never touches the Telegram client, and imports no FastAPI or SDK types
- [ ] The tool context is built in the application layer
- [ ] The legacy seeding is one clearly marked function
- [ ] The adapter shows the typing indicator while the run is in progress and sends the Reply afterwards
- [ ] A failed Telegram send is logged and does not cause an error response
- [ ] Application-seam tests (fake runtime, real `test_db`) cover a finished run
- [ ] Adapter-seam tests (fake Telegram client) cover message parsing, typing and sending
