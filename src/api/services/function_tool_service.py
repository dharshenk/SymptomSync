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
from opentelemetry import trace

logger = logging.getLogger(__name__)

PATIENT_REPORT_OUTPUT_PATH = os.getenv("PATIENT_REPORT_OUTPUT_PATH")
tracer = trace.get_tracer("symptom.sync.tracer")


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


def _serialize_tool_data(data):
    return json.dumps(data, default=str)


def _set_tool_input_attributes(
    span,
    tool_name: str,
    wrapper: RunContextWrapper[ToolContext],
    inputs: dict,
):
    span.set_attribute("agent.tool.name", tool_name)
    span.set_attribute("agent.tool.input", _serialize_tool_data(inputs))
    span.set_attribute("patient.id", str(wrapper.context.patient_id))
    span.set_attribute("doctor.id", str(wrapper.context.doctor_id))
    span.set_attribute("chat_session.id", str(wrapper.context.chat_session_id))


def _set_tool_output_attributes(span, output):
    output_text = str(output or "")
    span.set_attribute("agent.tool.output", output_text)
    span.set_attribute("agent.tool.output_length", len(output_text))


@function_tool
async def get_available_slots(
    wrapper: RunContextWrapper[ToolContext], appointment_date: date
):
    with tracer.start_as_current_span("agent.tool.get_available_slots") as span:
        _set_tool_input_attributes(
            span,
            "get_available_slots",
            wrapper,
            {"appointment_date": appointment_date},
        )

        wrapper.context.appointment_date = appointment_date
        slots = await wrapper.context.appointment_service.get_available_slots(
            doctor_id=wrapper.context.doctor_id, appointment_date=appointment_date
        )
        span.set_attribute("agent.tool.available_slots_count", len(slots))

        # Header for the Markdown response
        date_header = appointment_date.strftime("%A, %B %d, %Y")

        if not slots:
            output = f"### Status: No Availability\nNo slots are available for **{date_header}**. Please suggest another date to the patient."
            _set_tool_output_attributes(span, output)
            return output

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

        output = "\n".join(markdown_lines)
        _set_tool_output_attributes(span, output)
        return output


@function_tool
async def book_appointment(
    wrapper: RunContextWrapper[ToolContext],
    start_time: time,
    end_time: time,
    patient_notes: str | None = None,
):
    with tracer.start_as_current_span("agent.tool.book_appointment") as span:
        _set_tool_input_attributes(
            span,
            "book_appointment",
            wrapper,
            {
                "start_time": start_time,
                "end_time": end_time,
                "patient_notes": patient_notes,
                "appointment_date": wrapper.context.appointment_date,
            },
        )

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
            result = await wrapper.context.appointment_service.book_appointment(
                appointment
            )
            span.set_attribute("agent.tool.booking_succeeded", bool(result))
            if result:
                output = f"Appointment has been successfully booked with appointment number: {wrapper.context.appointment.appointment_number}"
                _set_tool_output_attributes(span, output)
                return output

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("agent.tool.error", str(e))
            output = f"Failed to book appointment due to the exception: {e}"
            _set_tool_output_attributes(span, output)
            return output

        _set_tool_output_attributes(span, None)


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
    with tracer.start_as_current_span("agent.tool.generate_patient_report") as span:
        _set_tool_input_attributes(
            span,
            "generate_patient_report",
            wrapper,
            {
                "name": name,
                "age": age,
                "gender": gender,
                "symptoms": symptoms,
                "medical_history": medical_history,
                "medications": medications,
            },
        )

        if not wrapper.context.appointment:
            output = "An appointment should be booked first before calling to generate patient report"
            _set_tool_output_attributes(span, output)
            return output

        path = (
            Path(PATIENT_REPORT_OUTPUT_PATH)
            / f"{wrapper.context.appointment.appointment_number}.pdf"
        )
        span.set_attribute("agent.tool.report_output_path", str(path))

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
            output = f"Patient report has been successfully generated and saved as {wrapper.context.appointment.appointment_number}.pdf"
            _set_tool_output_attributes(span, output)
            return output

        except Exception as e:
            span.record_exception(e)
            span.set_attribute("agent.tool.error", str(e))
            logger.error(f"Report failed to generate {str(e)}")
            output = "Report failed to generate"
            _set_tool_output_attributes(span, output)
            return output
