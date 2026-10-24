# Features of: Tester

The tester, also called lab QA, runs the tests assigned to them on the laboratory's machines. Testers see samples only by their lab code, never the customer or the customer's name for the sample.

## I. User stories

### Planning

- **US-T01** As a tester, I want to see my testing tasks in my to-do list, soonest deadline first, and claim unassigned testing tasks of my department, so that I work on what is due first.
- **US-T02** As a tester, I want to schedule a test from the scheduler's recommendation of way of testing, machine and slot, so that it finishes before its due date.
- **US-T03** As a tester, I want to move or cancel my booking, so that my schedule matches what I can do.
- **US-T04** As a tester, I want to be reminded before a booking starts, so that I am at the machine on time.
- **US-T19** As a tester, I want to mark one of my tests urgent with a reason, so that a sample I know must come first is scheduled first even when its due date is not close.
- **US-T20** As a tester, I want to be warned when one of my tests is at risk of missing its due date, so that I can ask for help in time.
- **US-T21** As a tester, I want to be warned when the machine of my booking is due for calibration or maintenance soon or was repaired recently, so that I check it before I test.

### Results

- **US-T05** As a tester, I want to enter a result as a number in the unit of the way of testing or as a text, so that the measurement is recorded as it was made.
- **US-T06** As a tester, I want to set a result's conclusion, pass or fail, against the sample's regulation, so that the report states whether the sample complies.
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

### Mobile

- **US-T30** As a tester, I want to do my testing tasks on my phone at the bench: claim them by scanning the sample's label, follow the method's steps, and enter, send and sign the result, so that I do not go back to a computer between steps.

## II. Feature details

### 1. Planning (US-T01 to US-T04, US-T19 to US-T21)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling), [SH-10](../../shared.md#sh-10-tasks-and-to-do-list) and [SH-11](../../shared.md#sh-11-schedules-and-reminders).

| Rule           | Description                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Claiming       | A tester sees the unassigned testing tasks of their department and can claim one; a task someone else claimed first cannot be claimed. |
| Recommendation | When a task is assigned to the tester, the scheduler recommends the way of testing and machine that finish it soonest within its due date. |
| Booking        | Scheduling takes the next free slot in the machine's queue: urgent tests first, then first in, first out.                |
| Marking urgent | The tester marks a test of their own testing task urgent, stating why, or removes the mark. A marked test is urgent whatever its due date. |
| Deadline risk  | The tester is told when one of their tests becomes at risk of missing its due date, and sees it marked at risk on the task, the to-do list and the schedule. |
| Machine heads-up | Scheduling or starting a booking on a machine due for calibration or maintenance soon, or repaired recently, shows a warning naming what is due or what was repaired; the booking goes ahead. |
| Adjusting      | Moving or cancelling a booking puts its slot back in the queue.                                                          |

Acceptance criteria:

- A scheduled booking appears on the tester's personal schedule, on the machine's schedule and in the tester's to-do list.
- Claiming a task assigns it to the tester; a second tester claiming it at the same time is told it is already claimed.
- A tester cannot claim a task of another department.
- A reminder arrives before the booking starts.
- A test whose method has a step in a bookable room is planned only at a time when the machine and the room are both free, and the room's booking shows on the tester's calendar and the room's schedule.
- Moving a booking moves the room bookings of its steps with it.
- Marking a queued test urgent without a reason is refused; once marked, it gets the next free slot before tests that are not urgent, and the reason shows on the test.
- A tester cannot mark urgent a test of a task assigned to someone else.
- A test whose scheduled booking ends after its due date shows as at risk, and its tester is told once.
- A booking that ended without a result makes its test at risk; entering the result, or a booking that finishes before the due date, clears it.
- Scheduling a booking on a machine whose calibration is due within the warning days shows a warning with the calibration date, and the booking is still made.
- A machine with a repair recorded within the warning days shows a warning naming the repair.
- A tester sees the lab code of a sample, not its customer or the customer's name for it.

### 2. Results (US-T05 to US-T09, US-T17, US-T18, US-T22)

Follows [Results](../overview.md#results) and [Signing](../overview.md#signing).

| Rule        | Description                                                                                          |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| Limit copy  | A result copies the sample's regulation limit for its parameter, with its unit, when it is created.   |
| Measurement | A result takes the machine and start time from its booking; the tester can correct them. Entering the result marks the measurement done. |
| Conclusion  | The tester sets pass or fail when the sample has a regulation.                                       |
| Retest      | A retest adds a result; the earlier one is kept.                                                     |
| Sanity check | Before a numeric result is sent for approval, it is compared with past approved results and the regulation limit. An unusual value shows a warning with the reason; the tester may still send it, and the warning stays on the result. |
| Task done   | The testing task is done when the reported result is approved.                                       |
| Outsourced  | The results of an outsourced test are entered by the subcontractor or by a lab QA; each result records who entered it. |
| Method steps | A tester sees the steps of the testing method of the way of testing chosen for their sample test, in step number order, from the testing task and the booking. They only read them; the administrator maintains them ([Administrator](admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28)). |

Acceptance criteria:

- A result entered for a booked test shows the booking's machine and start time, and the tester can correct them.
- A result entered on a sample with a regulation shows the copied limit and needs a conclusion before it is sent for approval.
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

Acceptance criteria:

- A change request without what to change or why is refused.
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

### 6. Mobile (US-T30)

Follows [Medilab Mobile](../applications/medilab-mobile.md#testing-at-the-bench-us-t30-us-hd17).

| Rule     | Description |
| -------- | ----------- |
| Claiming | Scanning a sample's label lists the unassigned testing tasks of the tester's department on it; the tester claims one or more. |
| Results  | Entering, sending and signing a result on the phone follow the [Results](#2-results-us-t05-to-us-t09-us-t17-us-t18-us-t22) rules. |

Acceptance criteria:

- Scanning the label of a sample offers none of the testing tasks of another department.
- A result entered and signed on the phone shows on the web waiting for the head of department, with the tester's signature.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Shared technical features](../../shared.md)
