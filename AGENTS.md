# Repository Guidelines

## Project Structure & Module Organization

SymptomSync is a FastAPI patient intake and appointment booking backend for WhatsApp and Telegram. `src/main.py` initializes the application. Within `src/api/`, keep external integrations in `clients/`, business logic in `services/`, Pydantic schemas in `models/`, and agent instructions in `prompts/`. Webhook, health, and telemetry modules live directly under `src/api/`.

Tests primarily mirror application modules under `tests/api/`; additional WhatsApp unit tests exist in `src/api/clients/tests/`. SQL schema and seed scripts live in `scripts/`. Architecture documents and demo assets live in `docs/`.

## Build, Test, and Development Commands

Run commands from the repository root:

- `uv sync --frozen`: install locked dependencies, including development tools.
- `docker compose up --build`: build and start the API, PostgreSQL, and Redis; the API is exposed on port 8888.
- `uv run uvicorn main:app --app-dir src --reload`: run the API locally with configured environment variables and backing services.
- `uv build`: build the Python distribution.
- `uv run pytest -c tests/pytest.ini tests`: run the primary test suite with its explicit configuration.
- `uv run pytest -c tests/pytest.ini tests -m integration`: select marked integration tests.
- `uv run pre-commit install`: install Git hooks; use `uv run pre-commit run --all-files` before submitting changes.

## Coding Style & Naming Conventions

Use Python 3.10-compatible syntax, four-space indentation, and type annotations consistent with surrounding code. Use `snake_case` for modules and functions, `PascalCase` for classes, and uppercase names for constants. Follow existing names such as `appointment_service.py` and `AppointmentService`. Black formats Python; Ruff checks lint rules. Hooks also check secrets, spelling, whitespace, and Python modernization.

## Testing Guidelines

Use pytest and pytest-asyncio; name files `test_*.py` and functions `test_*`. Mock external dependencies in unit tests and mark integration tests with `@pytest.mark.integration`. Service fixtures create and drop tables: configure a dedicated `test_db` using `POSTGRES_TEST_HOST` and `POSTGRES_TEST_PORT`. Redis tests also require configured credentials. Marker exclusion alone does not guarantee service-free execution. Measure coverage with `--cov=src/api --cov-report=term-missing`; no coverage threshold is configured.

## Commit & Pull Request Guidelines

Prefer the history's `feat:`, `fix:`, and `refactor:` prefixes with concise, actionable subjects. Keep changes focused. PR descriptions should explain behavior changes, link relevant issues, and report checks run and required configuration or schema changes. Include screenshots or demos for visible conversation-flow changes.

## Security & Configuration

Use `.env.sample` as the configuration reference and keep local secrets in ignored `.env` files. Never commit tokens, credentials, patient data, or generated patient reports. Update `uv.lock` alongside dependency changes.
