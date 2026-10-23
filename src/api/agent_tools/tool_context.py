"""Shared context and tracing helper for agent tools."""

from datetime import date
from uuid import UUID

from agents import RunContextWrapper
from pydantic import BaseModel, ConfigDict, Field

from src.api.models.appointment_model import Appointment
from src.api.services.appointment_service import AppointmentService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.telemetry import traced


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    patient_id: UUID
    doctor_id: UUID
    chat_session_id: UUID
    appointment_service: AppointmentService
    patient_intake_service: PatientIntakeService
    appointment_date: date = Field(
        default_factory=date.today
    )  # our get_available_slots function in the db only looks for one particular day
    appointment: Appointment | None = None


def _tool_attrs(wrapper: RunContextWrapper[ToolContext], *_, **__) -> dict:
    return {
        "patient.id": str(wrapper.context.patient_id),
        "doctor.id": str(wrapper.context.doctor_id),
        "chat_session.id": str(wrapper.context.chat_session_id),
    }


def traced_tool(func):
    return traced(f"agent.tool.{func.__name__}", attrs=_tool_attrs)(func)
