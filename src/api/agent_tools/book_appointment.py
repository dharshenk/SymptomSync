"""Agent tool that books the appointment from the saved intake details."""

import json
from datetime import date, datetime, timedelta

from agents import RunContextWrapper, function_tool

from src.api.agent_tools.tool_context import ToolContext, traced_tool
from src.api.agent_tools.update_patient_details import INTAKE_STEPS, _is_blank, _join
from src.api.models.appointment_model import Appointment
from src.api.telemetry import record_error

APPOINTMENT_MINUTES = 30

# Every intake field up to and including the chosen start time.
BOOKING_STEPS = INTAKE_STEPS + (
    (("preferred_start_time", "preferred appointment start time"),),
)


@function_tool
@traced_tool
async def book_appointment(wrapper: RunContextWrapper[ToolContext]) -> str:
    """Book the appointment using the saved intake details.

    Takes no arguments: the patient, date and start time are read from the saved
    intake details. Only call this once the patient has chosen a start time from
    the options returned by get_available_slots.
    """
    patient_intake_state = (
        await wrapper.context.patient_intake_service.get_intake_state(
            wrapper.context.chat_session_id
        )
    )
    missing = [
        label
        for step in BOOKING_STEPS
        for key, label in step
        if patient_intake_state is None or _is_blank(getattr(patient_intake_state, key))
    ]
    if missing:
        return json.dumps(
            {
                "status": "Not Ready",
                "missing": missing,
                "next": f"collect the necessary fields: {_join(missing)}",
            }
        )

    start_time = patient_intake_state.preferred_start_time
    end_time = (
        datetime.combine(date.min, start_time) + timedelta(minutes=APPOINTMENT_MINUTES)
    ).time()
    appointment = Appointment(
        patient_id=wrapper.context.patient_id,
        doctor_id=wrapper.context.doctor_id,
        chat_session_id=wrapper.context.chat_session_id,
        appointment_date=patient_intake_state.preferred_date,
        start_time=start_time,
        end_time=end_time,
    )

    try:
        booked = await wrapper.context.appointment_service.book_appointment(appointment)
    except Exception as e:
        record_error(e)
        return json.dumps({"status": "Failed", "error": str(e)})

    if not booked:
        return json.dumps(
            {
                "status": "Failed",
                "error": "The appointment could not be booked. Ask the patient to choose another start time.",
            }
        )

    wrapper.context.appointment = appointment
    return json.dumps(
        {
            "status": "Success",
            "appointment_number": appointment.appointment_number,
            "date": appointment.appointment_date.strftime("%A, %B %d, %Y"),
            "start_time": appointment.start_time.strftime("%I:%M %p"),
        }
    )
