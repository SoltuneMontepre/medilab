# WF-03 Testing assignment and scheduling: doc changes

Differences from `## WF-03 Testing assignment and scheduling` in `docs/functional/business-flows.md` that the owner accepted in `[Flow] WF-03 Testing assignment and scheduling.drawio`. The documents are updated later from these notes.

## Notify the assigned tester

- **Diagram:** after the head assigns the tester ("Assign tester"), the system sends "✉ Notify tester" to the assigned tester, who then opens the proposed booking. Claiming a task notifies nobody, as the tester acts themselves.
- **Concerns:** `## WF-03 Testing assignment and scheduling`, its Main path and its mermaid (`h1 --> t2`); the notification rules of [SH-11](../../../functional/shared.md#sh-11-schedules-and-reminders) in `docs/functional/shared.md` ("Own actions").
- **New text:**
  - Main path: "The head assigns an authorized tester, who is notified, or that tester claims the task; …"
  - Mermaid: `h1 --> notify[Notify the assigned tester] --> t2`
  - SH-11, Own actions: "Nobody is notified of their own action, such as claiming a task. Task notifications are for events that need attention, such as a task assigned to the person by someone else or a task coming due; …"

## The system decides whether the booking is feasible

- **Diagram:** the decision "Feasible booking before the due date?" is in the System lane, after the tester views the proposed booking: yes leads to the head's approval, no to the head's review.
- **Concerns:** the mermaid of `## WF-03 Testing assignment and scheduling`, which puts `t3{Feasible booking within capacity?}` in the Tester lane. WF-03-E2 and the outsourcing rule of [Head of department](../../../functional/laboratory_module/features/head-of-department.md) already say the scheduler finds no feasible slot before the due date.
- **New text:** in the mermaid, move the decision out of the Tester subgraph, beside `queue` and `reserve`: `t2 --> feasible{Feasible booking before the due date?}`, with `feasible -->|yes| approve` and `feasible -->|no| h2`.

## The head approves every feasible booking

- **Diagram:** after "Feasible booking before the due date?" answers yes, the head decides "Head approves the proposed booking?". Yes: the tester gets "Receive booking approval notification", then the system reserves the tester, required locations and machine if needed together. No: the head goes to "Review risk and feasible alternatives". Neither the tester nor the head accepts a proposed booking without this approval. The Demo scenarios page shows it in DS-03a and DS-03b: the head's "Approve the proposed booking", then the tester's "Receive booking approval notification".
- **Concerns:**
  - `## WF-03 Testing assignment and scheduling`: Main path ("the tester or head accepts it"), WF-03-E1 ("an authorized person accepts the booking") and the mermaid (`h4[Accept the proposed booking for the tester]`, `t4[Accept the proposed booking]`, `t3 -->|yes, the head accepts| h4`). SF-10's Paths in other flows ("WF-03 owns initial assignment and accepting bookings").
  - [Tester](../../../functional/laboratory_module/features/tester.md): US-T02 ("I want to accept a booking of the agreed way of testing from my department's proposed plan") and the rule "Accepting a booking checks that the tester, every required location and a machine when required are available".
  - [Head of department](../../../functional/laboratory_module/features/head-of-department.md): no story yet for approving a proposed booking.
  - The mermaid of [Laboratory overview](../../../functional/laboratory_module/overview.md) (`plan --> accept[Tester or head accepts the booking]`) and [Scheduling](../../../specs/scheduling.md) ("Testers and heads accept proposed bookings to schedule them"; the Accepting row).
  - The use case "Accept Proposed Booking" of US-T02 in [Use case diagram](../../use-case-diagram/readme.md).
- **New text:**
  - Main path: "… the department's plan proposes a booking of the agreed way in priority order; when it is feasible before the due date, the head approves it, the tester is notified, and it receives a reminder."
  - WF-03-E1: "… the head moves the task to another person or department with a reason, approves the proposed booking, and the new tester is notified."
  - Mermaid: in the Head of department subgraph, replace `h4` with `approve{Approve the proposed booking?}`; in the Tester subgraph, replace `t4` with `t4[Receive booking approval notification]`; `approve -->|yes| t4 --> reserve`, `approve -->|no| h2`.
  - US-T02 becomes "As a tester, I want to be notified when the head approves a booking of my task, so that I know when to test"; a new head-of-department story: "As a head of department, I want to approve a feasible proposed booking of my department, so that it is reserved before its due date."
  - Scheduling: "Heads approve proposed bookings to schedule them; the tester is notified." The Accepting row becomes Approving: "Approving a booking reserves its tester, machine and locations together, or nothing when any of them is taken meanwhile."

## The reminder is the system's; measuring belongs to WF-04

- **Diagram:** after the reservation, the system sends "✉ Remind tester before the booking starts", and the flow ends "Test booked → WF-04 Result entry and approval". The tester's measuring is not in WF-03.
- **Concerns:** the mermaid of `## WF-03 Testing assignment and scheduling`, which has `t5[Receive reminder and measure]` in the Tester lane between `reserve` and `wf04`. `## WF-04 Result entry and approval` already starts when "a booked test starts" with `t1[Follow the method and measure in the booking]`.
- **New text:** in the mermaid, replace `t5` with a system step outside the lanes: `reserve --> remind[Remind the tester before the booking starts] --> wf04([WF-04 Result entry and approval])`.
