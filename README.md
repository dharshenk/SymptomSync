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

## Tracing with Grafana Cloud

The API exports traces directly to Grafana Cloud using OTLP over HTTPS. In your
Grafana Cloud stack's OpenTelemetry configuration, generate connection settings
with permission to write traces. Copy the endpoint and authentication header into
your local, ignored `.env` file:

```dotenv
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-otlp-host>/otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64-credentials>
OTEL_SDK_DISABLED=false
```

Use your stack's generated values, including `Basic%20` for Python's header
parser. Keep credentials out of version control. See Grafana's
[OTLP connection instructions](https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/).
The exporter appends `/v1/traces` to the base endpoint. If you previously set
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_HEADERS`, remove
them or update them to your Grafana Cloud values; they override the generic settings.

Run `docker compose up --build -d app` to apply the settings. Compose reads them
from `.env`. For local Uvicorn runs, load them with
`uv run uvicorn main:app --app-dir src --reload --env-file .env`.
After sending an API request, open Grafana Explore, select your traces data source,
and filter by `service.name = symptom-sync`.

Without either endpoint configured, the app leaves tracing disabled. Set
`OTEL_SDK_DISABLED=true` to disable tracing even when an endpoint is configured.
