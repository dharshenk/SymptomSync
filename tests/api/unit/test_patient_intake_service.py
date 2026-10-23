"""Service-free tests for intake persistence and partial update behavior."""

from datetime import datetime, time, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.clients.postgres_sql_client import DatabaseError, PostgresSQLClient
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.services.patient_intake_service import PatientIntakeService


@pytest.fixture
def client():
    return Mock(spec=PostgresSQLClient)


@pytest.fixture
def service(client):
    return PatientIntakeService(client)


async def test_create_state(service, client):
    state = PatientIntakeState(chat_session_id=uuid4())
    assert await service.create_intake_state(state) == state
    query, params = client.execute_command.call_args.args
    assert "INSERT INTO patient_intake_state" in query
    assert params["chat_session_id"] == str(state.chat_session_id)
    assert params["status"] == "in_progress"
    assert params["symptoms"] is None
    assert "allergies" not in params
    assert "allergies" not in query


async def test_get_state(service, client):
    state = PatientIntakeState(chat_session_id=uuid4(), age=0)
    client.execute_query.return_value = [state.model_dump()]
    assert await service.get_intake_state(state.chat_session_id) == state
    assert client.execute_query.call_args.kwargs["fetch"] == "one"
    query = client.execute_query.call_args.args[0]
    columns = query.split(" FROM ")[0].removeprefix("SELECT ").split(", ")
    assert set(columns) == set(PatientIntakeState.model_fields)
    assert "allergies" not in columns


async def test_get_missing_state(service, client):
    client.execute_query.return_value = None
    assert await service.get_intake_state(uuid4()) is None


async def test_incremental_updates_preserve_omitted_fields(service, client):
    session_id = uuid4()
    stored = {"name": "Test Patient", "age": 25, "symptoms": None}

    def apply_update(query, params, fetch, commit):
        for field, value in params.items():
            if field != "chat_session_id":
                assert f"{field} = %({field})s" in query
                stored[field] = value
        assert "updated_at = CURRENT_TIMESTAMP" in query
        assert params["chat_session_id"] == str(session_id)
        return [PatientIntakeState(chat_session_id=session_id, **stored).model_dump()]

    client.execute_query.side_effect = apply_update
    state = await service.update_intake_state(session_id, symptoms="Headache")
    assert state.symptoms == "Headache"
    assert state.age == 25
    assert await service.update_intake_state(session_id, age=26)
    assert stored == {"name": "Test Patient", "age": 26, "symptoms": "Headache"}
    state = await service.update_intake_state(session_id, symptoms=None, age=0)
    assert (state.symptoms, state.age) == (None, 0)
    assert stored == {"name": "Test Patient", "age": 0, "symptoms": None}


async def test_update_returns_and_commits_in_one_statement(service, client):
    session_id = uuid4()
    client.execute_query.return_value = [
        PatientIntakeState(chat_session_id=session_id, age=30).model_dump()
    ]
    state = await service.update_intake_state(session_id, age=30)
    assert state.chat_session_id == session_id
    query = client.execute_query.call_args.args[0]
    columns = query.split("RETURNING ")[1].rstrip("; \n").split(", ")
    assert set(columns) == set(PatientIntakeState.model_fields)
    assert client.execute_query.call_args.kwargs == {"fetch": "one", "commit": True}
    client.execute_command.assert_not_called()


async def test_update_serializes_datetime_and_gender(service, client):
    slot = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    client.execute_query.return_value = [
        PatientIntakeState(chat_session_id=uuid4()).model_dump()
    ]
    assert await service.update_intake_state(
        uuid4(),
        gender="female",
        preferred_start_time=time(9, 0),
        status="completed",
        completed_at=slot,
    )
    params = client.execute_query.call_args.args[1]
    assert params["preferred_start_time"] == "09:00:00"
    assert params["gender"] == "female"
    assert params["status"] == "completed"


@pytest.mark.parametrize(
    "fields",
    [
        {"age": -1},
        {"allergies": "None"},
        {"age": 151},
        {"gender": "invalid"},
        {"status": "invalid"},
        {"status": None},
        {"id": str(uuid4())},
        {"created_at": None},
        {"updated_at": None},
        {"name": "x" * 201},
        {"symptoms = NULL; --": "bad"},
    ],
)
async def test_invalid_updates_never_reach_database(service, client, fields):
    with pytest.raises(ValidationError):
        await service.update_intake_state(uuid4(), **fields)
    client.execute_query.assert_not_called()


async def test_empty_update_does_not_write(service, client):
    assert await service.update_intake_state(uuid4()) is None
    client.execute_query.assert_not_called()


async def test_update_missing_state(service, client):
    client.execute_query.return_value = None
    assert await service.update_intake_state(uuid4(), symptoms="Headache") is None


@pytest.mark.parametrize("rowcount, expected", [(0, False), (1, True)])
async def test_delete_state(service, client, rowcount, expected):
    session_id = uuid4()
    client.execute_command.return_value = rowcount
    assert await service.delete_intake_state(session_id) is expected
    query, params = client.execute_command.call_args.args
    assert "DELETE FROM patient_intake_state" in query
    assert params == {"chat_session_id": str(session_id)}


async def test_database_error_propagates(service, client):
    client.execute_query.side_effect = DatabaseError("write failed")
    with pytest.raises(DatabaseError, match="write failed"):
        await service.update_intake_state(uuid4(), age=30)
