# Features of: Sample delivery staff

Sample delivery staff (nhân viên giao nhận mẫu) collect samples at the customer's site, receive the samples that arrive at the laboratory, hand them over to the departments that test them, carry outsourced samples to subcontractors, and return the untested sample material customers ask for.

## I. User stories

### Collecting samples

- **US-SD01** As sample delivery staff, I want to see my sample collection tasks on my schedule and to-do list with their time and place, so that I know where to go and when.
- **US-SD02** As sample delivery staff, I want to be reminded before a collection starts, so that I am not late.
- **US-SD03** As sample delivery staff, I want to mark a collection task done when the samples are collected, so that the laboratory expects them.
- **US-SD04** As sample delivery staff, I want to take photos of a sample when I collect or receive it, so that its state is on record.
- **US-SD05** As sample delivery staff, I want the customer to sign a handover record when they hand samples over, so that both sides have proof of what was handed over.

### Receiving samples

- **US-SD06** As sample delivery staff, I want to create a test request for a customer with its samples, parameters, requested date and report delivery, so that the laboratory can take work that does not come through an order.
- **US-SD07** As sample delivery staff, I want to see the samples expected for each test request, so that I know what should arrive.
- **US-SD08** As sample delivery staff, I want to print a label for each sample with its lab code, test request, results due date and a QR code, so that the sample can be identified and scanned without showing the customer.
- **US-SD09** As sample delivery staff, I want to record a sample's receipt with the amount, its condition and where it is stored, so that its state on arrival is on record.
- **US-SD10** As sample delivery staff, I want to reject a sample that cannot be tested, with the reason, so that nobody works on it.
- **US-SD11** As sample delivery staff, I want to put an insufficient sample on hold and report it to the head of department, so that it can be collected again.
- **US-SD12** As sample delivery staff, I want to hand a received sample over to each department that tests it, so that every department knows it has the sample.

### Carrying outsourced samples

- **US-SD13** As sample delivery staff, I want to see the dispatches I carry to subcontractors, so that the outsourced samples arrive when expected.

### Delivering reports

- **US-SD14** As sample delivery staff, I want to see the issued reports waiting for delivery and record each delivery, so that every customer gets their report the way they asked.

### Returning samples

- **US-SD15** As sample delivery staff, I want to return untested sample material to a customer who asks for it and record the return, so that the customer gets back what the laboratory did not use.

## II. Feature details

### 1. Collecting samples (US-SD01 to US-SD05)

Sample collection tasks follow [SH-10](../../shared.md#sh-10-tasks-and-to-do-list); reminders follow [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Scheduled task | Sales schedules a sample collection task on a confirmed order with **Start sample collection**: one task of the order's test request, in the shared queue of sample delivery staff, with the customer's address as its place and no time. Sample delivery staff claim it and plan its time. An order has at most one open collection task. The administrator routes the Sample collection task type to the role of sample delivery staff. A head of department's request to collect a sample again schedules one too. |
| Travel time | Reserve a configurable travel buffer between collection appointments, 60 minutes by default, when checking whether the staff member can take them. |
| Done by hand   | The task is marked done once the samples are collected.                                                           |
| Photos | Attach sample photos through the web interface when collecting or receiving a sample. Testers never see them. |
| Sampling location | When a sample is collected or received, the location it was taken from, such as sampling point RO-01, can be chosen from the locations. |
| Handover record | Record the staff member, appointment and collection time, actual samples and amounts, conditions, differences from the order and the customer's signature. A request can have several collections. Email the signed PDF; correct a signed record by a new record, preserving the old one. |
| Actual samples | Adjust the expected samples calculated from method sampling requirements to what is actually handed over for customer confirmation, including extra samples and excess material. Fewer samples wait for another collection or Sales cancels the missing part. Testing stays within the agreed scope: extra samples and excess material add no test and stay with the sample until the customer asks for them back ([Returning samples](#5-returning-samples-us-sd15)). |

Acceptance criteria:

- A collection task assigned to sample delivery staff appears on their personal schedule and in their to-do list.
- Starting sample collection on a confirmed order queues one unassigned collection task for sample delivery staff, and starting it again while that task is open is refused.
- A reminder arrives before the collection starts.
- A collection task created by a request to collect again shows the sample it is for.
- A photo attached at collection appears only to readers who may see the customer's sample name; testers cannot see it.
- Two collection appointments that leave less than the configured travel buffer are not offered as feasible.
- One request can record several collections and their differences from expected samples.
- Extra samples and excess material recorded at handover add no sample test.
- Signing a handover record stores the signature, when and on which device it was signed, and emails the PDF to the customer.
- A signed handover record cannot be edited.

### 2. Receiving samples (US-SD06 to US-SD12)

Follows the reception rules and the sample lifecycle in the [Laboratory overview](../overview.md#reception).

| Rule          | Description                                                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Test request | Without an order, create a request with customer, samples and their types, optional regulation comparison, each sample's parameters and selected ways, the customer's requested date, report language, delivery method and recipient. |
| Identification QR | Use only the sample's QR for identification and handover; test requests and handover documents have no separate identification QR. |
| Return estimate | The test request shows the estimated return date of its samples and parameters. Its committed return date defaults to the requested date when the laboratory can meet it, otherwise to the estimate; an earlier requested date is checked as a [priority request](../overview.md#testing-work-and-scheduling) before it is accepted. |
| Label         | The label shows the lab code, the test request's code, the date results are due and a QR code of the lab code, and nothing about the customer. |
| Receipt       | Receipt records when and by whom the sample was received, the amount received, its condition (good, damaged or insufficient) with a note, and where it is stored. |
| Testing tasks | Receiving a sample creates a testing task for each of its sample tests in the queue of the department that does the work.   |
| Handover      | The sample is handed over to each department that tests it; the department records when and by whom it received it.         |

Acceptance criteria:

- A test request created by sample delivery staff skips the paid step.
- A sample's label shows its lab code, test request code, results due date and QR code, but not the customer or the customer's name for the sample.
- Recording a sample's receipt sets it to received and creates its testing tasks in each department's queue.
- A rejected sample keeps its condition note and gets no testing tasks.
- An insufficient sample is on hold, and its head of department is told.
- A sample handed over to two departments shows both handovers and which department has received it.
- Scanning identifies the individual sample; the test request and handover document do not add another identification QR.

### 3. Carrying outsourced samples (US-SD13)

| Rule     | Description                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Carrier  | A dispatch is carried by sample delivery staff or by a delivery service, as the head of department records on it. Only people holding the sample delivery staff role, which the administrator names in the Laboratory settings, can be chosen. |

Acceptance criteria:

- A dispatch assigned to sample delivery staff appears in their list of dispatches to carry, with the subcontractor and the date sent.
- Only people holding the role named in the Laboratory settings are offered to take a dispatch, and choosing anyone else is refused; with no role named, nobody is.

### 4. Delivering reports (US-SD14)

Follows [Reports and change requests](../overview.md#reports-and-change-requests).

| Rule     | Description                                                                                                         |
| -------- | ------------------------------------------------------------------------------------------------------------------- |
| Waiting  | Issued, undelivered reports are listed with their delivery method, note and the contact who receives them. A report pending digital signing remains unissued and enters this list only after its signed PDF is stored and the report is issued. |
| Delivery | Sample delivery staff deliver the report as the test request says and record when it was delivered; they are recorded as who delivered it. A report sent by email is emailed to its recipient from the system. |

Acceptance criteria:

- Issuance makes the stored report PDF available in the list waiting for delivery, until its delivery is recorded. A digital-signing failure leaves the report outside that list.
- Recording a delivery stores when and by whom.
- A report not yet issued cannot be delivered.

### 5. Returning samples (US-SD15)

| Rule     | Description |
| -------- | ----------- |
| Returned | Extra samples and excess material, which testing never uses, and a retained sample once its retention period is over. |
| When     | Only when the customer asks: at the counter when they collect the report in person, or at a separate pickup. |
| Record   | A return records what was returned, when, by whom and to whom. Returning extra samples or excess material does not change the sample's state; returning a retained sample after its retention period ends it as returned instead of disposed. |
| Not asked for | What nobody asks for is disposed of with the sample under its retention rules. |

Acceptance criteria:

- A retained sample cannot be returned before its retention period ends.
- A return stores what was returned, when, by whom and to whom.
- Returning excess material leaves the sample's state unchanged; returning a retained sample ends it as returned.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
