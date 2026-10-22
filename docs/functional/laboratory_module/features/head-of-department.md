# Features of: Head of department

The head of department runs the testing work of one department: they assign its tasks, manage its schedule, decide on outsourcing, approve its results and handle samples that arrive insufficient. A head of department also has every feature of a [tester](tester.md).

## I. User stories

### Work and schedule

- **US-HD01** As a head of department, I want to see my department's queue of testing tasks with their due dates, so that nothing waits unnoticed.
- **US-HD02** As a head of department, I want to assign a sample's testing tasks, or a single task, to a person in my department, and reassign them with a reason, so that every test has someone responsible.
- **US-HD03** As a head of department, I want to see my department's machine schedules and the people's schedules, so that I can balance the work.
- **US-HD04** As a head of department, I want to move or cancel a booking of someone in my department, so that I can handle absences and incidents.
- **US-HD05** As a head of department, I want to see the scheduler's outsourcing suggestions for tests that cannot finish in time in-house, so that they still meet their due date.
- **US-HD12** As a head of department, I want to bump an urgent test to the earliest slot on a machine, moving bookings that have not started out of its way, so that a sample needed right away is tested right away.
- **US-HD14** As a head of department, I want to see my department's tests at risk of missing their due date, so that I can move work, bump or outsource in time.

### Samples and results

- **US-HD06** As a head of department, I want my department to record that it received a sample handed over to it by scanning the sample's label, so that the handover is on record.
- **US-HD07** As a head of department, I want to ask for an insufficient sample to be collected again, so that its tests can go ahead.
- **US-HD08** As a head of department, I want to approve or reject the results of my department with a reason, so that only checked results reach the report.
- **US-HD09** As a head of department, I want to cancel a sample test of my department with a reason, so that a test that cannot be done does not hold up the report.

### Outsourcing

- **US-HD10** As a head of department, I want to accept an outsourcing suggestion and put its sample tests in a dispatch to the subcontractor, so that tests that cannot finish in time in-house still meet their due date.
- **US-HD11** As a head of department, I want to record when a dispatch is sent, who or which delivery service takes it, and when its results are expected back, so that the outsourcing schedule shows where every outsourced test is.
- **US-HD13** As a head of department, I want to outsource a test of my department straight away with a reason, without waiting for an outsourcing suggestion, so that an emergency is handled when no machine is free in time.

### Laboratory files

- **US-HD15** As a head of department, I want to create the raw-data and result folders of a sample, so that its testers save their files in the right place.
- **US-HD16** As a head of department, I want to sign or reject a version of a result file with a reason, so that the file a report relies on is approved.

### Mobile

- **US-HD17** As a head of department, I want to assign my department's tasks and sign or reject its results on my phone, so that work and results do not wait while I am away from my desk.

## II. Feature details

### 1. Work and schedule (US-HD01 to US-HD05, US-HD12, US-HD14)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule                | Description                                                                                                             |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Queue               | Testing tasks of the department wait in its queue until the head assigns them.                                          |
| Assignment          | The head assigns all of a sample's testing tasks in the department to one person at once, or a single task; testers can also claim unassigned tasks. Assigning makes the scheduler recommend a way of testing, machine and slot to the assignee. Moving a task to another person or department needs a reason. |
| Adjusting           | The head can move or cancel any booking of the department; the slot goes back to the queue.                            |
| Marking urgent      | The head can mark any test of the department urgent, stating why, or remove the mark, as the tester does ([US-T19](tester.md#1-planning-us-t01-to-us-t04-us-t19-to-us-t21)). |
| Outsourcing         | When no machine can finish a test in time, or a machine becomes unavailable, the scheduler suggests outsourcing it through one of the parameter's subcontracted ways of testing. |
| Bumping             | The head bumps an urgent test of the department to the earliest slot on a machine fit to run it, with a reason. Bookings in that slot that have not started go back to the queue and are planned again; a running booking is never interrupted, so the bumped test starts when it ends. |
| Deadline risk       | The head is told when a test of the department becomes at risk of missing its due date, and can list the department's tests at risk from the queue and the schedules. |
| Late after bumping  | Before bumping, the head sees the tests the bump would make miss their due date, and chooses for them: let them run after their due date, outsource them straight away, or not bump. |

Acceptance criteria:

- A testing task in the department queue disappears from the queue once assigned, and appears in the assignee's to-do list.
- Assigning a sample assigns all of its testing tasks in the department to the chosen person.
- Reassigning a task to another person or department without a reason is refused; the reason is kept on the task.
- A head of department sees the bookings of their department's people and machines, not those of other departments.
- A test that no machine can finish before its due date shows an outsourcing suggestion.
- Bumping an urgent test gives it the earliest slot on a fit machine; the bookings it moves are planned again and their people are notified.
- Bumping a test that is not urgent, or bumping without a reason, is refused.
- A running booking is not moved by a bump.
- A bump that would make other tests miss their due date is not done until the head chooses what happens to them.
- A test of the department that becomes at risk notifies the head once and appears in the list of tests at risk.

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
- A result sent with a sanity warning shows the warning to the head who approves it.
- Cancelling a sample test without a reason is refused; a cancelled test does not appear on the report.
- A sample whose remaining tests are all approved is completed even if others were cancelled.

### 3. Outsourcing (US-HD10, US-HD11, US-HD13)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and the [subcontractor rules](admin.md#3-subcontractors-us-ad12).

| Rule        | Description                                                                                                                 |
| ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| Accept      | Accepting a suggestion marks its sample tests as outsourced through the suggested subcontracted way of testing, or another of the parameter's subcontracted ways the head chooses, and puts them in the subcontractor's draft dispatch. |
| Dispatch    | Outsourced sample tests for one subcontractor go in a dispatch: date sent, date results are expected back, and sample delivery staff (nhân viên giao nhận mẫu) or a delivery service with its tracking number. |
| Accreditation | A subcontractor whose accreditation has expired cannot be chosen.                                                          |
| Emergency   | The head outsources a waiting or assigned test of the department straight away, with a reason, through one of the parameter's subcontracted ways of testing. Its bookings that have not started are cancelled, and it goes in the subcontractor's draft dispatch as an accepted suggestion does. |

Acceptance criteria:

- Accepting an outsourcing suggestion sets its sample tests to outsourced.
- A sent dispatch appears on the outsourcing schedule with its expected date.
- A dispatch records either the sample delivery staff who took it or the delivery service and tracking number.
- Outsourcing a test straight away without a reason is refused; a test already in testing cannot be outsourced straight away.

### 4. Laboratory files (US-HD15, US-HD16)

Follows [Laboratory files](../overview.md#laboratory-files).

| Rule          | Description |
| ------------- | ----------- |
| Sample folders | Creating a sample's folders adds the raw-data and result folders it does not have yet, owned by the person who creates them, syncing every file upload-only; the owner adds the members. |
| Signing       | A version of a result file is signed through the approval chain of laboratory files; the signature belongs to that version and its hash. |

Acceptance criteria:

- Creating a sample's folders twice adds no second folder of the same category.
- Signing a file version records the signer, the version and its hash; a newer version of the file shows as not signed.
- Rejecting a version without a reason is refused.

### 5. Mobile (US-HD17)

Follows [Medilab Mobile](../applications/medilab-mobile.md#tasks-and-notifications-sh-10-sh-11-us-hd17).

| Rule    | Description |
| ------- | ----------- |
| Tasks   | The head assigns their department's waiting tasks and reassigns them with a reason on the phone, as in the department's queue on the web. |
| Results | The head signs or rejects their department's results on the phone at their level of the approval chain, following [Samples and results](#2-samples-and-results-us-hd06-to-us-hd09). |

Acceptance criteria:

- Rejecting a result on the phone without a reason is refused.
- A head cannot approve on the phone a result they entered.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Tester](tester.md)
- [Sample delivery staff](sample-delivery-staff.md)
- [Lab head](lab-head.md)
