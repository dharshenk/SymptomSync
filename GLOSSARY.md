# SymptomSync

A chat assistant that talks to patients over messaging, collects their details and symptoms, and books a doctor's appointment once the patient confirms.

## Language

**Patient**:
A person who chats with the assistant to arrange an appointment.
_Avoid_: User, customer

**Sender ID**:
The identifier the messaging platform gives a Patient; it identifies the Patient and their Chat Session. Stored in the legacy-named `patient_ph_no` field, although it is not a phone number.
_Avoid_: Phone number, ph_no

**Chat Session**:
The single ongoing conversation between one Patient and the assistant, including its message history.
_Avoid_: Thread, conversation

**Intake State**:
The details gathered from the Patient so far (name, age, gender, symptoms, conditions, medications, preferred date and start time) for the current Chat Session.
_Avoid_: Form, patient details

**Agent Run**:
One pass of the assistant working out a reply to a Patient's message, possibly using tools along the way.
_Avoid_: Turn, completion

**Approval Prompt**:
The booking summary shown to the Patient with the choices Go Ahead and Changes needed, sent when an Agent Run is ready to book.
_Avoid_: Confirmation message

**Pending Approval**:
A paused Agent Run waiting for the Patient's Decision; at most one exists per Chat Session.
_Avoid_: Pending booking

**Decision**:
The Patient's answer to an Approval Prompt: Go Ahead books the appointment, Changes needed cancels the booking attempt and asks what to change.
_Avoid_: Response, button press
