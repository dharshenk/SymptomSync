# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See `AGENTS.md` for repository guidelines (structure, commit style, testing setup); this file covers commands and architecture.

## Commands

Run from the repository root (imports are `src.api...`, so the root must be on the path).

- `uv sync --frozen` — install dependencies
- `docker compose up --build` — API (port 8888), PostgreSQL, Redis, Jaeger (traces at http://localhost:16686)
- `uv run uvicorn main:app --app-dir src --reload` — run locally (needs `.env` and a running Postgres)
- `uv run pytest -c tests/pytest.ini tests` — full suite; many service tests need a real `test_db` Postgres (`POSTGRES_TEST_HOST`/`PORT`) and Redis credentials
- `uv run pytest -c tests/pytest.ini tests/api/services/test_x.py::test_name` — single test
- `uv run pytest -c tests/pytest.ini tests -m integration` — integration-marked tests
- `uv run pre-commit run --all-files` — ruff, black, detect-secrets, codespell, pyupgrade

`asyncio_mode = auto` is set, so async tests need no decorator.

## Architecture

One webhook turns a chat message into an LLM agent run with DB-backed tools.

**Request flow** (`src/api/whatsapp_webhook_api.py`, `POST /webhook`): the endpoint currently accepts a **Telegram** `TelegramUpdate` (the WhatsApp request model and the GET verification route are commented out). It then:
1. Gets or creates a `Patient` keyed by the sender's ID (stored in `patient_ph_no`), and a chat session whose ID is `uuid5(NAMESPACE_DNS, patient_ph_no)`.
2. Loads prior `ChatMessage`s, persists the user message, and builds the message list: the system prompt (a Jinja template read from `SYSTEM_PROMPT_PATH`, rendered with `current_date`) plus history plus the new message.
3. Builds a `ToolContext` (patient, chat session, services, latest appointment, hardcoded doctor ID `1111...`) and calls `Runner.run` from the OpenAI Agents SDK.
4. Persists the bot reply and returns it as the HTTP response. Outbound sends to Telegram/WhatsApp are commented out, so replies are not pushed to the chat.

**Agent flow** read the latest prompt in `src/api/prompts` to understand the workflow of this application

**Agent setup** (`src/main.py`): a single shared `Agent` and `PostgresSQLClient` are created in the FastAPI lifespan and stored on `app.state`; routes reach them via `Depends`. The model is `LLM_MODEL` (native OpenAI) if set, otherwise a `LitellmModel` using `LITE_LLM_MODEL`. Reasoning effort is only set to `none` on the native path.

**Tools** (`src/api/services/function_tool_service.py`): `update_patient_details`, `get_available_slots`, `book_appointment` and `generate_patient_report` are `@function_tool`s. Each receives `RunContextWrapper[ToolContext]`, so services are injected through the context rather than globals. `update_patient_details` writes incrementally into `patient_intake_state` through `PatientIntakeService`, validated by `PatientIntakeUpdate`. The prompt in `src/api/prompts/` drives the intake order and tool usage, so prompt edits change behavior (v2 is the current one; select it via `SYSTEM_PROMPT_PATH`).

**Persistence**: `clients/postgres_sql_client.py` is a thin synchronous psycopg2 wrapper (`execute_query` / `execute_command`) used by the `async` service classes, which build raw SQL with named parameters. There is no ORM or migration tool. The schema is `scripts/database_schema_v1.sql`, with seed data in `scripts/populate_tables_for_testing.sql`; schema changes must be made there and in the service/model code. `get_intake_state` selects only the model's fields so old columns are tolerated.

**Tracing** (`src/api/telemetry.py`): OpenTelemetry with the `@traced(...)` decorator, used on `agent.run` and on every tool (`traced_tool`) with patient/session attributes. Set `OTEL_SDK_DISABLED=true` to turn tracing off.

**Other**: `clients/redis_client.py` is not wired into the app. PDF reports are generated with ReportLab by `patient_report_service.py` and written to `PATIENT_REPORT_OUTPUT_PATH`. WhatsApp client unit tests live in `src/api/clients/tests/`, while the rest of the tests live in `tests/api/`.
