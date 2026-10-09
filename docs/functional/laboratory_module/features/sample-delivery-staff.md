# Features of: Sample delivery staff

Sample delivery staff (nhân viên giao nhận mẫu) collect samples at the customer's site, receive the samples that arrive at the laboratory, hand them over to the departments that test them, and carry outsourced samples to subcontractors.

## I. User stories

### Collecting samples

- **US-SD01** As sample delivery staff, I want to see my sample collection tasks on my schedule and to-do list with their time and place, so that I know where to go and when.
- **US-SD02** As sample delivery staff, I want to be reminded before a collection starts, so that I am not late.
- **US-SD03** As sample delivery staff, I want to mark a collection task done when the samples are collected, so that the laboratory expects them.

### Receiving samples

- **US-SD04** As sample delivery staff, I want to see the samples expected for each test request, so that I know what should arrive.
- **US-SD05** As sample delivery staff, I want to record a sample's receipt with the amount, its condition and where it is stored, so that its state on arrival is on record.
- **US-SD06** As sample delivery staff, I want to reject a sample that cannot be tested, with the reason, so that nobody works on it.
- **US-SD07** As sample delivery staff, I want to put an insufficient sample on hold and report it to the head of department, so that it can be collected again.
- **US-SD08** As sample delivery staff, I want to hand a received sample over to each department that tests it, so that every department knows it has the sample.

### Carrying outsourced samples

- **US-SD09** As sample delivery staff, I want to see the dispatches I carry to subcontractors, so that the outsourced samples arrive when expected.

## II. Feature details

### 1. Collecting samples (US-SD01 to US-SD03)

Sample collection tasks follow [SH-10](../../shared.md#sh-10-tasks-and-to-do-list); reminders follow [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Scheduled task | Sales schedules a sample collection task on an order. A head of department's request to collect a sample again schedules one too. |
| Done by hand   | The task is marked done once the samples are collected.                                                           |

Acceptance criteria:

- A collection task assigned to sample delivery staff appears on their personal schedule and in their to-do list.
- A reminder arrives before the collection starts.
- A collection task created by a request to collect again shows the sample it is for.

### 2. Receiving samples (US-SD04 to US-SD08)

Follows the reception rules and the sample lifecycle in the [Laboratory overview](../overview.md#reception).

| Rule          | Description                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Receipt       | Receipt records when and by whom the sample was received, the amount received, its condition (good, damaged or insufficient) with a note, and where it is stored. |
| Testing tasks | Receiving a sample creates a testing task for each of its sample tests in the queue of the department that does the work.   |
| Handover      | The sample is handed over to each department that tests it; the department records when and by whom it received it.         |

Acceptance criteria:

- Recording a sample's receipt sets it to received and creates its testing tasks in each department's queue.
- A rejected sample keeps its condition note and gets no testing tasks.
- An insufficient sample is on hold, and its head of department is told.
- A sample handed over to two departments shows both handovers and which department has received it.

### 3. Carrying outsourced samples (US-SD09)

| Rule     | Description                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Carrier  | A dispatch is carried by sample delivery staff or by a delivery service, as the head of department records on it. |

Acceptance criteria:

- A dispatch assigned to sample delivery staff appears in their list of dispatches to carry, with the subcontractor and the date sent.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
