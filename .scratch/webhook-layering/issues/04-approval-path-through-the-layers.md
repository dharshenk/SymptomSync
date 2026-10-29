# 04: Approval path through the layers

**What to build:** The human-in-the-loop booking approval works through the new layers. When a run is ready to book, the Patient gets an Approval Prompt (booking summary with Go Ahead and Changes needed choices) and the run is saved as a Pending Approval. `handle_decision` applies the Patient's Decision. One application-layer unit owns the Pending Approval lifecycle: save when paused, claim on a Decision so a repeat finds nothing, restore on error, and while a row exists a new message only re-sends the prompt (or a "still working" reply while the Decision is being applied). The Telegram adapter maps button callbacks to a `Decision`, renders choices as an inline keyboard, and on a press removes the buttons and acknowledges it before the run, then runs under the typing indicator and sends the Reply.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] The Approval Prompt is a neutral Reply with choices; the booking-summary text is built in the application layer
- [ ] Callback strings `approve` / `changes_needed` appear only in the Telegram adapter
- [ ] Go Ahead resumes the run and books; Changes needed does not book and asks the Patient what to change
- [ ] A repeated press does nothing the second time
- [ ] A message while a Decision is pending gets the Approval Prompt again; while it is being applied, a "still working" reply
- [ ] A failure while applying a Decision restores the Pending Approval so it can be retried
- [ ] An unknown callback value re-sends the prompt, or says nothing is waiting
- [ ] Application-seam tests cover pause, Go Ahead, Changes needed, repeated press, message while pending, message while processing and error restore
- [ ] Adapter-seam tests cover callback mapping, keyboard rendering and the ack-before-run ordering
