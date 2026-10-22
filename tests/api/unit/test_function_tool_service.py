"""Exercise intake tools through the agent SDK without external services."""

import json
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from agents.tool_context import ToolContext as AgentToolContext

from src.api.models.patient_intake_model import PatientIntakeState
from src.api.services.appointment_service import AppointmentService
from src.api.services.function_tool_service import (
    ToolContext,
    _book_ready,
    _missing_upto,
    book_appointment,
    get_available_slots,
    update_patient_details,
)
from src.api.services.patient_intake_service import PatientIntakeService


@pytest.fixture
def intake_tool():
    service = AsyncMock(spec=PatientIntakeService)
    session_id = uuid4()
    stored = {}

    async def get_state(_session_id):
        assert _session_id == session_id
        return stored.get("state")

    async def create_state(state):
        stored["state"] = state
        return state

    async def update_state(_session_id, **fields):
        assert _session_id == session_id
        stored["state"] = PatientIntakeState(
            **{**stored["state"].model_dump(), **fields}
        )
        return True

    service.get_intake_state.side_effect = get_state
    service.create_intake_state.side_effect = create_state
    service.update_intake_state.side_effect = update_state
    wrapper = AgentToolContext(
        tool_name="update_patient_details",
        tool_call_id="test-call",
        tool_arguments="{}",
        context=ToolContext(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            chat_session_id=session_id,
            appointment_service=Mock(spec=AppointmentService),
            patient_intake_service=service,
        ),
    )

    async def call(**fields):
        # The SDK's strict schema represents optional fields with null values.
        arguments = dict.fromkeys(
            update_patient_details.params_json_schema["properties"]
        )
        arguments.update(fields)
        result = await update_patient_details.on_invoke_tool(
            wrapper, json.dumps(arguments)
        )
        return json.loads(result)

    return call, service


def test_intake_tool_schema_excludes_allergies():
    assert "allergies" not in update_patient_details.params_json_schema["properties"]
    assert "allergies" not in update_patient_details.params_json_schema["required"]


async def test_incremental_updates_preserve_saved_details(intake_tool):
    call, service = intake_tool
    first = await call(name="Test Patient", age=0)
    assert first["saved"] == ["name", "age"]
    assert first["missing"] == [
        "gender",
        "symptoms",
        "pre_existing_conditions",
        "medications",
        "preferred_date",
        "preferred_slot",
    ]
    assert "fields" not in first
    assert "allergies" not in first["missing"]
    assert first["next"] == "ask the patient for their gender"
    second = await call(symptoms="Headache")
    assert second["saved"] == ["symptoms"]
    assert second["missing"] == [
        "gender",
        "pre_existing_conditions",
        "medications",
        "preferred_date",
        "preferred_slot",
    ]
    assert second["next"] == "ask the patient for their gender"
    service.create_intake_state.assert_awaited_once()
    service.update_intake_state.assert_awaited_once_with(
        service.create_intake_state.call_args.args[0].chat_session_id,
        symptoms="Headache",
    )
    state = service.create_intake_state.call_args.args[0]
    assert state.name == "Test Patient"
    corrected = await call(age=25)
    assert corrected["saved"] == ["age"]
    assert "age" not in corrected["missing"]
    assert corrected["next"] == "ask the patient for their gender"
    assert "symptoms" not in corrected["missing"]


async def test_result_does_not_echo_saved_values(intake_tool):
    call, _ = intake_tool
    result = await call(name="Test Patient", symptoms="Long symptom description")
    assert "Test Patient" not in json.dumps(result)
    assert "Long symptom description" not in json.dumps(result)


async def test_progresses_to_slots_and_booking(intake_tool):
    call, _ = intake_tool
    result = await call(
        name="Test Patient",
        age=30,
        gender="female",
        symptoms="Headache",
        pre_existing_conditions="None",
        medications="None",
        preferred_date="2026-11-01",
    )
    assert result["missing"] == ["preferred_slot"]
    assert result["next"] == "call get_available_slots()"
    result = await call(preferred_slot="2026-11-01T09:00:00+00:00")
    assert result["saved"] == ["preferred_slot"]
    assert result["missing"] == []
    assert result["next"] == "call book_appointment()"


async def test_slot_alone_does_not_allow_booking(intake_tool):
    call, _ = intake_tool
    result = await call(preferred_slot="2026-11-01T09:00:00+00:00", name="  ")
    assert result["missing"][:2] == ["name", "age"]
    assert result["next"] == "ask the patient for their name, age and gender"


async def test_failed_save_does_not_return_progress(intake_tool):
    call, service = intake_tool
    await call(name="Test Patient")
    service.update_intake_state.side_effect = RuntimeError("write failed")
    # The SDK exposes tool failures as error text, rather than a success payload.
    with pytest.raises(json.JSONDecodeError):
        await call(age=30)


def _state(**fields):
    base = dict(
        chat_session_id=uuid4(),
        name="Test Patient",
        age=30,
        gender="female",
        symptoms="Headache",
        pre_existing_conditions="None",
        medications="None",
        preferred_date=date(2026, 11, 1),
    )
    return PatientIntakeState(**{**base, **fields})


@pytest.fixture
def booking_tools():
    intake = AsyncMock(spec=PatientIntakeService)
    appointments = AsyncMock(spec=AppointmentService)
    appointments.get_available_slots.return_value = [
        {"slot_start": time(9, 0), "slot_end": time(9, 30)}
    ]
    appointments.book_appointment.return_value = True
    wrapper = AgentToolContext(
        tool_name="tool",
        tool_call_id="test-call",
        tool_arguments="{}",
        context=ToolContext(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            chat_session_id=uuid4(),
            appointment_service=appointments,
            patient_intake_service=intake,
        ),
    )
    return wrapper, intake, appointments


def test_missing_upto_stops_at_last_required_field():
    state = _state(name="  ", preferred_date=None)
    assert _missing_upto(state, "gender") == ["name"]
    assert _missing_upto(state, "preferred_slot") == [
        "name",
        "preferred_date",
        "preferred_slot",
    ]
    assert _missing_upto(None, "age") == ["name", "age"]


async def test_slots_not_ready_until_preferred_date_collected(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state(preferred_date=None)
    result = json.loads(
        await get_available_slots.on_invoke_tool(
            wrapper, json.dumps({"appointment_date": "2026-11-01"})
        )
    )
    assert result["status"] == "Not Ready"
    assert result["missing"] == ["preferred_date"]
    appointments.get_available_slots.assert_not_awaited()


async def test_slots_rejects_date_that_differs_from_saved(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state()
    result = json.loads(
        await get_available_slots.on_invoke_tool(
            wrapper, json.dumps({"appointment_date": "2026-11-02"})
        )
    )
    assert result["status"] == "Not Ready"
    appointments.get_available_slots.assert_not_awaited()


async def test_slots_run_once_date_collected(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state()
    result = json.loads(
        await get_available_slots.on_invoke_tool(
            wrapper, json.dumps({"appointment_date": "2026-11-01"})
        )
    )
    assert result["status"] == "Success"
    appointments.get_available_slots.assert_awaited_once()


async def test_book_not_ready_without_slot(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state()
    assert await _book_ready(wrapper, {}, "call") is False
    result = json.loads(await book_appointment.on_invoke_tool(wrapper, "{}"))
    assert result["missing"] == ["preferred_slot"]
    assert result["next"] == "call get_available_slots()"
    appointments.book_appointment.assert_not_awaited()


async def test_book_uses_saved_slot_when_complete(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state(
        preferred_slot=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
    )
    assert await _book_ready(wrapper, {}, "call") is True
    result = await book_appointment.on_invoke_tool(wrapper, "{}")
    assert "successfully booked" in result
    booked = appointments.book_appointment.call_args.args[0]
    assert (booked.appointment_date, booked.start_time, booked.end_time) == (
        date(2026, 11, 1),
        time(9, 0),
        time(9, 30),
    )


async def test_book_rejects_slot_no_longer_available(booking_tools):
    wrapper, intake, appointments = booking_tools
    intake.get_intake_state.return_value = _state(
        preferred_slot=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    )
    result = json.loads(await book_appointment.on_invoke_tool(wrapper, "{}"))
    assert result["status"] == "Slot Unavailable"
    appointments.book_appointment.assert_not_awaited()
