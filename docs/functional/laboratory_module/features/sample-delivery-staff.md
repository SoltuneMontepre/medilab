# Features of: Sample delivery staff

Sample delivery staff (nhân viên giao nhận mẫu) collect samples at the customer's site, receive the samples that arrive at the laboratory, hand them over to the departments that test them, and carry outsourced samples to subcontractors.

## I. User stories

### Collecting samples

- **US-SD01** As sample delivery staff, I want to see my sample collection tasks on my schedule and to-do list with their time and place, so that I know where to go and when.
- **US-SD02** As sample delivery staff, I want to be reminded before a collection starts, so that I am not late.
- **US-SD03** As sample delivery staff, I want to mark a collection task done when the samples are collected, so that the laboratory expects them.
- **US-SD04** As sample delivery staff, I want to take photos of a sample when I collect or receive it, so that its state is on record.
- **US-SD05** As sample delivery staff, I want the customer to sign a handover record on my phone when they hand samples over, so that both sides have proof of what was handed over.

### Receiving samples

- **US-SD06** As sample delivery staff, I want to create a test request for a customer with its samples, parameters, expected date and report delivery, so that the laboratory can take work that does not come through an order.
- **US-SD07** As sample delivery staff, I want to see the samples expected for each test request, so that I know what should arrive.
- **US-SD08** As sample delivery staff, I want to print a label with the lab code as a QR code for each sample, so that the sample can be identified and scanned without showing the customer.
- **US-SD09** As sample delivery staff, I want to record a sample's receipt with the amount, its condition and where it is stored, so that its state on arrival is on record.
- **US-SD10** As sample delivery staff, I want to reject a sample that cannot be tested, with the reason, so that nobody works on it.
- **US-SD11** As sample delivery staff, I want to put an insufficient sample on hold and report it to the head of department, so that it can be collected again.
- **US-SD12** As sample delivery staff, I want to hand a received sample over to each department that tests it, so that every department knows it has the sample.

### Carrying outsourced samples

- **US-SD13** As sample delivery staff, I want to see the dispatches I carry to subcontractors, so that the outsourced samples arrive when expected.

## II. Feature details

### 1. Collecting samples (US-SD01 to US-SD05)

Sample collection tasks follow [SH-10](../../shared.md#sh-10-tasks-and-to-do-list); reminders follow [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Scheduled task | Sales schedules a sample collection task on an order. A head of department's request to collect a sample again schedules one too. |
| Done by hand   | The task is marked done once the samples are collected.                                                           |
| Photos         | Photos of a sample are attached when it is collected or received, on the web or the mobile app. Testers never see them. |
| Handover record | The handover record lists each sample with the amount and condition handed over, who handed it over for the customer and who took it. The customer signs by hand on the mobile app; the signed PDF is emailed to the customer. A signed record cannot be edited; a correction is a new record. |

Acceptance criteria:

- A collection task assigned to sample delivery staff appears on their personal schedule and in their to-do list.
- A reminder arrives before the collection starts.
- A collection task created by a request to collect again shows the sample it is for.
- A photo taken on the mobile app appears on the sample on the web.
- Signing a handover record stores the signature, when and on which device it was signed, and emails the PDF to the customer.
- A signed handover record cannot be edited.

### 2. Receiving samples (US-SD06 to US-SD12)

Follows the reception rules and the sample lifecycle in the [Laboratory overview](../overview.md#reception).

| Rule          | Description                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Test request  | Without an order, sample delivery staff create the test request: customer, samples with their sample type, physical state and regulation, the parameters of each sample, expected date, report language, delivery method and report recipient. |
| Label         | Each sample's label shows its lab code as text and as a QR code, and nothing else about the customer.                       |
| Receipt       | Receipt records when and by whom the sample was received, the amount received, its condition (good, damaged or insufficient) with a note, and where it is stored. |
| Testing tasks | Receiving a sample creates a testing task for each of its sample tests in the queue of the department that does the work.   |
| Handover      | The sample is handed over to each department that tests it; the department records when and by whom it received it.         |

Acceptance criteria:

- A test request created by sample delivery staff skips the paid step.
- A sample's label shows its lab code and QR code but not the customer's name for it.
- Recording a sample's receipt sets it to received and creates its testing tasks in each department's queue.
- A rejected sample keeps its condition note and gets no testing tasks.
- An insufficient sample is on hold, and its head of department is told.
- A sample handed over to two departments shows both handovers and which department has received it.

### 3. Carrying outsourced samples (US-SD13)

| Rule     | Description                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Carrier  | A dispatch is carried by sample delivery staff or by a delivery service, as the head of department records on it. |

Acceptance criteria:

- A dispatch assigned to sample delivery staff appears in their list of dispatches to carry, with the subcontractor and the date sent.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
