# 02: Agent runtime boundary and date in the system prompt

**What to build:** Put the OpenAI Agents SDK behind an `AgentRuntime` so the rest of the flow never sees SDK types. The runtime renders the system prompt, assembles the input, runs or resumes from a stored state string, and returns either `Finished` (reply text and items) or `NeedsApproval` (state). It holds no Pending Approval state. At the same time, move the date out of the user message: it appears only in the system prompt, at day granularity (e.g. "Thursday, October 29, 2026"), and new user messages are stored as the raw text. Existing stored rows are left alone, with no backfill.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `AgentRuntime` returns `Finished` or `NeedsApproval`, and no SDK type crosses its boundary
- [ ] Resuming from a stored state does not pass a context to the run, so approval decisions are kept
- [ ] The system prompt contains the date and nothing time-of-day
- [ ] New user messages are persisted without a `[Current date: ...]` prefix
- [ ] Tests that asserted the stamped text are updated, and the suite is green
- [ ] A fake `AgentRuntime` is available for use-case tests
