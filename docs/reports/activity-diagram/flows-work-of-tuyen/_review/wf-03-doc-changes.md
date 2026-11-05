# WF-03 Testing assignment and scheduling: doc changes

Differences from `## WF-03 Testing assignment and scheduling` in `docs/functional/business-flows.md` that the owner accepted in `[Flow] WF-03 Testing assignment and scheduling.drawio`. The documents are updated later from these notes.

## Notify the assigned tester

- **Diagram:** after the head assigns the tester ("Assign tester"), the system sends "✉ Notify tester" to the assigned tester, who then opens the proposed booking. Claiming a task notifies nobody, as the tester acts themselves.
- **Concerns:** `## WF-03 Testing assignment and scheduling`, its Main path and its mermaid (`h1 --> t2`); the notification rules of [SH-11](../../../../functional/shared.md#sh-11-schedules-and-reminders) in `docs/functional/shared.md` ("Own actions").
- **New text:**
  - Main path: "The head assigns an authorized tester, who is notified, or that tester claims the task; …"
  - Mermaid: `h1 --> notify[Notify the assigned tester] --> t2`
  - SH-11, Own actions: "Nobody is notified of their own action, such as claiming a task. Task notifications are for events that need attention, such as a task assigned to the person by someone else or a task coming due; …"

## The system decides whether the booking is feasible

- **Diagram:** the decision "Feasible booking before the due date?" is in the System lane, after the tester views the proposed booking: yes leads to accepting the booking, no to the head's review.
- **Concerns:** the mermaid of `## WF-03 Testing assignment and scheduling`, which puts `t3{Feasible booking within capacity?}` in the Tester lane. WF-03-E2 and the outsourcing rule of [Head of department](../../../../functional/laboratory_module/features/head-of-department.md) already say the scheduler finds no feasible slot before the due date.
- **New text:** in the mermaid, move the decision out of the Tester subgraph, beside `queue` and `reserve`: `t2 --> feasible{Feasible booking before the due date?}`, with its `yes`, `yes, the head accepts` and `no` lines leaving `feasible`.

## The reminder is the system's; measuring belongs to WF-04

- **Diagram:** after the reservation, the system sends "✉ Remind tester before the booking starts", and the flow ends "Test booked → WF-04 Result entry and approval". The tester's measuring is not in WF-03.
- **Concerns:** the mermaid of `## WF-03 Testing assignment and scheduling`, which has `t5[Receive reminder and measure]` in the Tester lane between `reserve` and `wf04`. `## WF-04 Result entry and approval` already starts when "a booked test starts" with `t1[Follow the method and measure in the booking]`.
- **New text:** in the mermaid, replace `t5` with a system step outside the lanes: `reserve --> remind[Remind the tester before the booking starts] --> wf04([WF-04 Result entry and approval])`.
