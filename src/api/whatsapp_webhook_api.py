from api.models.IO_model import InputModel
from api.services.chat_history_service import ChatHistoryService
from api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from api.models.chat_session_model import ChatMessage
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv
import asyncio
import os

load_dotenv()


def format_messages_for_runner(
    user_question: str, previous_messages: list["ChatMessage"] | None = None
) -> list[dict]:
    """
    Build a chat message list for OpenAI's Runner.
    Always appends the current user question, and prepends previous messages if given.

    Args:
        user_question (str): The new user input.
        previous_messages (list[ChatMessage] | None): Optional previous conversation.

    Returns:
        list[dict]: Messages formatted as [{"role": "user", "content": "..."}, ...].
    """
    messages: list[dict] = []

    if previous_messages:
        messages.extend(
            {"role": msg.sender_type.lower(), "content": msg.message_content}
            for msg in previous_messages
        )

    messages.append({"role": "user", "content": user_question})

    return messages


agent = Agent(
    name="assistant",
    model=LitellmModel(model="gemini/gemini-2.5-flash"),
    instructions="You're a helpful assistant. Who keeps it concise.",
)

database_config = DatabaseConfig(
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT"),
    database=os.getenv("POSTGRES_DATABASE"),
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
postgres_client = PostgresSQLClient(database_config)
chat_history_service = ChatHistoryService(postgres_client)


async def get_response(user_input: InputModel):
    messages = await chat_history_service.get_session_messages(
        session_id=user_input.session_id
    )
    input_list = format_messages_for_runner(
        user_question=user_input.input, previous_messages=messages
    )
    response = await Runner.run(starting_agent=agent, input=input_list)

    return response


if __name__ == "__main__":
    # Example input
    user_input = InputModel(input="who is messi")

    # Run the async get_response function
    response = asyncio.run(get_response(user_input))

    print("Assistant response:", response.final_output)
