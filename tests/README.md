# Testing Plan & Running Test Cases

This document describes the testing strategy for the SymptomSync project and
provides clear instructions for running all test cases.

---

## Test Types & Structure

The project uses **pytest** for all testing. Tests are organized as follows:

- **Unit Tests**: Validate individual functions and classes in isolation using
  mocks (see `test_redis_client.py`).
- **Integration Tests**: Test the interaction with real services (e.g., Redis)
  using actual connections (see `test_redis_client_integration.py`).

## Test Environment Setup

1. **Install Dependencies**

   Ensure you have a Python virtual environment activated and all dependencies
   installed:

   ```bash
   pip install -r requirements-dev.txt
   pip install -r src/api/requirements.txt
   ```

2. **Environment Variables**

   Integration tests require a running Redis instance and the following
   environment variables (see `.env.sample`):

   - `REDIS_HOST`
   - `REDIS_PORT`
   - `REDIS_DB`
   - `REDIS_PASSWORD`
   - `REDIS_USERNAME` (optional)

   You can copy `.env.sample` to `.env` and fill in your values.

3. **Start Services (Docker Compose)**

   To spin up Redis and Postgres locally:

   ```bash
   docker-compose up -d
   ```

---

## Running Tests

All tests are run using **pytest** from the `src/` directory:

```bash
cd src
pytest
```

### Run Only Unit Tests

To run only unit tests (excluding integration):

```bash
pytest -m 'not integration'
```

### Run Only Integration Tests

To run only integration tests (require real Redis):

```bash
pytest -m integration
```

### Run With Coverage

To check code coverage:

```bash
pytest --cov=api/clients/ --cov-report=term-missing
```

---

## Markers & Configuration

- **Markers**: `integration` and `e2e` markers are defined in `pytest.ini`.
- **Fixtures**: Integration fixtures auto-load environment variables and manage
  Redis state for test isolation.

---

## Best Practices

- **Unit tests** should not require any external services.
- **Integration tests** should clean up after themselves (DB flushes are handled
  by fixtures).
- Use `.env` for secrets, never commit real credentials.
- Use `pre-commit` to lint and check code before pushing.

---

## Troubleshooting

- If integration tests fail, ensure Redis is running and credentials are
  correct.
- For Docker issues, try `docker-compose down -v` and then `docker-compose up
  -d`.
- For more verbose output, use `pytest -v`.

---

For more details, see the [project documentation](../docs/).
