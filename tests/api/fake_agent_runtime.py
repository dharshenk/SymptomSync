"""A scripted AgentRuntime for use-case tests: no LLM, no SDK."""

from src.api.agent_runtime import RunOutcome


class FakeAgentRuntime:
    """Returns queued outcomes in order and records every call."""

    def __init__(self, *outcomes: RunOutcome):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []

    async def run(self, history, user_text, context):
        self.calls.append(("run", history, user_text, context))
        return self.outcomes.pop(0)

    async def resume(self, state, context, decision):
        self.calls.append(("resume", state, context, decision))
        return self.outcomes.pop(0)
