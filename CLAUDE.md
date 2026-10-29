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
- `uv run alembic upgrade head` / `downgrade -1` / `revision -m "msg"` — DB migrations (see Persistence)
- `uv run pre-commit run --all-files` — ruff, black, detect-secrets, codespell, pyupgrade

`asyncio_mode = auto` is set, so async tests need no decorator.

## Architecture

One webhook turns a chat message into an LLM agent run with DB-backed tools.

**Request flow** (`src/api/whatsapp_webhook_api.py`, `POST /webhook`; the file keeps its legacy name and now holds only the route, with the logic in `chat_flow.py` (handlers, `finalize_run`), `agent_runtime.py` (prompt, `run_agent`, `build_tool_context`), `telegram_delivery.py` (replies, buttons, typing indicator) and `dependencies.py` (`ChatServices` bundle)): `telegram_webhook` is the single route and accepts a **Telegram** `TelegramWebhookUpdate` (the WhatsApp request model and the GET verification route are commented out). It dispatches on the payload: a `callback_query` (button press) goes to `handle_approval`, a `message` to `handle_message`, anything else gets a 422. `handle_message` then:
1. Gets or creates a `Patient` keyed by the sender's ID (stored in `patient_ph_no`), and a chat session whose ID is `uuid5(NAMESPACE_DNS, patient_ph_no)`.
2. Loads prior `ChatMessage`s, persists the user message, and builds the message list: the system prompt (a Jinja template read from `SYSTEM_PROMPT_PATH`, rendered with `current_date`) plus history plus the new message.
3. Loads the session's `patient_intake_state` (creating an empty row if none exists) and builds a `ToolContext` (patient, chat session, services, intake state, latest appointment, hardcoded doctor ID `1111...`) and calls `Runner.run` from the OpenAI Agents SDK.
4. Hands the result to `finalize_run`. A finished run persists the bot reply and agent items and returns the reply as the HTTP response. Outbound sends to Telegram/WhatsApp are commented out, so replies are not pushed to the chat.

**Approval (HITL)**: `book_appointment` is `@function_tool(needs_approval=...)`; the callable returns True only when the intake (including `preferred_start_time`) is fully filled. When the run is interrupted, `finalize_run` saves `result.to_state().to_string(context_serializer=lambda _: {})` in `pending_approvals` (one row per chat session, via `PendingApprovalService`) and returns a booking summary with Telegram inline buttons (`approve` / `changes_needed`). While a row exists, `handle_message` only re-sends that prompt and does not run the agent. `handle_approval` (a `callback_query` on `POST /webhook`) rebuilds a fresh `ToolContext` with `build_tool_context`, restores the state with `RunState.from_string(..., context_override=RunContextWrapper(ctx))`, then `approve()`s, or `reject()`s with a message telling the LLM to ask what to change, and resumes via `run_agent`. When resuming, do not pass `context=` to `Runner.run`: it replaces the state's context and drops the approval decisions. The context is not stored with the state.

**Agent flow** read the latest prompt in `src/api/prompts` to understand the workflow of this application

**Agent setup** (`src/main.py`): a single shared `Agent` and `PostgresSQLClient` are created in the FastAPI lifespan and stored on `app.state`; routes reach them via `Depends`. The model is `LLM_MODEL` (native OpenAI) if set, otherwise a `LitellmModel` using `LITE_LLM_MODEL`. Reasoning effort is only set to `none` on the native path.

**Tools** (`src/api/services/function_tool_service.py`): `update_patient_details`, `get_available_slots`, `book_appointment` and `generate_patient_report` are `@function_tool`s. Each receives `RunContextWrapper[ToolContext]`, so services are injected through the context rather than globals. `update_patient_details` writes incrementally into `patient_intake_state` through `PatientIntakeService`, validated by `PatientIntakeUpdate`. The tools read intake state from `ToolContext.patient_intake_state` rather than querying; `update_patient_details` replaces it with the row returned by `update_intake_state` (`UPDATE ... RETURNING`, which needs `execute_query(..., commit=True)`). The prompt in `src/api/prompts/` drives the intake order and tool usage, so prompt edits change behavior (v2 is the current one; select it via `SYSTEM_PROMPT_PATH`).

**Persistence**: `clients/postgres_sql_client.py` is a thin synchronous psycopg2 wrapper (`execute_query` / `execute_command`) used by the `async` service classes, which build raw SQL with named parameters. There is no ORM. Schema changes are Alembic migrations in `migrations/versions/` written as raw SQL via `op.execute` (no autogenerate, no SQLAlchemy models); always write a working `downgrade()` and update the service/model code to match. `0001` is the baseline: it executes the frozen snapshot `migrations/sql/0001_baseline.sql` (never edit it; the old `scripts/database_schema_v1.sql` no longer exists). Use `IF [NOT] EXISTS` in migrations where a DB may have drifted. `migrations/env.py` builds the URL from the `POSTGRES_*` vars (set `POSTGRES_MIGRATION_HOST=localhost` when running from the host against the compose DB; set `NEON_DB_URL` to a full connection string to migrate a remote DB instead, it takes precedence). For a DB created before migrations existed, run `alembic stamp 0001` once. Seed data stays in `scripts/populate_tables_for_testing.sql`. `get_intake_state` selects only the model's fields so old columns are tolerated.

**Tracing** (`src/api/telemetry.py`): OpenTelemetry with the `@traced(...)` decorator, used on `agent.run` and on every tool (`traced_tool`) with patient/session attributes. Set `OTEL_SDK_DISABLED=true` to turn tracing off.

**Other**: `clients/redis_client.py` is not wired into the app. PDF reports are generated with ReportLab by `patient_report_service.py` and written to `PATIENT_REPORT_OUTPUT_PATH`. WhatsApp client unit tests live in `src/api/clients/tests/`, while the rest of the tests live in `tests/api/`.
