"""Agent tool that saves partial patient intake details."""

import json
from datetime import date, time

from agents import RunContextWrapper, function_tool

from src.api.agent_tools.tool_context import ToolContext, traced_tool
from src.api.models.patient_intake_model import PatientIntakeState, PatientIntakeUpdate
from src.api.models.patient_model import Gender

# Intake steps in the order the v2 prompt collects them. Each step is asked as one
# message, so every field still missing within the first unfinished step is requested
# together.
INTAKE_STEPS = (
    (("name", "name"), ("age", "age"), ("gender", "gender")),
    (("symptoms", "symptoms or reason for the visit"),),
    (
        ("pre_existing_conditions", "pre-existing conditions"),
        ("medications", "current medications"),
    ),
    (("preferred_date", "preferred appointment date"),),
)

# Fields in collection order; all are required before booking.
REQUIRED_FIELDS = (
    "name",
    "age",
    "gender",
    "symptoms",
    "pre_existing_conditions",
    "medications",
    "preferred_date",
    "preferred_start_time",
)


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _join(labels: list[str]) -> str:
    if len(labels) > 1:
        return ", ".join(labels[:-1]) + " and " + labels[-1]
    return labels[0]


def _next_ask(missing: list[str]) -> str:
    for step in INTAKE_STEPS:
        labels = [label for key, label in step if key in missing]
        if labels:
            return f"ask the patient for their {_join(labels)} in a single message"
    if "preferred_start_time" in missing:
        return "call get_available_slots() and ask the patient which slot they prefer"
    return "call book_appointment()"


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
    preferred_start_time: time | None = None,
) -> str:
    """Save newly collected or corrected patient details and return intake progress.

    Pass any number of the details, only those the patient actually provided;
    omitted or null arguments keep their saved values. Record an explicit answer
    of no conditions or medications as "None". preferred_date is the day the
    patient wants the appointment; preferred_start_time is the chosen start time of day, with no timezone.
    """
    fields = {
        "name": name,
        "age": age,
        "gender": gender,
        "symptoms": symptoms,
        "pre_existing_conditions": pre_existing_conditions,
        "medications": medications,
        "preferred_date": preferred_date,
        "preferred_start_time": preferred_start_time,
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

    missing = [key for key in REQUIRED_FIELDS if _is_blank(getattr(state, key))]
    # Saved values are omitted: they are already in the conversation as call
    # arguments, and echoing them would bloat context on every call.
    return json.dumps(
        {"saved": list(updates), "missing": missing, "next": _next_ask(missing)}
    )
