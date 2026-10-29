from dataclasses import dataclass
from typing import Annotated
import os

from agents import Agent
from fastapi import Depends, Request

from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.clients.telegram_client import TelegramClient, TelegramConfig
from src.api.services.appointment_service import AppointmentService
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.services.patient_service import PatientService
from src.api.services.pending_approval_service import PendingApprovalService


@dataclass
class ChatServices:
    """Everything a chat flow needs, built once per request."""

    patient_service: PatientService
    chat_history_service: ChatHistoryService
    patient_intake_service: PatientIntakeService
    pending_approval_service: PendingApprovalService
    appointment_service: AppointmentService
    agent: Agent
    telegram_client: TelegramClient


def get_postgres_client(request: Request) -> PostgresSQLClient:
    return request.app.state.postgres_client


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_telegram_client():
    return TelegramClient(TelegramConfig(bot_token=os.getenv("TELEGRAM_BOT_TOKEN")))


def get_chat_services(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
    agent: Annotated[Agent, Depends(get_agent)],
    telegram_client: Annotated[TelegramClient, Depends(get_telegram_client)],
) -> ChatServices:
    return ChatServices(
        patient_service=PatientService(postgres_client),
        chat_history_service=ChatHistoryService(postgres_client),
        patient_intake_service=PatientIntakeService(postgres_client),
        pending_approval_service=PendingApprovalService(postgres_client),
        appointment_service=AppointmentService(postgres_client),
        agent=agent,
        telegram_client=telegram_client,
    )
