from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel


class AgentService:
    def __init__(self) -> None:
        self.name = "Assistant"
        self.model = LitellmModel(model="gemini/gemini-2.5-flash")
        self.instructions = "You're a helpful assistant"
        self._agent = self._initialize_agent()

    def _initialize_agent(self):
        return Agent(name=self.name, model=self.model, instructions=self.instructions)

    def get_response(self, user_input: str):
        response = Runner.run_sync(starting_agent=self._agent, input=user_input)
        return response
