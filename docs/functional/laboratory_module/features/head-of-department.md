# Features of: Head of department

The head of department runs the testing work of one department: they assign its tasks, manage its schedule, decide on outsourcing, approve its results and handle samples that arrive insufficient. A head of department also has every feature of a [tester](tester.md).

## I. User stories

### Work and schedule

- **US-HD01** As a head of department, I want to see my department's queue of testing tasks with their due dates, so that nothing waits unnoticed.
- **US-HD02** As a head of department, I want to assign a sample's testing tasks, or a single task, to a person in my department, and reassign them with a reason, so that every test has someone responsible.
- **US-HD03** As a head of department, I want to see my department's machine schedules and the people's schedules, so that I can balance the work.
- **US-HD04** As a head of department, I want to move or cancel a booking of someone in my department, so that I can handle absences and incidents.
- **US-HD05** As a head of department, I want to see the scheduler's outsourcing suggestions for tests that cannot finish in time in-house, so that they still meet their due date.

### Samples and results

- **US-HD06** As a head of department, I want my department to record that it received a sample handed over to it by scanning the sample's label, so that the handover is on record.
- **US-HD07** As a head of department, I want to ask for an insufficient sample to be collected again, so that its tests can go ahead.
- **US-HD08** As a head of department, I want to approve or reject the results of my department with a reason, so that only checked results reach the report.
- **US-HD09** As a head of department, I want to cancel a sample test of my department with a reason, so that a test that cannot be done does not hold up the report.

### Outsourcing

- **US-HD10** As a head of department, I want to accept an outsourcing suggestion and put its sample tests in a dispatch to the subcontractor, so that tests that cannot finish in time in-house still meet their due date.
- **US-HD11** As a head of department, I want to record when a dispatch is sent, who or which delivery service takes it, and when its results are expected back, so that the outsourcing schedule shows where every outsourced test is.

## II. Feature details

### 1. Work and schedule (US-HD01 to US-HD05)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule                | Description                                                                                                             |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Queue               | Testing tasks of the department wait in its queue until the head assigns them.                                          |
| Assignment          | The head assigns all of a sample's testing tasks in the department to one person at once, or a single task; testers can also claim unassigned tasks. Assigning makes the scheduler recommend a way of testing, machine and slot to the assignee. Moving a task to another person or department needs a reason. |
| Adjusting           | The head can move or cancel any booking of the department; the slot goes back to the queue.                            |
| Outsourcing         | When no machine can finish a test in time, or a machine becomes unavailable, the scheduler suggests outsourcing it through one of the parameter's subcontracted ways of testing. |

Acceptance criteria:

- A testing task in the department queue disappears from the queue once assigned, and appears in the assignee's to-do list.
- Assigning a sample assigns all of its testing tasks in the department to the chosen person.
- Reassigning a task to another person or department without a reason is refused; the reason is kept on the task.
- A head of department sees the bookings of their department's people and machines, not those of other departments.
- A test that no machine can finish before its due date shows an outsourcing suggestion.

### 2. Samples and results (US-HD06 to US-HD09)

Follows [Reception](../overview.md#reception), [Results](../overview.md#results) and the [approval and signing chain](../../../business/approval-and-signing-chain.md).

| Rule          | Description                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| Handover      | A person of the department records when and by whom it received a handed-over sample by scanning its label, on the web or the mobile app. |
| Collect again | Asking for an insufficient sample to be collected again schedules a sample collection task for sample delivery staff. |
| Approval      | The head signs or rejects results at their level of the test result's approval chain; a rejection records its reason. A head cannot approve a result they entered. |
| Cancelling    | The head cancels a sample test of the department that has no approved result, with a reason. Its task and bookings are cancelled, and the report leaves it out. |

Acceptance criteria:

- Scanning a sample's label records the handover for the scanner's department; a person outside the department is refused.
- Asking for a sample to be collected again creates a sample collection task and records who asked and when.
- Rejecting a result sends its sample test back to testing and tells the tester the reason.
- Once every result of a sample is approved, the sample is completed.
- A head cannot approve a result they entered.
- Cancelling a sample test without a reason is refused; a cancelled test does not appear on the report.
- A sample whose remaining tests are all approved is completed even if others were cancelled.

### 3. Outsourcing (US-HD10, US-HD11)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and the [subcontractor rules](admin.md#3-subcontractors-us-ad12).

| Rule        | Description                                                                                                                 |
| ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| Accept      | Accepting a suggestion marks its sample tests as outsourced through the suggested subcontracted way of testing.              |
| Dispatch    | Outsourced sample tests for one subcontractor go in a dispatch: date sent, date results are expected back, and sample delivery staff (nhân viên giao nhận mẫu) or a delivery service with its tracking number. |
| Accreditation | A subcontractor whose accreditation has expired cannot be chosen.                                                          |

Acceptance criteria:

- Accepting an outsourcing suggestion sets its sample tests to outsourced.
- A sent dispatch appears on the outsourcing schedule with its expected date.
- A dispatch records either the sample delivery staff who took it or the delivery service and tracking number.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Tester](tester.md)
- [Sample delivery staff](sample-delivery-staff.md)
- [Lab head](lab-head.md)
