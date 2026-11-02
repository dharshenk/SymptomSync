# 01: Neutral vocabulary and conversation resolution

**What to build:** Add the channel-neutral vocabulary the later tickets build on, and make both existing flows share one way of resolving a Sender ID into a Patient and Chat Session. Patient-facing behavior does not change. The vocabulary is: Incoming Message, Incoming Decision, a `Decision` enum (Go Ahead, Changes needed), and a Reply with optional choices (label plus Decision). The doctor ID is read from configuration instead of being hardcoded.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Incoming Message, Incoming Decision, `Decision` and Reply (with choices) exist and use the terms in `GLOSSARY.md`
- [ ] One shared get-or-create `resolve_conversation` is used by both the message and the approval flow
- [ ] A Decision from an unknown sender creates a Patient instead of returning a 404, and ends with "nothing waiting for your approval"
- [ ] The doctor ID comes from configuration
- [ ] The existing test suite is green, with tests added for `resolve_conversation`
