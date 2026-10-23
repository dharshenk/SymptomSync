"""Agent tool that lists the doctor's open appointment start times for a date."""

import json
from datetime import time

from agents import RunContextWrapper, function_tool

from src.api.agent_tools.tool_context import ToolContext, traced_tool
from src.api.agent_tools.update_patient_details import INTAKE_STEPS, _is_blank, _join


def _format_start_time(value: time) -> str:
    """Naive 12-hour label: 9 am, 9:30 am, 12 pm, 4:15 pm."""
    hour = value.hour % 12 or 12
    suffix = "am" if value.hour < 12 else "pm"
    if value.minute:
        return f"{hour}:{value.minute:02d} {suffix}"
    return f"{hour} {suffix}"


@function_tool
@traced_tool
async def get_available_slots(wrapper: RunContextWrapper[ToolContext]) -> str:
    """Return the available appointment start times on the patient's saved preferred date.

    Takes no arguments: the date is read from the saved intake details. Present the
    returned start times to the patient as choices; times are plain clock times with
    no timezone.
    """
    patient_intake_state = wrapper.context.patient_intake_state
    missing = [
        label
        for step in INTAKE_STEPS
        for key, label in step
        if _is_blank(getattr(patient_intake_state, key))
    ]
    if missing:
        return json.dumps(
            {
                "status": "Not Ready",
                "missing": missing,
                "next": f"collect the necessary fields: {_join(missing)}",
            }
        )

    preferred_date = patient_intake_state.preferred_date
    slots = await wrapper.context.appointment_service.get_available_slots(
        doctor_id=wrapper.context.doctor_id, preferred_date=preferred_date
    )

    date_str = preferred_date.strftime("%A, %B %d, %Y")

    if not slots:
        return json.dumps(
            {
                "status": "No Availability",
                "date": date_str,
                "available_start_times": [],
                "instructions": "No slots are available for this date. Politely inform the patient and ask them to suggest another date.",
            }
        )

    return json.dumps(
        {
            "status": "Success",
            "date": date_str,
            "available_start_times": [
                _format_start_time(slot["slot_start"]) for slot in slots
            ],
            "instructions": "Present these start times to the patient as choices and ask which one they prefer. Do not mention any other times.",
        }
    )
