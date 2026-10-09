from src.api.services.appointment_service import AppointmentService
from src.api.models.appointment_model import Appointment
from src.api.models.patient_model import Gender
from src.api.services.patient_report_service import generate_patient_report_pdf
from datetime import date, time
from uuid import UUID
from agents import function_tool, RunContextWrapper
from pathlib import Path
import os
import logging
import json
from pydantic import BaseModel, ConfigDict, Field

from pydantic.types import PositiveInt
from src.api.telemetry import traced, record_error

logger = logging.getLogger(__name__)

PATIENT_REPORT_OUTPUT_PATH = os.getenv("PATIENT_REPORT_OUTPUT_PATH")


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    patient_id: UUID
    doctor_id: UUID
    chat_session_id: UUID
    appointment_service: AppointmentService
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


@function_tool
@traced_tool
async def get_available_slots(
    wrapper: RunContextWrapper[ToolContext], appointment_date: date
):
    wrapper.context.appointment_date = appointment_date
    slots = await wrapper.context.appointment_service.get_available_slots(
        doctor_id=wrapper.context.doctor_id, appointment_date=appointment_date
    )

    date_str = appointment_date.strftime("%A, %B %d, %Y")

    # Handle the empty state cleanly in JSON
    if not slots:
        data = {
            "status": "No Availability",
            "date": date_str,
            "available_start_times": [],
            "instructions": "No slots are available for this date. Politely inform the patient and ask them to suggest another date.",
        }
        return json.dumps(data)

    # Extract only the start times as clean user-friendly strings
    start_times = [slot["slot_start"].strftime("%I:%M %p") for slot in slots]

    # Build a structured data payload
    data = {
        "status": "Success",
        "date": date_str,
        "available_start_times": start_times,
        "instructions": "Present these start times to the patient as choices and ask which one they prefer. Do not mention any other times.",
    }

    return json.dumps(data, indent=2)


@function_tool
@traced_tool
async def book_appointment(
    wrapper: RunContextWrapper[ToolContext],
    start_time: time,
    end_time: time,
    patient_notes: str | None = None,
):
    appointment = Appointment(
        patient_id=wrapper.context.patient_id,  # UUID from PatientData
        doctor_id=wrapper.context.doctor_id,
        chat_session_id=wrapper.context.chat_session_id,
        appointment_date=wrapper.context.appointment_date,
        start_time=start_time,
        end_time=end_time,
        patient_notes=patient_notes,
    )

    wrapper.context.appointment = appointment
    try:
        result = await wrapper.context.appointment_service.book_appointment(appointment)
        if result:
            return f"Appointment has been successfully booked with appointment number: {wrapper.context.appointment.appointment_number}"

    except Exception as e:
        record_error(e)
        return f"Failed to book appointment due to the exception: {e}"


@function_tool
@traced_tool
def generate_patient_report(
    wrapper: RunContextWrapper[ToolContext],
    name: str,
    age: PositiveInt,
    gender: Gender,
    symptoms: str,
    medical_history: str,
    medications: str,
):
    if not wrapper.context.appointment:
        return "An appointment should be booked first before calling to generate patient report"

    path = (
        Path(PATIENT_REPORT_OUTPUT_PATH)
        / f"{wrapper.context.appointment.appointment_number}.pdf"
    )

    try:
        generate_patient_report_pdf(
            name=name,
            age=age,
            gender=gender,
            symptoms=symptoms,
            medical_history=medical_history,
            medications=medications,
            appointment_date=wrapper.context.appointment.appointment_date,
            appointment_time=wrapper.context.appointment.start_time,
            appointment_number=wrapper.context.appointment.appointment_number,
            output_path=str(path),
        )
        return f"Patient report has been successfully generated and saved as {wrapper.context.appointment.appointment_number}.pdf"

    except Exception as e:
        record_error(e)
        logger.error(f"Report failed to generate {str(e)}")
        return "Report failed to generate"
