# Features of: Tester

The tester, also called lab QA, runs assigned tests with a machine when the way of testing requires one. Lab QA is an alias for Tester, not a separate quality-assurance role. Testers see samples only by their lab code, never the customer or the customer's name for the sample.

## I. User stories

### Planning

- **US-T01** As a tester, I want to see my testing tasks in my to-do list, soonest deadline first, and claim unassigned testing tasks of my department, so that I work on what is due first.
- **US-T02** As a tester, I want to schedule a run of the agreed way of testing from the recommended resources and slot, so that it finishes before its due date.
- **US-T03** As a tester, I want to move or cancel my booking, so that my schedule matches what I can do.
- **US-T04** As a tester, I want to be reminded before a booking starts, so that I am ready to start on time.
- **US-T19** As a tester, I want to mark one of my tests urgent with a reason, so that a sample I know must come first is scheduled first even when its due date is not close.
- **US-T20** As a tester, I want to be warned when one of my tests is at risk of missing its due date, so that I can ask for help in time.
- **US-T21** As a tester, I want to be warned when the machine of my booking is due for calibration or maintenance soon or was repaired recently, so that I check it before I test.

### Results

- **US-T05** As a tester, I want to enter a result as a number in the unit of the way of testing or as a text, so that the measurement is recorded as it was made.
- **US-T06** As a tester, I want to assess requested regulation comparisons as pass, fail or insufficient basis, so that the report states only what its evidence supports.
- **US-T07** As a tester, I want to send my result for approval and sign it, so that the head of department can review it.
- **US-T08** As a tester, I want to retest when a result is rejected, so that the reported result is correct, while the rejected one stays on record.
- **US-T09** As a tester, I want to enter the results a subcontractor sends back for an outsourced test, so that they reach the report when the subcontractor does not enter them itself.
- **US-T17** As a tester, I want to see the steps of the testing method of my test, each with how long it takes, what to do and its note, so that I run the test the way the laboratory defines it.
- **US-T18** As a tester, I want to see where my sample was taken from and where each step of my test is done, so that I know where to go to get what I need.
- **US-T22** As a tester, I want to be warned before sending a result that is unusual for its parameter and sample type or close to the regulation limit, so that I check it before it goes for approval.

### Samples

- **US-T10** As a tester, I want to be reminded of samples whose retention ends soon and record their disposal, so that no sample is kept longer than needed.

### Corrections

- **US-T11** As a tester, I want to raise a change request on a result whose process is completed, stating what to change and why, so that a mistake is corrected as a new version.

### Laboratory files

- **US-T23** As a tester, I want a folder on my computer to stay in step with a laboratory folder, so that the files I save reach MediLab without uploading them by hand.
- **US-T24** As a tester, I want to see every version of a file with who saved it, from which computer and when, and restore an earlier one, so that no work is lost.
- **US-T25** As a tester, I want a file someone else changed while I changed it to be kept as a conflict instead of overwritten, so that I can choose which version to keep.
- **US-T26** As a tester, I want to edit a result spreadsheet or document together with colleagues in the browser, so that we do not send copies around.
- **US-T27** As a tester, I want to lock a working or result file that is not an Office document while I edit it, so that nobody changes it meanwhile.
- **US-T28** As a tester, I want to share a folder I own with colleagues, so that we work on the same files.
- **US-T29** As a tester, I want to browse and download the files of my samples in the back office, so that I can reach them from any computer.

## II. Feature details

### 1. Planning (US-T01 to US-T04, US-T19 to US-T21)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling), [SH-10](../../shared.md#sh-10-tasks-and-to-do-list) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Claiming | A tester may claim an unassigned testing task of their department only when the Lab Head's authorization list includes its parameter. There are no team queues and no authorization validity dates. A task someone else claimed first cannot be claimed. |
| Recommendation | Recommend resources and a slot for a run of the already agreed way, with its explicit sample-type applicability; do not select a different method or performing party. |
| Booking | A run has one person, one way, one time interval and a machine only if needed. It may combine attempts from several samples and requests within the configured capacity. Reserve the tester and required locations as well as the machine. Queued work is planned urgent first, then first in, first out. |
| Marking urgent | The tester marks a test of their own testing task urgent, stating why, or removes the mark. A marked test is urgent whatever its due date. |
| Deadline risk | Notify the tester and Head of Department when risk first appears, then include unresolved risks in a daily summary. Show the flag on tasks and schedules. Sales contacts the customer only when the promised return date is affected or at risk. |
| Machine heads-up | Warn within the separate calibration, maintenance or recent-repair windows, each defaulting to 7 days. Valid warnings allow booking only while calibration, maintenance and availability requirements are satisfied. |
| Adjusting      | Moving or cancelling a booking puts its slot back in the queue.                                                          |

Acceptance criteria:

- A run appears on the tester's schedule and to-do list and on the schedules of its required resources; a no-machine run is schedulable without a machine.
- Claiming a task assigns it to the tester; a second tester claiming it at the same time is told it is already claimed.
- A tester cannot claim a task of another department.
- A reminder arrives before the booking starts.
- Planning checks that the tester, every required location and a machine when required are available; an unavailable room blocks a no-machine run too.
- Moving a booking moves the room bookings of its steps with it.
- Marking a queued test urgent without a reason is refused; once marked, it gets the next free slot before tests that are not urgent, and the reason shows on the test.
- A tester cannot mark urgent a test of a task assigned to someone else.
- A test whose booking ends after its due date is flagged, sends an initial notice and remains in daily risk summaries until resolved.
- A tester not authorized for its parameter cannot claim or be scheduled for the test.
- A run exceeding the configured capacity cannot be scheduled.
- A booking that ended without a result makes its test at risk; entering the result, or a booking that finishes before the due date, clears it.
- A currently valid calibration due within the warning window shows its date; booking proceeds only if all other maintenance and resource conditions hold.
- A machine with a repair recorded within the warning days shows a warning naming the repair.
- A tester sees the lab code of a sample, not its customer or the customer's name for it.

### 2. Results (US-T05 to US-T09, US-T17, US-T18, US-T22)

Follows [Results](../overview.md#results) and [Signing](../overview.md#signing).

| Rule        | Description                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| Limit copy | Creating an attempt copies its unit, LOD and LOQ from its way and sample type. If comparison is requested, copy the exact regulation, parameter and sample-type limit and unit; missing configuration remains visible. |
| Measurement | Each attempt belongs to exactly one run or subcontract dispatch. Its run supplies the performer, interval and machine when required; entering one attempt's result does not complete every other attempt in a shared run. |
| Conclusion | No conclusion is needed without requested regulation comparison. For a requested comparison, the tester assesses pass, fail or insufficient basis. Text and below-LOD/LOQ values need professional assessment, never automatic passing or substitution with zero. Reports show the threshold and unit from the attempt's snapshot. |
| Retest | A retest is a new attempt in a new run; earlier attempts and the link to an interrupted run are retained. |
| Sanity check | Before a numeric result is sent for approval, it is compared with past approved results and the regulation limit. An unusual value shows a warning with the reason; the tester may still send it, and the warning stays on the result. |
| Task done   | The testing task is done when the reported result is approved.                                       |
| Outsourced  | The results of an outsourced test are entered by the subcontractor or by a lab QA; each result records who entered it. |
| Method steps | A tester sees the steps of the testing method of the way of testing chosen for their sample test, in step number order, from the testing task and the booking. They only read them; the administrator maintains them ([Administrator](admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28)). |

Acceptance criteria:

- A result identifies its run or subcontract dispatch, never both; a no-machine run has no machine.
- A below-LOQ result preserves the raw number if available and prints the copied threshold and unit after tester confirmation.
- Catalog changes do not rewrite an existing attempt's unit, LOD or LOQ.
- A requested comparison shows its exact copied limit or missing basis; insufficient basis does not force pass/fail. A result outside comparison scope is sent without a conclusion.
- A numeric result far from the approved results of the same parameter, way of testing and sample type shows a warning before it is sent; sending it anyway keeps the warning on the result.
- A numeric result within the margin of the regulation limit shows a warning.
- With fewer approved results than the minimum to compare, only the limit check runs; a text result is not checked.
- The warning never names a customer or shows another customer's sample.
- A tester opening a testing task sees the steps of its method with their number, duration, what to do and note, in step number order; a method without steps shows none.
- A step with a location shows that location's code and name to the tester.
- A testing task whose sample names a location shows that location on the task, the schedule, the to-do list and the timeline, and opening it shows it marked on its parent location's map.
- A tester cannot change a step.
- A rejected result stays on record, and the sample test goes back to testing.
- Approving the reported result closes the tester's testing task.

### 3. Samples (US-T10)

Follows [Reception](../overview.md#reception).

| Rule     | Description                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| Disposal | A sample is disposed of once it is not kept, its retention period is over or its request is cancelled. The method is the one entered on the sample, or else its sample type's disposal method. Disposal cannot be undone. |
| Reminder | A daily job gives testers a to-do listing samples whose retention ends within the reminder days, a system parameter (7 by default), or has ended. Running it again does not add a second to-do for the same sample. |

Acceptance criteria:

- Disposing of a sample with no method on it and none on its sample type is refused.
- A disposed sample cannot be disposed of again or changed back.
- A sample whose retention ends in 3 days appears on the reminder; a disposed one does not.

### 4. Corrections (US-T11)

Follows [Reports and change requests](../overview.md#reports-and-change-requests) and [SH-07](../../shared.md#sh-07-signed-documents-are-locked).

| Rule           | Description                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------- |
| Change request | A tester or head who can edit results raises a change request on a completed result with what to change and why. Once its chain approves it, a new unsigned version of the result replaces the old one and is signed again; the old version is kept. |
| Issued report | A correction to a reported result automatically links or creates its report's change request, without duplicating an open request. A replacement report waits for the required approvals and approval of all corrected results, then needs a fresh Lab Head signature before issue. |
| Pending signature | A correction may be proposed while a report waits for signature. Before applying it, stop the old signing task and return the report to draft. Approved results retain their own change-request requirement. Rebuild the report and create a fresh task after the corrected results are approved, for initial and replacement reports alike. |

Acceptance criteria:

- A change request without what to change or why is refused.
- Correcting an issued result links one open report correction and never releases an unsigned replacement.
- An old signing task cannot sign a report whose results are being corrected.
- An approved change request on a result creates a new version linked to the old one, which stays readable and is marked as replaced.

### 5. Laboratory files (US-T23 to US-T29)

Follows [Laboratory files](../overview.md#laboratory-files) and [Medilab Sync](../applications/medilab-sync.md).

| Rule        | Description |
| ----------- | ----------- |
| Syncing     | Medilab Sync uploads every saved file of a bound local folder that matches the folder's sync rules, and in two-way folders downloads the new current versions others saved. |
| History     | Every version stays readable and downloadable; restoring one adds a new current version. |
| Conflicts   | A conflict keeps both versions; the tester keeps their own file or takes the server's in Medilab Sync. |
| Editing     | Office result and working files open in the browser editor; raw-data files never do. |
| Sharing     | The owner of a folder adds and removes its members; a member cannot leave a folder, only stop syncing it on their computer. |

Acceptance criteria:

- Saving a file in a bound local folder adds a version on the server with the tester, the computer, the size and the hash.
- A file that does not match the folder's sync rules is not uploaded.
- A file uploaded from version 10 while the server holds version 11 is kept as a conflict version, and version 11 stays current.
- Restoring version 3 of a file with 5 versions adds version 6 with the content of version 3.
- Uploading content the file already has stores no second copy of the bytes.
- No one can change or delete a version, its hash or its size.
- Saving in the online editor adds a version marked as edited online; a second person opening the file joins the same session.
- A raw-data file cannot be opened in the online editor or locked.
- Uploading a file someone else has locked is refused.
- A tester who is not a member of a folder, or cannot see its sample, gets nothing from it.
- Removing a member stops their uploads to the folder at once, and the files on their computer stay.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
