# ── Stage 1: Build ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv for fast, reproducible dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first (maximises Docker layer cache hits)
COPY pyproject.toml uv.lock ./

# Install only production dependencies (no dev group) into the project venv
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the source code
COPY src/ src/

# Install the project itself (editable is not needed in production)
RUN uv sync --frozen --no-dev


# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create a non-root user for security
RUN groupadd --system app && useradd --system --gid app app

# Copy the virtual environment and source from the builder stage
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Ensure the venv's binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Directory for generated reports (matches .gitignore entry)
RUN mkdir -p /app/generated_reports && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
