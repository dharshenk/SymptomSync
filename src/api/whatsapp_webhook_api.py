from services.agent_service import AgentService

# from models.IO_model import InputModel
# from services.chat_history_service import ChatHistoryService
# from clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig


agent = AgentService()
# database_config = DatabaseConfig()
# postgres_client = PostgresSQLClient()
# chat_history_service = ChatHistoryService()


# def get_response(user_input: InputModel):

#     messages = chat_history_service.get_session_messages(
#         session_id=user_input.session_id
#     )
#     response = agent.get_response()
#     return response
