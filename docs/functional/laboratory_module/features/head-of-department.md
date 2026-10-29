# Features of: Head of department

The head of department runs the testing work of one department: they assign its tasks, manage its schedule, decide on outsourcing, approve its results and handle samples that arrive insufficient. A head of department also has every feature of a [tester](tester.md).

## I. User stories

### Work and schedule

- **US-HD01** As a head of department, I want to see my department's queue of testing tasks with their due dates, so that nothing waits unnoticed.
- **US-HD02** As a head of department, I want to assign a sample's testing tasks, or a single task, to a person in my department, and reassign them with a reason, so that every test has someone responsible.
- **US-HD03** As a head of department, I want to see my department's machine schedules and the people's schedules, so that I can balance the work.
- **US-HD04** As a head of department, I want to move or cancel a booking of someone in my department, so that I can handle absences and incidents.
- **US-HD05** As a head of department, I want to see the scheduler's outsourcing suggestions for tests that cannot finish in time in-house, so that they still meet their due date.
- **US-HD12** As a head of department, I want urgent work to get the earliest feasible slot through a plan revision I approve for my department, moving bookings that have not started out of its way, so that a sample needed right away is tested right away.
- **US-HD14** As a head of department, I want to see my department's tests at risk of missing their due date, so that I can move work, free capacity or outsource in time.

### Samples and results

- **US-HD06** As a head of department, I want my department to record that it received a sample handed over to it by scanning the sample's label, so that the handover is on record.
- **US-HD07** As a head of department, I want to ask for an insufficient sample to be collected again, so that its tests can go ahead.
- **US-HD08** As a head of department, I want to approve or reject the results of my department with a reason, so that only checked results reach the report.
- **US-HD09** As a head of department, I want to cancel a sample test of my department with a reason, so that a test that cannot be done does not hold up the report.

### Outsourcing

- **US-HD10** As a head of department, I want to accept an outsourcing suggestion and put its sample tests in a dispatch to the subcontractor, so that tests that cannot finish in time in-house still meet their due date.
- **US-HD11** As a head of department, I want to record when a dispatch is sent, who or which delivery service takes it, and when its results are expected back, so that the outsourcing schedule shows where every outsourced test is.
- **US-HD13** As a head of department, I want to outsource a test of my department straight away with a reason, without waiting for an outsourcing suggestion, so that an emergency is handled when required in-house resources cannot meet the date.

### Laboratory files

- **US-HD15** As a head of department, I want to create the raw-data and result folders of a sample, so that its testers save their files in the right place.
- **US-HD16** As a head of department, I want to sign or reject a version of a result file with a reason, so that the file a report relies on is approved.

### Mobile

- **US-HD17** As a head of department, I want to assign my department's tasks and sign or reject its results on my phone, so that work and results do not wait while I am away from my desk.

### Testing figures

- **US-HD18** As a head of department, I want testing figures for my department over a period, so that I can review turnaround, overdue work, retests and workload.

## II. Feature details

### 1. Work and schedule (US-HD01 to US-HD05, US-HD12, US-HD14)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling), [Scheduling](../../../specs/scheduling.md) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule                | Description                                                                                                             |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Queue | Testing tasks queue by department. The head assigns them or an authorized tester claims them; team membership does not create a separate testing queue. |
| Assignment | The head assigns a sample's department tasks or one task to a person authorized by the Lab Head for each parameter. The department's plan proposes a booking for the agreed way. Reassignment to another person or department requires a reason. |
| Adjusting | The head moves or cancels not-started bookings of the department. Changes synchronize its tester, machine when needed and required location reservations; cancelling returns its sample test to the plan without cancelling it. A booking the head places or moves by hand is pinned: plan revisions do not move it and report a conflict instead. |
| Marking urgent      | The head can mark any test of the department urgent, stating why, or remove the mark, as the tester does ([US-T19](tester.md#1-planning-us-t01-to-us-t04-us-t19-to-us-t21)). |
| Outsourcing | The scheduler suggests viable subcontracted ways when in-house resources cannot meet the due date. The head reviews them; changing an accepted way requires a revised quotation and customer agreement through Sales. |
| Plan revisions | A recalculation that moves scheduled bookings, such as when urgent work needs a slot others hold, is a plan revision. It lists every moved booking with its new slot, internal due date and committed return date, and the head approves the moves in the department. A move whose planned finish passes its internal due date would miss a committed return date: it is held back, and its booking keeps its slot, until Sales records the customer's agreement to a new date; the other moves are recalculated without it and can be applied. A running booking is never moved. |
| Deadline risk | Notify the head initially and in a daily consolidated summary while a risk remains. The queue and schedules show affected tests. Sales informs the customer when the committed return date is affected or at risk. |
| Freeing capacity | Instead of waiting for a customer's agreement, the head may free capacity, such as with planned OverTime or another machine linked to the same method, and recalculate, or pursue an agreed outsourcing alternative. Any change to an accepted way still needs a revised quotation and customer agreement. |
| Due date override | The head may change an internal due date with a reason. Preserve the override when the committed return date changes, recalculate only automatic dates and report conflicts. Feasibility checks only read: they use the company calendar and holidays, give reasons and the earliest feasible date, and reserve or move no bookings. An infeasible internal date may be kept with a reason and risk flag; it implies no reserved resources. |
| Outside working hours | The head records planned OverTime for a tester, an outside-hours interval and a reason, without an HR overtime shift; the tester can then be booked in that interval. The scheduler never creates, moves or recalculates OverTime: moving or cancelling a booking leaves it for the head to change. OverTime extends only the tester's availability; machines and locations keep their own. Actual overtime and payroll are outside scope. |
| Disruption | Downtime, an unavailable room or approved leave returns affected not-started bookings to the plan and notifies the head for reassignment or authorized claiming. Replan only on another machine linked to the same method. A machine that breaks down or loses calibration during a booking ends it; the head assesses the interrupted result as usable, needing a retest or needing more sample. A retest is a new result with a new booking. |

Acceptance criteria:

- A testing task in the department queue disappears from the queue once assigned, and appears in the assignee's to-do list.
- Assigning a sample assigns all of its testing tasks in the department to the chosen person.
- Reassigning a task to another person or department without a reason is refused; the reason is kept on the task.
- A head of department sees the bookings of their department's people and machines, not those of other departments.
- A test whose required in-house resources cannot meet its due date shows viable outsourcing alternatives; a way that needs no machine is checked against its tester and required locations.
- A plan revision for urgent work proposes it in the earliest feasible slot and lists the bookings it moves with their new slots; their people are notified once it is applied.
- A head approves only the moves of their own department in a plan revision.
- A running booking is not moved by a plan revision.
- A move whose planned finish passes its internal due date is held back, and its booking keeps its slot, until Sales records the customer's agreement to a new date.
- A booking the head moved by hand stays where it is when the plan is recalculated, and the conflict is reported.
- A risk sends an initial notice and remains in daily consolidated summaries until resolved.
- A manual due-date override survives a customer-date change; automatic dates are recalculated.
- A tester can be booked outside normal hours only within planned OverTime the head recorded; moving that booking leaves the OverTime unchanged.
- Approving leave returns overlapping not-started bookings to the plan without assigning another tester.
- A non-working day is reported according to the company calendar; a public holiday the administrator marked as a working day is accepted.
- A feasible date is accepted when a free slot exists, or simulated moves can make room without missing other tests' due dates; checking the date moves no bookings.
- A date with no feasible slot is reported with reasons and the earliest feasible date. Keeping it requires the head's reason and a visible risk flag.

### 2. Samples and results (US-HD06 to US-HD09)

Follows [Reception](../overview.md#reception), [Results](../overview.md#results) and the [approval and signing chain](../../../business/approval-and-signing-chain.md).

| Rule          | Description                                                                                                  |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| Handover | A person of the department records when and by whom it received a sample by scanning its label through the web interface. |
| Collect again | Asking for an insufficient sample to be collected again schedules a sample collection task for sample delivery staff. |
| Approval | The head signs or rejects results at the result approval level, recording a rejection reason. They may approve a result they entered, including when they are the department's only result signer. The Lab Head reviews the approved results and signs the report before issue. |
| Cancelling    | The head cancels a sample test of the department that has no approved result, with a reason. Its testing task and its own booking end, and the report leaves it out. Bookings sharing its machine interval continue unchanged. |

Acceptance criteria:

- Scanning a sample's label records the handover for the scanner's department; a person outside the department is refused.
- Asking for a sample to be collected again creates a sample collection task and records who asked and when.
- Rejecting a result sends its sample test back to testing, opens a new testing task for it and tells the tester the reason.
- Once every result of a sample is approved, the sample is completed.
- A head can explicitly approve a result they entered; it still needs the Lab Head's report signature before issue.
- A result sent with a sanity warning shows the warning to the head who approves it.
- Cancelling a sample test without a reason is refused; a cancelled test does not appear on the report.
- A sample whose remaining tests are all approved is completed even if others were cancelled.

### 3. Outsourcing (US-HD10, US-HD11, US-HD13)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and the [subcontractor rules](admin.md#3-subcontractors-us-ad12).

| Rule        | Description                                                                                                                 |
| ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| Accept | Accept an outsourcing suggestion only for the agreed subcontracted way. If it changes an accepted selection, Sales first obtains customer agreement through a revised quotation. The head then puts its sample tests in the subcontractor's draft dispatch. |
| Dispatch | A dispatch holds one subcontractor, sending and due dates, the sample tests sent, the subcontractor's report, and sample delivery staff or a delivery service and tracking number. The way's turnaround includes transport and processing. |
| Accreditation | A subcontractor whose accreditation has expired cannot be chosen.                                                          |
| Emergency | The head may initiate outsourcing for a waiting or assigned test with a reason, without waiting for a scheduler suggestion. Only the department testing a test with no suggestion sees the emergency action, and its reason is shown on the test. Changing an accepted way still requires Sales and customer agreement on a revised quotation. Once agreed, cancel not-started bookings and put its sample tests in a draft dispatch. |

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
- A head may approve their own result on the phone, as on the web; the Lab Head reviews it when signing the final report.

### 6. Testing figures (US-HD18)

| Rule | Description |
| --- | --- |
| Department figures | For the chosen period show completed sample tests, the share completed on time, average receipt-to-approval time, overdue sample tests, retests and workload per person. The head sees their department; the Lab Head sees all departments. |

Acceptance criteria:

- Department filtering applies to all six measures and the underlying records.
- The Lab Head can compare the same period across departments.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Tester](tester.md)
- [Sample delivery staff](sample-delivery-staff.md)
- [Lab head](lab-head.md)
