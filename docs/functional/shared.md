# Shared technical implementations

This document describes the technical capabilities shared by every module (E-commerce, Inventory and Laboratory). They are not specific to any actor: users meet them as behaviour of the whole system, and developers and system administrators build and configure them once. It is a reference for developers and system administrators.

Each requirement has an ID (`SH-nn`) so that module documents can refer to it.

## I. Business requirements

### 1. Platform

#### SH-01 Modular installation and integration

The system consists of three modules (E-commerce, Inventory, Laboratory) that can be installed independently and work together when installed together.

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- Installing a module never requires installing a module that depends on it.
- When two modules are installed, the integration between them is active without extra configuration. Features that need a module that is not installed are hidden, not broken.
- Each module can be upgraded without losing the data of the others.
- The MediLab look is the optional Medilab Theme module (`sol_theme`), which depends on no other MediLab module and that no MediLab module depends on. Installing or removing it changes only how the system looks.
- Each module builds on Odoo Community apps and installs them with itself, as listed in [Module boundaries](../business/module-boundaries.md#odoo-apps). No module needs Odoo Enterprise.

Acceptance criteria:

- Laboratory installs and runs alone, and looks like standard Odoo without the theme.
- The theme installs on an Odoo database without any MediLab module.
- Every module installs on Odoo Community without any Enterprise app.
- E-commerce and Inventory each install on top of Laboratory without the other being present.
- Uninstalling E-commerce or Inventory leaves Laboratory data intact.

#### SH-02 Simple installation and configuration

Anyone with Odoo 20 experience can install and configure the system without developer help.

- Installation follows the standard Odoo way: add the module, update the app list, install.
- Everything a laboratory needs to adapt (company details, numbering, deadlines, e-mail, payment and signing providers, languages) is available in the settings screens, not in code.
- A fresh installation has working defaults and, optionally, demo data to try the system.
- A setup guide lists the steps in order and what to check after each.

Acceptance criteria:

- A new installation can run the full order-to-result flow after following the setup guide, without editing any code.

#### SH-03 Configuration through settings and system parameters

The system's behaviour is driven by configuration, not by hard-coded values.

- **System parameters** hold values such as the quotation payment deadline, reminder intervals, upload size limits and numbering formats.
- **Configuration files** (environment variables) hold deployment settings and secrets, such as provider credentials. Secrets never appear in the database, logs or documents.
- Settings are changed from the settings screens by administrators; every change is audited (SH-05).
- A new option is added by declaring it with a default, so existing installations keep working after an upgrade.
- Each system parameter is a settings field declared by its module, with a type, a default and a help text in each language, and stored in Odoo's system parameter table.
- Settings that change behaviour of existing documents apply to future documents only.

Acceptance criteria:

- Changing the payment deadline setting changes the deadline of the next quotation, not of those already sent.
- A missing optional setting falls back to its documented default.

### 2. Trust and traceability

#### SH-04 Signatures and digital signing

**Approving a document is signing it.** There is one concept: a user with the right role signs a document in the system, and that signature is the approval. There is no separate approval step and no separate signing step.

| Item             | Rule                                                                                                                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Who signs | The role required by the document's approval chain, for example the Head of Sales for an order, the Head of Department for a test result and the Lab Head for a test report. Chains can have several levels, each signing in turn. The Head of Department may approve results they entered; the Lab Head reviews the approved results and signs the report before issue. |
| What is recorded | For every signature: the signer, their role and level, the time, and the document version signed, with the hash of its content for a document whose content has one, such as a laboratory file version. The signer is the logged-in user; signing needs a deliberate action (and confirmation), not just opening the document. |
| Rejection        | A signer can reject with a reason instead of signing. The reason is kept and the requester is notified.                                                                                                                  |
| Documents        | Invoices, quotations, orders, test results and any other document type that has an approval chain.                                                                                                                       |

**Digital signature is applied automatically when a document is printed.** When a signed document is printed or exported as PDF (for sending, downloading or archiving), the system has the signature provider (see Viettel Sign below) digitally sign the PDF with the laboratory's certificate and stores the signed file. Users do not sign certificates by hand.

- One laboratory certificate signs every digitally signed document, whoever signed the approval chain.
- The test report is the document type that is digitally signed. Another document type joins by naming the report it prints; the rules below then apply to it.
- The signed PDF is stored with the document, together with the signature details and the time, so the same file is returned every time it is downloaded.
- Only documents that have been fully signed (final level approved) are digitally signed on print. A document still under approval prints as a draft, clearly marked, without a digital signature.
- Every signed PDF can be verified: it shows who approved it (from the signature records), that the digital signature is valid, and that the content has not changed. Verification is a public page, open to the customer without logging in: they upload the PDF and see the result. Each signed PDF prints the page's address.
- If the provider is unavailable, the document is not printed as signed; the user is told and can retry, and the signing is retried automatically. Nothing is shown as digitally signed unless the provider confirmed it.

Acceptance criteria:

- Printing a fully signed document returns a digitally signed PDF without any extra step from the user.
- Printing a document that is still under approval returns an unsigned, marked draft.
- A signed PDF fails verification if any of its content is changed.
- A provider outage leaves the document unsigned and retries it.
- The signature record shows the signer, role, time and document version for every level.

#### SH-05 Audit trail

Every action in the system is recorded and can be reported on.

- **What is recorded:** user actions (create, edit, delete, approve, sign, download), system events (scheduled jobs, integrations, errors) and data changes with the old and the new value.
- **Each entry has:** who (user or system), when, what (document and field), the old and new value, and the source (screen, API, job, or the system installing or upgrading a module).
- Audit entries cannot be edited or deleted by any user, including administrators. Only the cleanup job removes them, once they are older than the audit retention period and written to an archive file (SH-09).
- The audit retention period is a system parameter. Until an administrator sets it, entries are kept for ever.
- Authorised users (administrators and auditors) can search the trail by document, user, period and action, and open the full history of one document. The history of a document includes the entries of the documents under it, such as the samples and sample tests of a test request, also once a sample is deleted.
- **Audit reports** can be generated for a period and exported for compliance purposes.
- Personal data in the trail is limited to what is needed to identify who acted. Personal data in a changed field, such as an email, a phone or an address, is masked so its value is never shown in full.
- An entry records one action; an edit lists each changed field with its old and new value. An entry written by a scheduled job links to the job run. Signing in and out is not recorded.
- Odoo's field tracking shows the changes of a document in its chatter to everyone who reads it; the audit trail is the record that no one can edit or remove, kept apart from the chatter.

Acceptance criteria:

- Changing a price shows who changed it, when, and from what to what.
- An administrator cannot remove an entry from the trail.
- The history of a test request shows the changes to its samples and sample tests.
- A report for a given period lists every signature, approval and deletion in that period.

#### SH-06 Locking of documents in use

Two users cannot change the same document at the same time.

- When a user starts editing a document, the document is locked for others; they can still read it.
- Others who try to edit see who holds the lock and since when, and can ask to be notified when it is released.
- The lock is released on save, on cancel, when the user leaves, or automatically after a period of inactivity, so a closed browser does not block the document.
- An administrator can release a lock that is stuck; this is audited.
- Long operations, such as sending a quotation or confirming a payment, lock the document for their duration so they cannot run twice.
- A document has at most one active lock. The inactivity period is a system parameter (SH-03), 15 minutes by default.
- Others see a lock taken or released as it happens, without reloading, through Odoo's bus.

Acceptance criteria:

- A second user opening a locked document sees who is editing it and cannot save changes.
- A lock abandoned by a closed browser is released after the inactivity period.

#### SH-07 Signed documents are locked

Once a document is signed it cannot be modified. Because approving is signing (SH-04), this applies from the first signature of the approval chain.

- From the first signature the document is read-only for everyone, including administrators.
- **Until the document's process is completed**, a signer at any level, the final level included, may withdraw their own signature once every higher level has withdrawn theirs. This reopens the document for editing; every withdrawal is audited and the document must be signed again from that level.
- **After the document's process is completed**, such as a completed result or order or an issued report, it cannot be reopened. A person allowed to edit that document type raises a **change request** with the proposed changes and reason. This applies to results, reports, quotations and orders.
- The change request follows an approval chain defined per document type, for example the Head of Sales for a quotation or the Head of Department for a test result and the Lab Head for a test report.
- When the chain approves, create an unsigned **new version** linked to the unchanged signed one, and sign the new version again. Results mark the previous version replaced at correction. An issued report remains the issued version until its signed replacement is issued; [linked result and report corrections](laboratory_module/overview.md#reports-and-change-requests) wait for all required result approvals and use a fresh report signing task.
- Anyone concerned can follow the status of the change request: requested, approved, rejected, applied.
- A rejected request leaves the signed document untouched and records the reason.

Acceptance criteria:

- No screen or API changes a signed document.
- A signer can withdraw their signature only while no higher level has a standing signature and the document's process is not completed, and the document is then editable again.
- After the document's process is completed, no signature can be withdrawn.
- An approved change request produces a new version linked to the old one; the old one stays readable.
- The status of a change request is visible to the requester at every step.

### 3. Operations

#### SH-08 Multiple languages

All user-facing text can be translated, and users choose their language.

- Every label, message, e-mail template, document template and report can be translated.
- A user switches language from their profile at any time; the screen changes immediately and the choice is remembered.
- Customers receive e-mails and documents in their own preferred language.
- A new language is added by installing it and translating the texts; no code change is needed.
- Fall back to the default language when a text is not translated yet.
- Dates, numbers and currency follow the language's format.
- Languages and translations are Odoo's own: a language is installed from the settings, and every text is translated through Odoo's translation files. English and Vietnamese are installed with the Laboratory module.
- E-mails, document templates and reports render in the recipient's language: the customer's contact language for customers, the user's language for staff.
- A check in CI fails, listing them, when a user-facing string of a MediLab module has no Vietnamese translation.

Acceptance criteria:

- A user who switches to another language sees no untranslated labels in the screens that have been translated.
- Adding a language does not affect users of other languages.

#### SH-09 Scheduled tasks

Recurring work runs by itself, and its health is visible.

Typical jobs: payment reminders, quotation expiry, retention and expiry checks (Inventory), report generation, e-mail retries.

- Each job has a schedule (interval or fixed time) that an administrator can change.
- Administrators see every job with its last run, next run, result and duration, and can open the log of each run.
- A failed job is retried automatically a limited number of times with a growing delay; after that it is marked failed and an administrator is notified.
- An administrator can run a job by hand and retry a failed one.
- A job is safe to run twice: running it again never sends a duplicate reminder or creates a duplicate record.
- Jobs do not run on top of themselves: a second run waits or is skipped while the first is running.
- **Job and queue.** Each job has a unique key and is scheduled by an Odoo cron that administrators configure. A job works through a queue of items: each item is one unit of work, such as one reminder to send, with a key unique within the job, so the same work is never queued twice. An item is retried with a growing delay up to the job's number of attempts, then marked failed. A run claims the items it takes; an item claimed longer than the job's claim timeout, such as after a crash, goes back to the queue.
- Each run records when it started and ended, its result, its log, and who ran it by hand; how many items were done and remain comes from Odoo's cron progress.
- **Cleanup job.** A cleanup job removes housekeeping records older than their retention period: finished job items and job runs, released and expired locks, read notifications and their pushes, mobile devices turned off, and audit entries older than the audit retention period. Each retention period is a system parameter, 90 days by default; the audit retention period is empty by default, which keeps entries for ever. It never removes business records or signatures.
- **Archive files.** Only audit entries are archived; the other records are removed without one. Before it removes audit entries, the cleanup job writes them to a compressed archive file per period, stored as an Odoo attachment in object storage, checks the file, and only then removes the entries. Administrators can list and download archive files; an archive is never loaded back into the system.
- Backups of the whole database and file store belong to the hosting, not to the application.

Acceptance criteria:

- A job that fails shows its error in the run log and is retried.
- Running a payment-reminder job twice in a row sends each reminder once.

#### SH-10 Tasks and to-do list

Work waiting for someone is a task with a deadline, and every person sees their tasks in one to-do list.

- **Tasks are MediLab's own.** A task has its chatter and attachments. Tasks are internal: a task is assigned to one internal Odoo user, so everyone who does tasks has a login.
- **Task types.** Each kind of task, such as sample collection, testing a parameter or signing a document, is a task type. Task types come with the modules that create their tasks; administrators neither create nor remove them. A task type says what creates its tasks (an event, or people by hand), where new tasks go (the queue of the department the event names, the holders of a role, or the person the event names), and the deadline when the document gives none. Administrators choose where new tasks go and the default deadline.
- **Created by the system or by people.** The system creates a task when its event happens, such as a sample being received. People can also create a task and assign it with a deadline, such as sales scheduling a sample collection on an order.
- **Linked documents.** Only the system links a task to the document it opens and sets its type. Nobody changes a task's type or document afterwards. A task acts on its document, such as a testing task showing its method's steps or moving its test along as it is assigned, only while the system linked it. A task stored before this rule is trusted only when its audit trail shows it was created that way and never changed; an administrator reviews the others.
- **Department queue.** A task routed to a department waits in that department's queue until the head of department assigns it to a person or a person of the department claims it. When two people claim the same task at once, the second is told it is already claimed. A task routed to a role waits the same way until one of the role's holders claims it.
- **Access.** Every person sees the tasks assigned to them and the queues they can claim from without any permission. Creating tasks by hand, assigning, reassigning and cancelling them, and seeing other tasks need the task permissions, such as those of the person's department for a head of department.
- **Reassigning.** Moving a task to another department, or an assigned task to another person, needs a reason, which is kept on the task and in the audit trail.
- **To-do list.** A person's to-do list shows their open tasks, soonest deadline first. Clicking a task opens its document at the action to take, such as entering a result or signing.
- **Dashboard.** The Tasks app opens on the person's day: today's planned tasks against the hours of the day, the next tasks to do with the action each needs, the tasks waiting in their queues to claim, and what they finished. From it, their tasks, their finished tasks and all the tasks they can see open as a list, a calendar or a timeline.
- **Lifecycle.** Every task goes through the same statuses: open, assigned, in progress, then done or cancelled. The state of the work itself, such as a sample or a result, belongs to that document.
- **Done.** A task created by the system is done when its work is done, such as when the result it asked for is approved. A task created by hand is marked done by its assignee. Done tasks move to the person's completed list.

Acceptance criteria:

- A task assigned to a person appears in their to-do list with its deadline.
- A person can claim an unassigned task of their own department, not of another; a task already claimed cannot be claimed again.
- Reassigning a task without a reason is refused.
- A task created by hand that names a document, or a change to a task's type or document, is refused; a task changed that way before the rule never acts on its document.
- Clicking a task opens its document at its action.
- A testing task is done when its result is approved, without anyone marking it.
- Changing where a task type's tasks go routes its new tasks there; existing tasks stay where they are.

#### SH-11 Schedules and reminders

Tasks with a planned time, test runs and resource reservations appear on schedules, and people are reminded before they start.

| Schedule              | Shows                                                                                     |
| --------------------- | ----------------------------------------------------------------------------------------- |
| Personal schedule | A person's planned tasks, test runs including no-machine runs, and independent location bookings |
| Machine schedule | A machine's reservations for runs, downtime and queued work |
| Location schedule | Independent bookings and the step intervals reserved by test runs in a bookable location |
| Test request schedule | The tasks, bookings and due dates of the samples of one test request                     |
| Outsourcing schedule  | Sample tests sent to subcontractors, with the date sent and the date results are expected |

- **Built on Odoo Calendar.** A planned task and a test run, with a machine reservation when needed, each have an Odoo calendar event (`calendar.event`) with the person who does the work as attendee, so the personal schedule is the person's Odoo calendar, next to their other events. Task and event stay in step both ways: planning or moving the task moves the event, and moving or deleting the event in the calendar replans or unplans the task; a run's event can only move where its tester and all required resources are available. Working hours and holidays come from the HR calendar; approved leave comes from Odoo Time Off. A no-machine run still has a personal event and any required location reservations.
- **Booking a location.** Anyone who works for the company can book a bookable [location](laboratory_module/features/admin.md#1-catalog-us-ad01-to-us-ad08-us-ad26-to-us-ad28) for a time: the booking is an Odoo calendar event that names the location, with its organiser and attendees, so it shows on their calendars and on the location's schedule. Bookings of one location do not overlap or fall within its unavailable intervals; a location that is not bookable, or is archived, cannot be booked. Newly recorded unavailability replans affected not-started bookings and notifies their responsible people. The organiser moves or cancels an independent booking; an administrator can cancel an independent booking. Booking a location shows the free times of the locations under a chosen location, such as the rooms of a floor.
- **Run reservations.** A location reservation associated with a run cannot be moved or cancelled independently, including from the calendar. Change it through the run using the existing run-adjustment permissions. Moving a not-started run checks its tester, required machine and every required location before changing anything, then updates its event, not-started attempts and all resource reservations together; failure leaves every reservation unchanged. Cancelling a not-started run removes its personal event and resource reservations and returns its not-started attempts to the queue without cancelling their sample tests. Notify the responsible people and update reminders. Ordinary move or cancel actions are refused once the run starts; required-location unavailability follows the disruption rules.
- A reminder is sent before a planned task, run or location booking starts, 15 minutes by default. Use its calendar event and notify the task assignee or location organiser and attendees, without a second Odoo alarm. Moving a booking cancels its unsent old reminder and schedules a reminder for the new time. If the new time is already inside the reminder window, notify immediately. Deduplicate each schedule update; never retract a reminder already delivered.
- A reminder is shown in the application as a pop-up and sent by email through Brevo. Mobile-app delivery is deferred with Medilab Mobile.
- **Event settings.** The administrator can turn an event off, so no notification of it is created, and edit its templates. Mandatory events cannot be turned off. Turning an event off does not stop the tasks the event creates.
- **Recipients.** For each event, the administrator chooses who is notified: the holders of one or more roles, the people of one or more departments, or both, on top of the person the event concerns directly, such as the assignee of a task.
- **Notifications.** Every notification belongs to an event, such as a booking reminder, and has a key, so the same notification is never created twice. It is delivered once on each channel the person keeps on for that event. Mandatory events, such as a password reset or a payment receipt, cannot be turned off.
- **Built on Odoo Discuss.** A notification is an Odoo message (`mail.message`) on the document it is about, and an event is a message subtype (`mail.message.subtype`). In the application it is an Odoo inbox notification, shown as a pop-up through the bus. By e-mail it goes through Odoo's mail queue, which retries it. Mobile-app pushes are outside the current delivery scope.
- **Channel choices.** A person's choice of channels extends Odoo's own notification preference on their user: Odoo's choice, in the application or by e-mail, is their default for every event, and their preferences add a choice per event and supported channel.

Acceptance criteria:

- A run appears on its tester's personal schedule and on each required resource schedule; a no-machine run needs no machine reservation.
- A location booking appears on the calendars of its organiser and attendees and on the location's schedule.
- Booking a location for a time that overlaps another of its bookings is refused with a message naming the existing booking.
- A location that is not bookable cannot be chosen for a booking.
- A reminder arrives 15 minutes before a booking starts, once on each selected channel.
- Moving a booking cancels only unsent old reminders, schedules the new one and sends immediately if already inside the reminder window. Reprocessing the same update creates no duplicate.
- A run cannot be planned during an unavailable interval of any required location.
- Moving a run to a slot with a busy tester, machine or required location is refused without changing any reservation.
- A run-associated location reservation cannot be dragged or deleted independently; a permitted run move updates every reservation and not-started attempt together.
- Cancelling a not-started run releases all its reservations and queues its attempts without cancelling the sample tests; ordinary move and cancel actions on a running run are refused.
- An event the administrator turned off notifies nobody; turning it on again notifies the next occurrence.

#### SH-12 Internal messaging

| Rule | Description |
| --- | --- |
| Chat | Laboratory staff communicate through Odoo Discuss. |
| Record discussion | Staff discuss an accessible record in its chatter, keeping the conversation with the work it concerns. Existing access permissions apply. |

Acceptance criteria:

- Staff can exchange messages in Discuss and discuss a record they may access in its chatter.
- A record discussion does not grant access to records the participant cannot read.

## II. External systems integration

All integrations are optional and enabled in the settings. Credentials come from configuration files (SH-03), never from the database. Every call is logged in the audit trail (SH-05), and a provider outage never loses a business action: it is queued and retried (SH-09).

### 1. Brevo (email)

The system sends all e-mail through Brevo's SMTP relay, set as Odoo's outgoing mail server in the configuration file, so every e-mail, from notifications to quotations, goes through Odoo's mail queue.

- Used for: notifications, alerts, quotations and invoices with attachments, reminders and reports.
- Administrators configure the sender and the templates. Templates are Odoo e-mail templates (`mail.template`), translatable (SH-08), and use the customer's contact (Sales documents) and notification preferences.
- Delivery status (sent, delivered, opened, bounced, failed) is recorded against the message from Brevo's webhooks, on Odoo's notification of each recipient, so staff can see whether a customer received a quotation.
- The webhook is accepted only when `Authorization: Bearer` matches `BREVO_WEBHOOK_TOKEN`. Brevo's create-webhook call can set that bearer token. A missing or wrong token is rejected before any event is stored. The event is matched by the `X-Mailin-custom` header `notification:<id>` or by the message id together with the recipient address. A later weaker event does not replace a bounce or a failure. A hard bounce flags `email_bounced` only on the partner of that notification whose address is the event address.
- Bounced or invalid addresses are flagged on the customer's contact so that they are not used again.
- If Brevo is unavailable the message stays queued and is retried; the business action that triggered it is not rolled back.

### 2. PayOS (payments)

The system takes online payments through PayOS, added as a payment provider of Odoo's payment framework (`payment.provider`). Each payment is an Odoo payment transaction, and a confirmed one posts an Odoo payment on the invoice. The PayOS keys come from the configuration file, not from the provider record.

- Used for the advance and final invoices. The customer pays from the portal or from a payment link in an e-mail.
- Payment methods are whatever PayOS offers (for example bank transfer by QR code); administrators enable or disable them in the settings, and the portal shows only those enabled.
- A payment is confirmed only by the provider's signed notification, never by the customer's browser returning to the website. The signature is verified, and a repeated notification creates no second payment.
- A confirmed payment is recorded against the invoice and updates its payment status automatically; partial payments are supported.
- The status of each payment (created, pending, paid, failed, cancelled, expired) is stored and shown to the accountant.
- If notifications are missed, a scheduled job (SH-09) asks the provider for the status of pending payments.
- Refunds are outside this integration.

### 3. Viettel Sign (digital signature)

The system digitally signs printed documents through Viettel Sign's remote signing (SH-04). It does not ask users to sign; approval in the system already did that.

- The laboratory holds one certificate at Viettel Sign, on an account that signs automatically, without anyone confirming each signature in the MySign app. The account's credentials come from the configuration file.
- Administrators turn digital signing on in the settings and see the laboratory's certificate with its expiry, read from the provider. An expired or revoked certificate stops digital signing. Administrators are alerted a number of days before the certificate expires, a system parameter (SH-03) of 30 days by default, and again when it expires or is revoked.
- When a fully signed document is printed or exported, the system has the provider sign the PDF with the laboratory's certificate; the signed file is stored with the document and the signature details.
- Verification of a signed PDF checks its digital signature against the laboratory's certificate as the provider last reported it, that the file is the one the system stored, and the approval records of the document, and shows the result to anyone who uploads the file.
- If the provider is unavailable, the document is not issued as signed; the user is told and can retry, and the request is retried automatically (SH-09). No document is shown as digitally signed unless the provider confirmed it.

### 4. Firebase Cloud Messaging (mobile push)

Firebase delivery is deferred with Medilab Mobile and is outside the current application scope. Its integration design is retained below for the later mobile application.

- When a person signs in on the app, the app registers the device's token for their user; signing out turns the token off. Odoo's own push devices serve web browsers only, so mobile devices are MediLab's own records.
- A push sent to a token Firebase reports as permanently invalid (`UNREGISTERED`, `SENDER_ID_MISMATCH`, or `INVALID_ARGUMENT` about the token) turns that token off. A timeout or a temporary error leaves the token on and the delivery is retried.
- The access token is an OAuth token from Google Application Default Credentials or a service-account JSON in the environment, refreshed by `google-auth`. The credential value is not stored on a record and is not written to the log.
- The Firebase credentials are configuration, not data (SH-03). SMTP and FCM do not provide exactly-once delivery. The records and the jobs are created once; a retry sends again only while the earlier attempt did not succeed.

## III. Related documents

- [Overview](index.md)
- [E-commerce module](ecommerce_module/overview.md)
- [Inventory module](inventory_module/overview.md)
- [Laboratory module](laboratory_module/overview.md)
