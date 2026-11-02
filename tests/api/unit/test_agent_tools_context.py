"""Agent tools read intake state from ToolContext instead of querying the database."""

import json
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4


from src.api.agent_tools import ToolContext
from src.api.agent_tools.book_appointment import book_appointment
from src.api.agent_tools.get_available_slots import get_available_slots
from src.api.agent_tools.update_patient_details import update_patient_details
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.services.appointment_service import AppointmentService
from src.api.services.patient_intake_service import PatientIntakeService

SESSION_ID = uuid4()
FULL = dict(
    name="Test Patient",
    age=30,
    gender="female",
    symptoms="Headache",
    pre_existing_conditions="None",
    medications="None",
    preferred_date=date(2026, 11, 2),
    preferred_start_time=time(9, 0),
)


def make_context(**state_fields):
    return ToolContext(
        patient_id=uuid4(),
        doctor_id=uuid4(),
        chat_session_id=SESSION_ID,
        appointment_service=Mock(spec=AppointmentService),
        patient_intake_service=Mock(spec=PatientIntakeService),
        patient_intake_state=PatientIntakeState(
            chat_session_id=SESSION_ID, **state_fields
        ),
    )


def invoke(tool, context, **args):
    """Run a @function_tool through the SDK entry point with our context."""
    wrapper = SimpleNamespace(context=context, tool_name=tool.name)
    return tool.on_invoke_tool(wrapper, json.dumps(args))


async def test_update_refreshes_context_from_returning():
    context = make_context(name="Old")
    returned = context.patient_intake_state.model_copy(
        update={"name": "New", "age": 40}
    )
    context.patient_intake_service.update_intake_state = AsyncMock(
        return_value=returned
    )

    result = json.loads(
        await invoke(update_patient_details, context, name="New", age=40)
    )

    assert context.patient_intake_state is returned
    assert result["saved"] == ["name", "age"]
    context.patient_intake_service.update_intake_state.assert_awaited_once_with(
        SESSION_ID, name="New", age=40
    )
    context.patient_intake_service.get_intake_state.assert_not_called()
    context.patient_intake_service.create_intake_state.assert_not_called()


async def test_update_without_fields_skips_database():
    context = make_context(name="Kept")
    context.patient_intake_service.update_intake_state = AsyncMock()

    result = json.loads(await invoke(update_patient_details, context))

    assert result["saved"] == []
    assert "name" not in result["missing"]
    context.patient_intake_service.update_intake_state.assert_not_called()


async def test_update_failure_leaves_context_unchanged():
    context = make_context(name="Old")
    before = context.patient_intake_state
    context.patient_intake_service.update_intake_state = AsyncMock(return_value=None)

    result = await invoke(update_patient_details, context, name="New")

    assert "could not be saved" in result  # SDK turns the exception into tool output
    assert context.patient_intake_state is before


async def test_get_available_slots_reads_context_state():
    context = make_context(**FULL)
    context.appointment_service.get_available_slots = AsyncMock(
        return_value=[{"slot_start": time(9, 0)}]
    )

    result = json.loads(await invoke(get_available_slots, context))

    assert result["status"] == "Success"
    assert result["available_start_times"] == ["9 am"]
    context.appointment_service.get_available_slots.assert_awaited_once_with(
        doctor_id=context.doctor_id, preferred_date=date(2026, 11, 2)
    )
    context.patient_intake_service.get_intake_state.assert_not_called()


async def test_get_available_slots_not_ready_when_context_state_incomplete():
    context = make_context(name="Test Patient")

    result = json.loads(await invoke(get_available_slots, context))

    assert result["status"] == "Not Ready"
    assert "age" in result["missing"]
    context.patient_intake_service.get_intake_state.assert_not_called()


async def test_book_appointment_reads_context_state():
    context = make_context(**FULL)
    context.appointment_service.book_appointment = AsyncMock(return_value=True)

    result = json.loads(await invoke(book_appointment, context))

    assert result["status"] == "Success"
    booked = context.appointment_service.book_appointment.call_args.args[0]
    assert (booked.appointment_date, booked.start_time) == (
        date(2026, 11, 2),
        time(9, 0),
    )
    assert context.appointment is booked
    context.patient_intake_service.get_intake_state.assert_not_called()


async def test_book_appointment_not_ready_without_start_time():
    context = make_context(**{**FULL, "preferred_start_time": None})

    result = json.loads(await invoke(book_appointment, context))

    assert result["status"] == "Not Ready"
    assert result["missing"] == ["preferred appointment start time"]
    context.appointment_service.book_appointment.assert_not_called()
