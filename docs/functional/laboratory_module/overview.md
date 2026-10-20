# Laboratory Module Overview

The Laboratory module is the core of MediLab. It holds the master data, the test requests, the samples and their results, and the signing that approves them. E-commerce and Inventory depend on it; it depends on no other MediLab module. It builds on Odoo's Employees, Calendar, Discuss and portal, as listed in [Module boundaries](../../business/module-boundaries.md#odoo-apps). The tables are drawn in [laboratory.prisma](../../infrastructure/database/laboratory/laboratory.prisma).

## Core entities

The module is built around two entities:

- **Sample**: the material someone holds in their hand. A sample has a sample type (nền mẫu).
- **Test parameter**: what the laboratory does to the sample. A parameter belongs to parameter groups (nhóm chỉ tiêu).

A parameter has N testing methods, and a sample has N parameters.

```mermaid
erDiagram
    TEST_REQUEST ||--|{ SAMPLE : has
    SAMPLE }o--|| SAMPLE_TYPE : "is of"
    SAMPLE ||--|{ SAMPLE_TEST : "is tested for"
    SAMPLE_TEST }o--|| TEST_PARAMETER : tests
    SAMPLE_TEST }o--o| PARAMETER_METHOD : "is tested by"
    TEST_PARAMETER ||--|{ PARAMETER_METHOD : "is tested by"
    PARAMETER_METHOD }o--|| TESTING_METHOD : uses
    TESTING_METHOD ||--o{ TESTING_METHOD_STEP : "is done in"
    LOCATION ||--o{ LOCATION : contains
    TESTING_METHOD_STEP }o--o| LOCATION : "is done in"
    SAMPLE }o--o| LOCATION : "is taken from"
    ACCREDITATION_CERTIFICATE }o--o{ TESTING_METHOD : covers
    SAMPLE_TEST ||--o{ TEST_RESULT : "is measured in"
```

## Test requests and samples

| Rule              | Description                                                                                                                                  |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Customer          | A customer is a company or an individual. Their details are their contact; a company's people are the contact's people. A customer has a code from a sequence, the tax ID on its contact, and a citizen ID for an individual, which is masked in the audit trail. People who use the customer portal sign in with Odoo users linked to those contacts. Sales maintains customers. |
| Test request      | A test request groups the samples of one customer. E-commerce creates it from a confirmed order, with the samples sales defined on the quotation; without E-commerce, sample delivery staff create it with its samples and parameters. Confirming it needs at least one sample, and each sample at least one parameter. |
| Lab code          | Each sample gets a unique lab code (mã PTN) from a sequence, such as PTN.2026.0001, numbered again each year. Testers see only the lab code, never the customer or the customer's name for the sample: only people who can read test requests see those. |
| Sample details    | A sample has the customer's name for it, its sample type, its physical state (solid, liquid, gas or semi-solid), and its form and container as text. It can name the [location](features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28) it was taken from, such as a sampling point. |
| Regulation        | A sample can name the regulation its results are compared with.                                                                               |
| Sample test       | Each parameter tested on a sample is a sample test, with a quantity and a due date. The way of testing is chosen later by the laboratory, helped by the scheduling system, and must be a way of testing that parameter. |

## Lifecycles

Each document keeps its own status. Tasks keep their own generic lifecycle ([SH-10](../shared.md#sh-10-tasks-and-to-do-list)).

### Test request

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> confirmed: request confirmed
    confirmed --> paid: payment received or customer allowed credit
    confirmed --> sample_received: no payment step
    paid --> sample_received: first sample received
    sample_received --> testing: first sample test started
    testing --> awaiting_approval: every sample test has a result entered
    awaiting_approval --> testing: a result is rejected
    awaiting_approval --> completed: every result approved
    testing --> completed: the remaining tests are approved when one is cancelled
    completed --> reported: report issued
    completed --> testing: the lab head sends results back
    draft --> cancelled
    confirmed --> cancelled
    paid --> cancelled
    sample_received --> cancelled
    testing --> cancelled
```

- Only the request of an order goes through the paid step, which E-commerce sets. A request sample delivery staff create goes straight from confirmed to sample received.

### Sample

```mermaid
stateDiagram-v2
    [*] --> expected
    expected --> received: sample received
    received --> rejected: unusable on arrival
    received --> on_hold: insufficient on arrival
    on_hold --> received: more sample collected
    received --> testing: first sample test started
    testing --> awaiting_approval: every sample test has a result entered
    awaiting_approval --> testing: a result is rejected
    awaiting_approval --> completed: every result approved
    testing --> completed: the remaining tests are approved when one is cancelled
    completed --> reported: report issued
    completed --> testing: the lab head sends one of its results back
    reported --> retained: kept after testing
    reported --> disposed: not kept
    retained --> disposed: retention period over
    cancelled --> disposed: request cancelled
    expected --> cancelled
    received --> cancelled
    testing --> cancelled
```

### Sample test

```mermaid
stateDiagram-v2
    [*] --> waiting
    waiting --> assigned: assigned to a person
    assigned --> waiting: put back in the department queue
    waiting --> outsourced: sent to a subcontractor
    assigned --> outsourced: sent to a subcontractor
    assigned --> testing: test started
    waiting --> testing: test started before it is assigned
    testing --> result_entered: result entered and sent for approval
    outsourced --> result_entered: subcontractor's result sent for approval
    result_entered --> outsourced: outsourced result rejected or withdrawn
    result_entered --> testing: result rejected or withdrawn
    result_entered --> approved: result approved
    approved --> testing: the lab head sends its result back
    waiting --> cancelled
    assigned --> cancelled
    testing --> cancelled
```

### Test report

```mermaid
stateDiagram-v2
    [*] --> draft: every sample test of the request approved or cancelled
    draft --> signing: a level of a longer chain signs
    draft --> issued: the last level signs
    signing --> issued: the last level signs
    signing --> draft: a signature is withdrawn or the report is rejected
    issued --> replaced: a change request creates a new version
```

- A rejected report stays in draft until the results sent back are approved again; its request is then completed again and the lab head gets a new signing task.

## Reception

| Rule            | Description                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Receipt         | When a sample arrives, the laboratory records when and by whom it was received, the amount received, its condition (good, damaged or insufficient) with a note, and where it is stored. |
| Label           | Each sample has a label printed by sample delivery staff, showing its lab code, its test request's code, the date results are due and a QR code of the lab code. It never shows the customer or the customer's name for the sample. |
| Photos          | Sample delivery staff attach photos of a sample when they collect or receive it, on the web or the mobile app. Photos are shown wherever the customer's name for the sample is shown, so testers never see them. |
| Handover record | When a customer hands samples over, sample delivery staff fill in a handover record (biên bản giao nhận mẫu) listing each sample with the amount and condition handed over. The customer signs it by hand on the mobile app, and the signed PDF is emailed to the customer. A signed record is never edited; a correction is a new record and the old one is kept. |
| Rejection       | A sample that cannot be tested on arrival is rejected with its condition note.                                                         |
| Insufficient    | A sample that arrives insufficient is put on hold and reported to the head of department, who asks for it to be collected again. The request schedules a sample collection task for sample delivery staff. The sample goes back to received when more sample arrives. |
| Retention       | A sample kept after testing is retained until the report date plus its sample type's retention days. |
| Disposal        | A tester disposes of a sample that is not kept, whose retention period is over, or whose request was cancelled. Disposal records when, by whom and how; the method is the one entered on the sample, or else its sample type's disposal method, and is required. Disposal cannot be undone. Every day, testers get a to-do listing the samples whose retention ends within the reminder days, a system parameter (7 by default), or has ended, and that are not disposed of yet. |
| Handover        | A received sample is handed over to each department that tests it. A person of that department records when and by whom it was received by scanning the sample's label, on the web or the mobile app; a person outside the department is refused. |

## Results

| Rule            | Description                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Attempts        | Every measurement of a sample test is its own result. Retests add a result; earlier results are kept. One result per sample test is the reported one: the latest entered, and only it is sent for approval. A new result can be entered for a received sample while the test waits, is assigned or is in testing, not while its reported result waits for approval. |
| Value           | A result is a number in the unit of the way of testing, shown with the number of decimals its way of testing sets, or a text such as "Not detected". Numbers are stored exactly, never rounded by floating point. |
| Limit copy      | When a result is created, the limit of the sample's regulation for its parameter is copied onto it with its unit. Later changes to the regulation do not change existing results. |
| Versions        | A change request on a result whose process is completed creates a new version that replaces it. The signed version stays unchanged and is marked as replaced. |
| Measurement     | A result records the machine it ran on and when it started, both taken from its booking and correctable by the lab QA; an outsourced result has no machine. The time the result is entered is when the measurement is done: the test's scheduled or running bookings are done, and a booking still waiting in the queue is cancelled. |
| Entered by      | Each result records who entered it. The results of an outsourced test are entered by the subcontractor, whose people sign in to the system, or by a lab QA, once its dispatch is sent. A lab QA sends them for approval like their own. |
| Sanity check    | Before a numeric result is sent for approval, it is compared with the approved results of the same parameter, way of testing and sample type, whoever the customer. When there are enough of them, 10 by default, and the value is more than 3 standard deviations from their mean, or the value is within 10% of the regulation limit, the tester is warned with the reason and may still send it. The warning is kept on the result and shown to the approver. The minimum count, the spread and the margin are [system parameters](../shared.md#sh-03-configuration-through-settings-and-system-parameters). A text result is not checked. |
| Conclusion      | The tester sets each result's conclusion, pass or fail, when the sample has a regulation.                                         |
| No self-approval | The person who entered a result cannot approve it; another person who signs that level must. Signing the first level of a chain with more than one level sends the result; any other signature approves it. |
| Final decision  | The tester can withdraw a result they sent until the head of department acts. The head's approval or rejection completes the result's process, so neither can be withdrawn: a rejected result stays on record and a retest adds a new one. Rejecting tells the person who entered the result the reason. Only the lab head's rejection of the report sends an approved result back. |
| Progress        | Entering the first result, or starting a booking, starts the test, its sample and its test request; outsourcing a test starts its sample and its test request. A sample waits for approval once each of its remaining tests has its reported result sent, and is completed once each is approved; its test request follows its samples the same way. Cancelled tests, and cancelled or rejected samples, do not count. |
| Cancelling      | The head of department can cancel a sample test of their department that has no approved result, with a reason, such as the parameter cannot be tested on the sample: a person of the department of the test's testing task who may edit sample tests. Only a waiting, assigned or testing test can be cancelled. Its task and bookings, running ones included, are cancelled. A cancelled test is left out of the report; its reason stays on the test request. |
| No deletion     | A result cannot be deleted, and neither can the sample test, sample or test request it belongs to. |

## Reports and change requests

| Rule            | Description                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Test report     | A test request has one test report covering all its samples, issued in Vietnamese, English or both side by side. Samples have no sign-off of their own: once a sample's results are approved, the next signature is the lab head's on the report. It is signed through its approval chain and issued with a report number from a sequence and the digitally signed PDF ([SH-04](../shared.md#sh-04-signatures-and-digital-signing)). |
| Draft           | When every sample test of a request is approved or cancelled, the system creates the draft report and a signing task for the lab head. |
| Content         | The report shows its report number and the test request's code, the customer and their address, when the samples were received and the report date, and for each sample its name, lab code and conclusion with a table of parameter, result, unit, limit and method. It prints the heads of department who approved the results and the lab head; testers' signatures are internal and not printed. Cancelled tests are left out. |
| Rejection       | The lab head can reject a report with a reason, naming the results to check again. Those results go back to the queue of their head of department, unassigned and unsigned: their signatures are withdrawn, their sample tests, samples and request go back to testing, and a new testing task with the reason waits unassigned in the queue of the department that tested them. The report waits until they are approved again; the lab head then gets a new signing task. |
| Delivery        | The test request records the report language (Vietnamese, English or bilingual, bilingual by default), how the report is delivered (in person by default, by post, by email or another way with a note) and the contact who receives it. Sample delivery staff deliver the issued report that way and record when it was delivered and by whom; recording an email delivery emails the PDF to the recipient. When digital signing is on, an issued report's PDF is the digitally signed one, so it is delivered, downloaded and announced once Viettel Sign has signed it. Customers are notified when a report's PDF is ready, on the order and to its contact when the request came from an order, and issued reports can always be downloaded from the customer portal. |
| Change request  | A change to a document whose process is completed is a change request: what to change, why, who asked and when. Anyone who can edit that type of document can raise one, on an approved result or an issued report. A rejected result is corrected by a retest, and a rejected correction by another change request, since a reported sample takes no retest. A version has one open change request at a time. It is signed through the change-request chain of the document's type ([SH-07](../shared.md#sh-07-signed-documents-are-locked)); approval or rejection is final, and the requester is notified of either. |
| New version     | The last approval of a change request applies it: a new version of the document, such as a result or a report, replaces the old one, which is kept unchanged and marked as replaced. A new result version keeps the old one's values and copied limit, unsigned; its test goes back to testing with a testing task in the queue of the department that tested it, noting what to change. A new report version is a draft the lab head gets a signing task for; signing it issues it with a new report number, and the portal offers it in place of the old one. |

## Signing

Signing follows [Approval and signing chain](../../business/approval-and-signing-chain.md) and [SH-04](../shared.md#sh-04-signatures-and-digital-signing).

| Rule            | Description                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Approval chain  | Each document type, such as test result, has one chain of levels for signing it and one for change requests on it, each signed in order. Each level names the role that signs it, whether the signer must belong to the department that did the work, and whether the level can reject. |
| Signature       | A signature records the document and its version, the level, the signer and, as they were at signing, the signer's name, role and level name. A rejection records its reason. |
| Withdrawal      | A withdrawn signature is kept with the time it was withdrawn; signature records are never deleted.                               |
| People          | A person is someone who works for the laboratory, maintained by the administrator. Their details are their contact; if they sign in, they have an Odoo user. |
| Permissions     | A permission is an action on a document type (read, create, edit, archive, delete or sign) on every record, only those of the person's department or only those of the person's team. |
| Roles           | A role is a set of permissions the administrator defines. A person holds roles and can also be given permissions directly; they have every permission of their roles plus their own. |
| Enforcement     | Permissions are enforced in the API and in the interface: a person does not see menus, records, fields or buttons for what they are not allowed to do. |
| Global rules    | Some rules hold for everyone whatever their permissions, such as a signed document not being edited, archived or deleted. See [Security](../../security/readme.md). |
| Signing levels  | Each approval level names the role that signs it. |

## Testing work and scheduling

Testing work follows [SH-10](../shared.md#sh-10-tasks-and-to-do-list) tasks and [SH-11](../shared.md#sh-11-schedules-and-reminders) schedules.

```mermaid
flowchart LR
    received[Sample received] --> queue[Testing task in the department queue]
    queue --> assign[Head of department assigns a person]
    assign --> recommend[Scheduler recommends a way of testing and a machine slot]
    recommend --> book[Person schedules the booking]
    recommend -->|no machine in time| outsource[Scheduler suggests outsourcing to a subcontractor]
    book --> test[Person tests and enters the result]
    test --> approve[Result sent for approval]
    approve --> done[Task done when the result is approved]
```

| Rule               | Description                                                                                                                                     |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Testing tasks      | When a sample is received, the system creates a testing task for each sample test and puts it in the queue of the department that does the work. |
| Assignment         | Testers claim unassigned testing tasks of their department, or the head of department assigns them: all of a sample's testing tasks in the department to one person at once, or a single task. Moving a task to another person or department needs a reason. |
| Due date           | Sales states the date the customer expects the results on the test request. Each sample test is due at the end of the day, in the company's time zone, a safety margin in days before that date (2 days by default), kept for handling incidents. The due date is worked out when the sample test is created or the request's expected date changes; changing the safety margin does not change due dates already worked out. The worked-out date is the default and can be changed on the sample test. A test is urgent when its due date is within a number of hours, 24 by default, or when the person running it or the head of their department marks it urgent, stating why. The safety margin and the urgency threshold are [system parameters](../shared.md#sh-03-configuration-through-settings-and-system-parameters) administrators change. |
| Method steps       | The person running a test sees the steps of the testing method of its way of testing, each with its number, how long it takes, what to do and its note. The steps are the same for the whole laboratory. |
| Recommendation     | When a task is assigned, the scheduler recommends the way of testing and machine that can finish it soonest within its due date, from the machines that can run it and are fit to use. |
| Run time and slots | Each way of testing has a run time on each machine that can run it. A booking takes the run time rounded up to whole slots of 15 minutes.     |
| Machine queue      | Tests waiting for a machine join its queue. The scheduler gives each the next free slot: urgent tests first, then in the order they joined the queue. |
| No overlap         | The bookings of one machine do not overlap. A machine that is overdue for calibration, under repair or retired gets no bookings.              |
| Suggest outsourcing | When no machine that can run a test is available, or none has a free slot that finishes before the test's due date, the scheduler suggests outsourcing it through one of the parameter's subcontracted ways of testing. |
| Machine unavailable | When a machine becomes under repair or overdue for calibration, its scheduled bookings go back to the queue and are rescheduled on other machines; those that cannot finish in time get an outsourcing suggestion. |
| Locations          | A step of a testing method can name the [location](features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28) where it is done, such as a fume hood or a water point. A sample can name the location it was taken from. The person running a test sees the locations of its steps and of its sample, on the testing task, the schedule, the to-do list and the timeline of their day, and opens it on its parent location's map. A bookable location, such as a shared room, is booked on the calendar ([SH-11](../shared.md#sh-11-schedules-and-reminders)), by people or by the scheduler for a step done in it. |
| Rooms              | When a step of the way of testing's method is done in a bookable location, the scheduler books that location for the step's time along with the machine, and plans the test only when the machine and every such location are free. Steps run in step number order from the start of the test, each for its duration rounded up to whole slots of 15 minutes. Each location booking is a calendar event on the person's calendar and the location's schedule ([SH-11](../shared.md#sh-11-schedules-and-reminders)). Moving, cancelling or rescheduling the machine booking moves or cancels its location bookings with it. |
| Adjusting          | The person running a test, and the head of their department, can move or cancel its booking; the slot goes back to the queue.                 |
| Bumping            | The head of department can bump an urgent test to the earliest slot on a machine fit to run it, with a reason. Bookings in that slot that have not started go back to the queue and are planned again, and their people are notified; a running booking is never interrupted. When the bump would make other tests miss their due date, the head chooses: let them run late, outsource them straight away, or not bump. |
| Changing a due date | A sample test's due date can be changed by hand; the date from the safety margin is its default. |
| Return estimate    | For a set of samples and parameters, the scheduler estimates the earliest date their results can be returned: for each parameter, the earliest a machine that can run it finishes, given its queue and run time, plus the safety margin; the latest of those is the estimate. A parameter only a subcontractor tests is named and left out. Nothing is booked by an estimate. |
| Priority request   | When the customer asks for results earlier than the estimate, the scheduler checks the requested date as if its tests were urgent, with the due date check below. It answers that the date can be met, can be met only by outsourcing named parameters, or cannot be met, with the earliest date it can. An accepted priority request marks the tests of its test request urgent when they are created. |
| Due date check     | A due date falls on a weekday and not on a public holiday; the administrator can mark a public holiday as a working day. When a due date is set, the scheduler checks that the test has a free slot that finishes before it, or that other bookings can move to make room without missing their own due dates; otherwise it reports that the date cannot be met. |
| Deadline risk      | A test is at risk when it has no booking that finishes before its due date, or its booking has ended without a result. The person running it and the head of their department are told once when it becomes at risk, and it shows as at risk on the task, the queue and the schedules until it no longer is. The scheduler checks whenever bookings change, and a [scheduled job](../shared.md#sh-09-scheduled-tasks) finds bookings that ended without a result. |
| Machine heads-up   | Scheduling or starting a booking on a machine whose next calibration or maintenance is due within a number of days, or that had a repair recorded within those days, shows a warning naming it; the booking goes ahead. The number of days is a [system parameter](../shared.md#sh-03-configuration-through-settings-and-system-parameters), 7 by default. |
| Bookings as tasks  | A scheduled booking appears on the person's schedule and in their to-do list as part of their testing task, due at its start.                |
| Outsourcing        | The head of department decides on outsourcing suggestions, and can outsource a waiting or assigned test straight away with a reason in an emergency. Sample tests tested by a subcontractor are sent in a dispatch with the date sent and the date results are expected back, carried by sample delivery staff or a delivery service. A dispatch is draft, sent, received or cancelled; a sample test is in one dispatch that is not cancelled, a cancelled dispatch's tests stay outsourced for another dispatch, and a dispatch whose tests have results cannot be cancelled. |

## Laboratory files

Laboratory files are the files the testing work produces and uses outside MediLab's forms: raw data from instruments, working spreadsheets, result files and report drafts. The Laboratory module keeps them the way an object store does: folders of files, each file a series of versions, with the bytes in an S3 bucket and only their description in the database. People work on the files in their own programs on the laboratory's computers through [Medilab Sync](applications/medilab-sync.md), browse and download them in the Documents menu of the back office, and edit Office documents together in the browser. Medilab Sync and Medilab Mobile reach the module through its REST API.

| Rule            | Description |
| --------------- | ----------- |
| Folder          | A folder holds files under paths relative to it, such as `HPLC/run-01.csv`. It has an owner, a name unique for that owner, and members. It never stores where it lives on anyone's computer. |
| Sample folders  | A folder can belong to a sample, with a category: raw data, working documents, results or reports. The head of department creates a sample's folders from the sample; a person needs both the folder and the sample to use it, so testers still see only the lab code. |
| Members         | The owner and the people they add can read and write the folder: see, download and upload its files and restore their versions. There is no read-only member. The owner and administrators add and remove members; only administrators change the owner, and the previous owner stays a member. |
| Sync rules      | A folder can limit which files are synced by name prefix, name pattern with `*`, or extension, with or without subfolders. With no rule every file is synced. |
| Versions        | Saving a changed file adds a version: a number that never changes, who saved it, from which device, when, its size and SHA-256 hash, and how it was made: synced, restored, edited online, or kept from a conflict. A version is never edited or deleted. The file's current version is the one people get. Two versions with the same content share the stored bytes. |
| Uploads         | A file is uploaded straight to the bucket in parts through short-lived signed addresses, never through Odoo, up to 5 GiB in parts of 16 MiB. The server checks the hash before the version counts. An upload left unfinished expires and its parts are removed. |
| Conflicts       | An upload made from a version that is no longer the current one is kept as a conflict version, never written over the current one. The person chooses to keep their own file or take the server's; both versions stay in the history. |
| Restore         | Restoring an earlier version adds a new current version with its content; history is never rewritten. |
| Raw data        | Raw-data files are evidence: each save adds a version, they are not edited online and they are not locked. |
| Online editing  | Word, Excel and PowerPoint result and working files are edited together in the browser through ONLYOFFICE. One editing session is open per file; saving it adds a version. When the editing service is down, sync, download, history and restore keep working. |
| Locks           | A working or result file that is not an Office document can be locked by one person while they edit it, for 30 minutes unless renewed. Others cannot upload it meanwhile; an administrator can release a lock someone left. |
| Signing         | A version of a result file is approved by signing it through the approval chain of laboratory files ([SH-04](../shared.md#sh-04-signatures-and-digital-signing)). The signature belongs to that version and its hash; a newer version needs its own. |
| Devices         | Each computer signs in once with the person's MediLab login and gets its own key; the password is never stored on it. An administrator sees every device and revokes one, which stops it at once without removing the person's folder memberships. |
| Turning off     | An administrator can turn a folder off: nobody can upload to it, and its files can still be read and downloaded. |
| Archiving       | An archived folder keeps its files and versions until its retention date, worked out from a retention period that is a system parameter. |
| Changes         | The API gives each device the changes to the current versions of a folder since the last change it saw, so every computer gets other people's new versions. Renaming and deleting are not passed between computers. |
| Audit           | Signing in and out of a device, uploads, conflicts, restores, downloads, online editing, locks, signatures, member changes and archiving are recorded in the [audit trail](../shared.md#sh-05-audit-trail). |

### Upload

```mermaid
stateDiagram-v2
    [*] --> prepared: upload asked for
    prepared --> uploading: first part sent
    prepared --> completed: same content already stored
    uploading --> finalizing: every part sent
    finalizing --> completed: hash checked, new current version
    finalizing --> conflict: made from an older version
    prepared --> expired: not finished in time
    uploading --> expired: not finished in time
    prepared --> aborted: cancelled by the device
    uploading --> aborted: cancelled by the device
    finalizing --> failed: hash or size wrong
```

### Online editing session

```mermaid
stateDiagram-v2
    [*] --> open: a person opens the file online
    open --> saving: the editor saves
    saving --> committed: new version added
    saving --> conflict: the file changed meanwhile
    open --> closed: everyone left without changes
    open --> expired: no activity for 12 hours
    saving --> error: the editor's file cannot be read
```

### Lock

```mermaid
stateDiagram-v2
    [*] --> active: a person locks the file
    active --> active: renewed before it expires
    active --> released: the person unlocks it, or an administrator releases it
    active --> expired: 30 minutes without renewal
```

## Actors

- [Administrator](features/admin.md): master data, people, roles, approval chains and task types
- [Sample delivery staff](features/sample-delivery-staff.md): collect, receive and hand over samples, and carry outsourced samples to subcontractors
- [Tester](features/tester.md): schedules and runs tests, enters and signs results
- [Head of department](features/head-of-department.md): assigns testing work, manages the department's schedule, approves results
- [Lab head](features/lab-head.md): signs test reports and approves their change requests
- [Subcontractor](features/subcontractor.md): sees the tests sent to it and enters their results

## Related documents

- [Overview](../index.md)
- [Administrator](features/admin.md)
- [Approval and signing chain](../../business/approval-and-signing-chain.md)
- [Shared technical features](../shared.md)
- [Database diagram](../../infrastructure/database/laboratory/laboratory.prisma)
