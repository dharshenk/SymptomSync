"""A scripted AgentRuntime for use-case tests: no LLM, no SDK."""

from src.api.agent_runtime import RunOutcome


class FakeAgentRuntime:
    """Returns queued outcomes in order and records every call.

    A queued exception instance is raised instead of returned.
    """

    def __init__(self, *outcomes: RunOutcome):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []

    async def run(self, history, user_text, context):
        self.calls.append(("run", history, user_text, context))
        return self._next()

    async def resume(self, state, context, decision):
        self.calls.append(("resume", state, context, decision))
        return self._next()

    def _next(self):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
