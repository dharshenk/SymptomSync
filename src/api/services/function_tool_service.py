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
from pydantic import BaseModel, ConfigDict, Field

from pydantic.types import PositiveInt

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


@function_tool
async def get_available_slots(
    wrapper: RunContextWrapper[ToolContext], appointment_date: date
):
    wrapper.context.appointment_date = appointment_date
    slots = await wrapper.context.appointment_service.get_available_slots(
        doctor_id=wrapper.context.doctor_id, appointment_date=appointment_date
    )

    # Header for the Markdown response
    date_header = appointment_date.strftime("%A, %B %d, %Y")

    if not slots:
        return f"### Status: No Availability\nNo slots are available for **{date_header}**. Please suggest another date to the patient."

    # Build the Markdown Table
    markdown_lines = [
        f"### Available Slots for {date_header}",
        "",
        "| Start Time | End Time |",
        "| :--------- | :------- |",
    ]

    for slot in slots:
        # Converting datetime.time objects to user-friendly strings
        start = slot["slot_start"].strftime("%I:%M %p")
        end = slot["slot_end"].strftime("%I:%M %p")
        markdown_lines.append(f"| {start} | {end} |")

    # Final footer instruction for the LLM
    markdown_lines.append(
        "\n**Instructions:** Present these times to the patient and ask which one they prefer."
    )

    return "\n".join(markdown_lines)


@function_tool
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
    result = await wrapper.context.appointment_service.book_appointment(appointment)
    if result:
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
