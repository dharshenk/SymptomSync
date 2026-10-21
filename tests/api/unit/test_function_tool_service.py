"""Exercise intake tools through the agent SDK without external services."""

import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from agents.tool_context import ToolContext as AgentToolContext

from src.api.models.patient_intake_model import PatientIntakeState
from src.api.services.appointment_service import AppointmentService
from src.api.services.function_tool_service import ToolContext, update_patient_details
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
    assert first["fields"]["name"] == "Test Patient"
    assert first["fields"]["age"] == 0
    assert first["fields"]["symptoms"] is None
    assert "allergies" not in first["fields"]
    assert first["message"] == (
        "yet to be collected: gender, symptoms, pre_existing_conditions, "
        "medications, preferred_slot"
    )
    second = await call(symptoms="Headache")
    assert second["fields"]["name"] == "Test Patient"
    assert second["fields"]["age"] == 0
    assert second["fields"]["symptoms"] == "Headache"
    service.create_intake_state.assert_awaited_once()
    service.update_intake_state.assert_awaited_once_with(
        service.create_intake_state.call_args.args[0].chat_session_id,
        symptoms="Headache",
    )
    corrected = await call(age=25)
    assert corrected["fields"]["age"] == 25
    assert corrected["fields"]["symptoms"] == "Headache"


async def test_progresses_to_slots_and_booking(intake_tool):
    call, _ = intake_tool
    result = await call(
        name="Test Patient",
        age=30,
        gender="female",
        symptoms="Headache",
        pre_existing_conditions="None",
        medications="None",
    )
    assert result["fields"]["preferred_slot"] is None
    assert result["message"] == "call get_available_slots()"
    result = await call(preferred_slot="2026-11-01T09:00:00+00:00")
    assert result["fields"]["preferred_slot"] == "2026-11-01T09:00:00Z"
    assert result["message"] == "call book_appointment()"


async def test_slot_alone_does_not_allow_booking(intake_tool):
    call, _ = intake_tool
    result = await call(preferred_slot="2026-11-01T09:00:00+00:00", name="  ")
    assert result["message"].startswith("yet to be collected: name, age")


async def test_failed_save_does_not_return_progress(intake_tool):
    call, service = intake_tool
    await call(name="Test Patient")
    service.update_intake_state.side_effect = RuntimeError("write failed")
    # The SDK exposes tool failures as error text, rather than a success payload.
    with pytest.raises(json.JSONDecodeError):
        await call(age=30)
