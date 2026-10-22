from src.api.services.appointment_service import AppointmentService
from src.api.models.appointment_model import Appointment
from src.api.models.patient_model import Gender
from src.api.services.patient_report_service import generate_patient_report_pdf
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.models.patient_intake_model import PatientIntakeState, PatientIntakeUpdate
from datetime import date, datetime
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
    patient_intake_service: PatientIntakeService
    appointment_date: date = Field(
        default_factory=date.today
    )  # our get_available_slots function in the db only looks for one particular day
    appointment: Appointment | None = None


# Intake steps in the order the v2 prompt collects them; each step is asked as one
# message, so only the fields still missing within the current step are requested.
INTAKE_STEPS = (
    (("name", "name"), ("age", "age"), ("gender", "gender")),
    (("symptoms", "symptoms or reason for the visit"),),
    (
        ("pre_existing_conditions", "pre-existing conditions"),
        ("medications", "current medications"),
    ),
    (("preferred_date", "preferred appointment date"),),
)


# Fields in collection order. A tool is ready once everything up to and including
# its last required field is filled.
REQUIRED_FIELDS = (
    "name",
    "age",
    "gender",
    "symptoms",
    "pre_existing_conditions",
    "medications",
    "preferred_date",
    "preferred_slot",
)


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _missing_upto(state: PatientIntakeState | None, last_field: str) -> list[str]:
    """Fields still unfilled from the first one up to and including last_field."""
    required = REQUIRED_FIELDS[: REQUIRED_FIELDS.index(last_field) + 1]
    return [key for key in required if state is None or _is_blank(getattr(state, key))]


def _not_ready(missing: list[str]) -> str:
    return json.dumps(
        {"status": "Not Ready", "missing": missing, "next": _next_ask(missing)}
    )


def _next_ask(unfilled: list[str]) -> str:
    for step in INTAKE_STEPS:
        labels = [label for key, label in step if key in unfilled]
        if labels:
            return "ask the patient for their " + " and ".join(
                [", ".join(labels[:-1])] * (len(labels) > 1) + labels[-1:]
            )
    return "call get_available_slots()"


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
async def update_patient_details(
    wrapper: RunContextWrapper[ToolContext],
    name: str | None = None,
    age: int | None = None,
    gender: Gender | None = None,
    symptoms: str | None = None,
    pre_existing_conditions: str | None = None,
    medications: str | None = None,
    preferred_date: date | None = None,
    preferred_slot: datetime | None = None,
) -> str:
    """Save newly collected or corrected details and return intake progress.

    Supply only known details; omitted or null arguments preserve saved values.
    Record explicit answers of no conditions or medications as "None".
    preferred_date is the patient's preferred appointment date; collect it
    before preferred_slot. preferred_slot is the chosen appointment date and time.
    """
    fields = {
        "name": name,
        "age": age,
        "gender": gender,
        "symptoms": symptoms,
        "pre_existing_conditions": pre_existing_conditions,
        "medications": medications,
        "preferred_date": preferred_date,
        "preferred_slot": preferred_slot,
    }
    updates = PatientIntakeUpdate(
        **{key: value for key, value in fields.items() if value is not None}
    ).model_dump(exclude_unset=True)
    service = wrapper.context.patient_intake_service
    session_id = wrapper.context.chat_session_id
    state = await service.get_intake_state(session_id)
    if state is None:
        await service.create_intake_state(
            PatientIntakeState(chat_session_id=session_id, **updates)
        )
    elif updates:
        if not await service.update_intake_state(session_id, **updates):
            raise RuntimeError("Patient details could not be saved")

    state = await service.get_intake_state(session_id)
    if state is None:
        raise RuntimeError("Saved patient details could not be retrieved")

    saved = state.model_dump(mode="json", include=set(fields))
    unfilled = [key for key, value in saved.items() if _is_blank(value)]
    if not unfilled:
        message = "call book_appointment()"
    else:
        message = _next_ask(unfilled)
    # Saved values are omitted: they are already in the conversation as call
    # arguments, and echoing them would bloat context on every call.
    return json.dumps(
        {
            "saved": list(updates),
            "missing": unfilled,
            "next": message,
        }
    )


@function_tool
@traced_tool
async def get_available_slots(
    wrapper: RunContextWrapper[ToolContext], appointment_date: date
):
    state = await wrapper.context.patient_intake_service.get_intake_state(
        wrapper.context.chat_session_id
    )
    missing = _missing_upto(state, "preferred_date")
    if missing:
        return _not_ready(missing)
    if state.preferred_date != appointment_date:
        return json.dumps(
            {
                "status": "Not Ready",
                "missing": [],
                "next": "save the patient's new preferred date with update_patient_details() first",
            }
        )

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


async def _book_ready(
    wrapper: RunContextWrapper[ToolContext], _params: dict, _call_id: str
) -> bool:
    """HITL gate: ask the patient for approval only when every detail is collected.

    Returning False does not skip the tool; it runs without an approval prompt, and
    the guard in book_appointment then tells the model what is still missing.
    """
    state = await wrapper.context.patient_intake_service.get_intake_state(
        wrapper.context.chat_session_id
    )
    return not _missing_upto(state, "preferred_slot")


@function_tool()  # after HITL implementation add this to the params: needs_approval=_book_ready
@traced_tool
async def book_appointment(wrapper: RunContextWrapper[ToolContext]):
    patient_intake_state = (
        await wrapper.context.patient_intake_service.get_intake_state(
            wrapper.context.chat_session_id
        )
    )
    missing = _missing_upto(patient_intake_state, "preferred_slot")
    if missing:
        return _not_ready(missing)

    slot_date = patient_intake_state.preferred_slot.date()
    slot_start = patient_intake_state.preferred_slot.time()
    slots = await wrapper.context.appointment_service.get_available_slots(
        doctor_id=wrapper.context.doctor_id, appointment_date=slot_date
    )
    slot = next((s for s in slots or [] if s["slot_start"] == slot_start), None)
    if slot is None:
        return json.dumps(
            {
                "status": "Slot Unavailable",
                "next": "apologize, call get_available_slots() and let the patient choose another slot",
            }
        )

    appointment = Appointment(
        patient_id=wrapper.context.patient_id,  # UUID from PatientData
        doctor_id=wrapper.context.doctor_id,
        chat_session_id=wrapper.context.chat_session_id,
        appointment_date=slot_date,
        start_time=slot_start,
        end_time=slot["slot_end"],
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
