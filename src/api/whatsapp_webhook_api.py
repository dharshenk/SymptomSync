from api.models.IO_model import InputModel
from api.models.patient_model import Patient
from api.services.chat_history_service import ChatHistoryService
from api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from api.models.chat_session_model import ChatMessage, SenderType
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv
from api.services.patient_service import PatientService
from uuid import UUID
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

    sender_type_map = {"patient": "user", "bot": "assistant"}

    messages: list[dict] = []

    if previous_messages:
        messages.extend(
            {
                "role": sender_type_map.get(msg.sender_type.lower()),
                "content": msg.message_content,
            }
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
patient_service = PatientService(postgres_client)
chat_history_service = ChatHistoryService(postgres_client)


async def get_response(user_input: InputModel):
    patient = await patient_service.get_patient_by_patient_id(
        user_input.patient.patient_id
    )
    if not patient:
        patient = await patient_service.create_patient(user_input.patient)

    chat_session = await chat_history_service.get_session(user_input.session_id)
    if not chat_session:
        chat_session = await chat_history_service.create_session(
            user_input.session_id, patient.id
        )

    previous_messages = await chat_history_service.get_session_messages(
        session_id=chat_session.id
    )

    user_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.patient,
        message_content=user_input.input,
        message_sequence=(
            previous_messages[-1].message_sequence + 1 if previous_messages else 1
        ),
    )
    await chat_history_service.add_message(user_message)

    input_list = format_messages_for_runner(
        user_question=user_input.input, previous_messages=previous_messages
    )

    # running the agent
    response = await Runner.run(starting_agent=agent, input=input_list)

    ai_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.bot,
        message_content=response.final_output,
        message_sequence=user_message.message_sequence + 1,
    )

    await chat_history_service.add_message(ai_message)

    return response


if __name__ == "__main__":
    # Example input
    user_input = InputModel(
        input="what's his former club",
        patient=Patient(
            patient_id="8795674356",
            first_name="john",
            last_name="doe",
            phone_number="8795674356",
        ),
        session_id=UUID("6df362ea-10a5-48a3-9daa-38959166362a"),
    )

    # Run the async get_response function
    response = asyncio.run(get_response(user_input))

    print("Assistant response:", response.final_output)
