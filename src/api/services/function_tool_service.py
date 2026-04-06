from api.services.appointment_service import AppointmentService
from api.models.appointment_model import Appointment
from datetime import date, time
from uuid import UUID
from agents import function_tool, RunContextWrapper

from pydantic import BaseModel


class ToolContext(BaseModel):
    patient_id: UUID
    chat_session_id: UUID
    appointment_service: AppointmentService


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
    return wrapper.context.appointment_service.book_appointment(appointment)
