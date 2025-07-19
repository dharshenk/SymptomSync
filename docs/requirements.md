# Telemedicine Intake Assistant – Product Features

## Overview

The **Telemedicine Intake Assistant** is a generative AI-powered system that interacts with patients through a conversational interface (text or voice) to gather relevant medical information before a consultation. It aims to reduce consultation time, improve doctor preparedness, and streamline appointment scheduling without taking on the role of diagnosis.

---

## Product Scope & Delivery Plan

### Platforms
- **Web Frontend** (Responsive, P1)
- **WhatsApp Bot Integration** (P1)
- **Voice Assistant** (Interactive, P2 – Post chat-version MVP)

### Primary Personas
- **Patient** (first-time or returning)
- **Doctor**
- **Healthcare Admin / Receptionist**

---

## EPIC: Patient Intake & Triage Assistant

### 🎯 P1 Features

#### 1. Patient Conversational Flow (Text)
- Structured conversation to capture:
  - Current symptoms
  - Duration and severity
  - Recent events (travel, injury, stress)
  - Medication intake
  - Allergies
  - Chronic conditions
  - Lifestyle habits
- Uses dynamic prompt engineering for follow-up questions
- Conversation is summarized into structured format (JSON) for doctor's use

#### 2. Patient Profile Management
- Secure login and profile
- View and update basic health history
- Access previous consultations (if available)
- Link with external EMRs (optional for P2)

#### 3. Appointment Scheduling
- Available time slots from hospital/clinic calendar
- User can select slot and confirm
- Reminders over WhatsApp & Email

#### 4. WhatsApp Bot Integration
- Entire intake conversation over WhatsApp
- Ability to resume from where the patient left off
- Button-based UI for easier interactions

#### 5. Guarding & Safety Layer
- **Rule-based filters + LLM safety prompts** to:
  - Prevent any diagnosis or medication suggestions
  - Reject and redirect any diagnosis-related queries with a templated response
- **Human-in-loop design**: Always closes with "a doctor will review this"
- Monitors AI response logs for safety violations
- Escalation if AI fails or user reports harm

---

### 🚧 P2 Features

#### 6. Voice Assistant Support (Interactive)
- Voice-first interface that:
  - Reads out questions
  - Captures voice input
  - Converts to text, summarizes in background
  - Feels like a human-like guided intake interview
- Multilingual support roadmap (starting with English)

#### 7. Doctor Interface
- View structured intake summary
- Add annotations
- See patient historical record
- Option to initiate video/audio consultation (P2++)

#### 8. Health Record Integration
- Allow patients to upload past prescriptions, lab reports
- Use OCR + GenAI to extract relevant info
- Tag and attach to current intake summary

#### 9. Triage Tagging for Clinic Workflow
- Auto-label urgency (Low/Moderate/Urgent)
- Support admin prioritization
- Tag potential specializations (e.g., Ortho, ENT)

#### 10. Patient Education / Follow-ups
- Basic generative summaries of what next steps to expect
- Tailored info (e.g., “how to prepare for your ENT consult”)
- WhatsApp follow-up prompts ("How are you feeling after your visit?")

---

## Future Enhancements (Nice-to-Have, not scoped for MVP)

- Symptom progression tracking across visits
- Gamified symptom check-in for chronic patients
- Integration with wearables for contextual info (Fitbit, Apple Watch)

---

## Non-Functional Requirements

- HIPAA & Indian IT Act 2000 compliant (data privacy)
- Scalable backend (FastAPI/Node.js) for integrations
- Secure auth (OAuth2, WhatsApp auth binding)
- Logs & monitoring for guardrail effectiveness

---

## MVP Definition

**MVP = Chat-based intake + WhatsApp + Appointment Scheduling + Guardrails + Summary output for doctor**

---

## Notes

- All diagnosis responsibilities lie **strictly with the doctor**.
- The AI is a **helper**, not a replacement for clinical judgment.
