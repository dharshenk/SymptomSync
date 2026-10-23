# Potential Issues

Known risks that are not fixed yet. Each entry says where it lives, when it triggers, and a possible fix.

## 1. Concurrent first messages can race on intake-state creation

- **Where:** `src/api/whatsapp_webhook_api.py` (get-then-create of `patient_intake_state`); the same pattern is used for patients and chat sessions.
- **Trigger:** two webhook calls for the same brand-new session (for example a Telegram retry or two quick messages) both see no row, and both call `create_intake_state`.
- **Effect:** the second `INSERT` fails on the unique constraint, so that request returns an error.
- **Possible fix:** insert with `ON CONFLICT (chat_session_id) DO NOTHING`, then select the row (a `get_or_create` on the service), and do the same for patients and chat sessions.

## 2. `PostgresSQLClient.transaction()` references an unbound `conn`

- **Where:** `src/api/clients/postgres_sql_client.py`, `transaction()`.
- **Trigger:** `get_connection()` raises (pool exhausted, connection failure) before `conn` is assigned.
- **Effect:** the bare `except` block runs `if conn:`, which raises `UnboundLocalError` and hides the real `DatabaseError`.
- **Possible fix:** drop the outer `except` (`get_connection` already rolls back on error), or bind `conn = None` before the `try`.

## 3. Stale cached intake state when requests for one session overlap

- **Where:** `ToolContext.patient_intake_state` (`src/api/agent_tools/tool_context.py`), read by `get_available_slots` and `book_appointment`.
- **Trigger:** the webhook loads the intake state once per request, so the copy is only as fresh as the start of that request. Handled one after another, requests are always consistent, because each builds a new `ToolContext`. The problem only appears when two requests for the same session are in flight together.
- **Example:**
  1. The user sends "Monday at 10 works" and a second later "actually make it Tuesday".
  2. Requests A and B both load `{preferred_date: Mon}`.
  3. B's LLM call finishes first and saves Tuesday to the DB.
  4. A is still mid-run. Its `book_appointment` reads its cached copy, so it books Monday while the DB says Tuesday.
- **Effect:** an appointment is booked from stale details, and the patient is told something that contradicts what they last said.
- **Possible fixes:**
  - Serialize webhook handling per chat session (an in-process lock or a Redis lock keyed on `session_id`). This is the most complete fix, since the chat history has the same ordering problem.
  - Re-read the state from the DB inside `book_appointment` only, as a cheap guard on the one irreversible action.
  - Compare `updated_at` on the cached state against the DB before booking, and refuse or reload if they differ.
