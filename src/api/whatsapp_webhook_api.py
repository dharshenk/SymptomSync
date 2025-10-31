from services.agent_service import AgentService

agent = AgentService()


def get_response(user_input: str):
    response = agent.get_response(user_input=user_input)
    return response
