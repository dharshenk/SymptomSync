from typing import Annotated
import os

from agents import Agent
from fastapi import Depends, Request

from src.api.agent_runtime import AgentRuntime
from src.api.chat_application import ChatApplication
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.clients.telegram_client import TelegramClient, TelegramConfig
from src.api.services.appointment_service import AppointmentService
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.services.patient_service import PatientService
from src.api.services.pending_approval_service import PendingApprovalService


def get_postgres_client(request: Request) -> PostgresSQLClient:
    return request.app.state.postgres_client


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_telegram_client():
    return TelegramClient(TelegramConfig(bot_token=os.getenv("TELEGRAM_BOT_TOKEN")))


def get_chat_application(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
    agent: Annotated[Agent, Depends(get_agent)],
) -> ChatApplication:
    return ChatApplication(
        PatientService(postgres_client),
        ChatHistoryService(postgres_client),
        PatientIntakeService(postgres_client),
        PendingApprovalService(postgres_client),
        AppointmentService(postgres_client),
        AgentRuntime(agent),
    )
