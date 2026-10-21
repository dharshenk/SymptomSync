# WhatsApp & Telegram Patient Intake Agent

AI-powered patient intake and appointment booking through WhatsApp and Telegram.

The agent collects patient information, checks doctor availability, books appointments, and generates a PDF summary — all within a chat conversation.

<p align="center">
  <img src="./docs/demo%20gif/demo.gif" alt="Demo" width="400" />
</p>

## Features

* WhatsApp and Telegram integrations
* AI-driven patient intake workflow
* Doctor availability lookup
* Appointment booking
* Patient summary PDF generation
* PostgreSQL persistence
* OpenTelemetry tracing
* FastAPI backend
* Docker-based deployment

## Architecture

```text
WhatsApp / Telegram
         │
         ▼
      Webhook
         │
         ▼
      FastAPI
         │
         ▼
      AI Agent
         │
 ┌───────┼────────┐
 ▼       ▼        ▼
Patients Slots  Booking
 Service  Tool    Tool
         ▲
         │
         ▼
    PostgreSQL
         │
         ▼
     PDF Report
```

## Tech Stack

* FastAPI
* PostgreSQL
* OpenAI
* ReportLab
* OpenTelemetry
* Docker Compose
* uv

## Example Flow

1. Patient starts a chat on WhatsApp or Telegram
2. Agent collects intake information
3. Agent checks doctor availability
4. Patient selects a slot
5. Appointment is booked
6. PDF summary is generated
7. Confirmation is sent

## Tracing with Jaeger

`docker compose up --build` starts Jaeger alongside the API and sends traces to
`http://jaeger:4318` over the Compose network. Open <http://localhost:16686> and
select the `symptom-sync` service after sending an API request. Jaeger uses
in-memory storage; its traces are lost when the container restarts.

For an API running locally, start Jaeger with `docker compose up -d jaeger`, then
set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` in the API process's
environment before starting Uvicorn. Alternatively, set
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces` (this takes
precedence over the base endpoint, including in Compose).

Without either endpoint configured, the app leaves tracing disabled. Set
`OTEL_SDK_DISABLED=true` to disable tracing even when an endpoint is configured.
