from api.services.appointment_service import AppointmentService
from api.models.appointment_model import Appointment
from api.models.patient_model import Gender
from api.services.patient_report_service import generate_patient_report_pdf
from datetime import date, time
from uuid import UUID
from agents import function_tool, RunContextWrapper
from pathlib import Path
import os
import logging
from pydantic import BaseModel, ConfigDict

from pydantic.types import PositiveInt

logger = logging.getLogger(__name__)

PATIENT_REPORT_OUTPUT_PATH = os.getenv("PATIENT_REPORT_OUTPUT_PATH")


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    patient_id: UUID
    chat_session_id: UUID
    appointment_service: AppointmentService
    appointment: Appointment | None = None


@function_tool
def book_appointment(
    wrapper: RunContextWrapper[ToolContext],
    doctor_id: UUID,
    appointment_date: date,
    start_time: time,
    end_time: time,
    patient_notes: str | None = None,
):

    appointment = Appointment(
        patient_id=wrapper.context.patient_id,  # UUID from PatientData
        doctor_id=doctor_id,
        chat_session_id=wrapper.context.chat_session_id,
        appointment_date=appointment_date,
        start_time=start_time,
        end_time=end_time,
        patient_notes=patient_notes,
    )

    wrapper.context.appointment = appointment
    if wrapper.context.appointment_service.book_appointment(appointment):
        return f"Appointment has been successfully booked with appointment number: {wrapper.context.appointment.appointment_number}"

    else:
        return "Failed to book appointment"


@function_tool
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

    except Exception as e:
        logger.error(f"Report failed to generate {str(e)}")
        return "Report failed to generate"
