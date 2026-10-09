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

Acceptance criteria:

- Laboratory installs and runs alone.
- E-commerce and Inventory each install on top of Laboratory without the other being present.
- Uninstalling E-commerce or Inventory leaves Laboratory data intact.

#### SH-02 Simple installation and configuration

Anyone with Odoo 19 experience can install and configure the system without developer help.

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
- Each system parameter has a key, a typed value (integer, decimal, boolean, text or duration), its default and a description in each language, and belongs to the module that declares it.
- Settings that change behaviour of existing documents apply to future documents only.

Acceptance criteria:

- Changing the payment deadline setting changes the deadline of the next quotation, not of those already sent.
- A missing optional setting falls back to its documented default.

### 2. Trust and traceability

#### SH-04 Signatures and digital signing

**Approving a document is signing it.** There is one concept: a user with the right role signs a document in the system, and that signature is the approval. There is no separate approval step and no separate signing step.

| Item             | Rule                                                                                                                                                                                                                     |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Who signs        | The role required by the document's approval chain, for example the Head of Sales for an order or the Lab Head for a test result. Chains can have several levels, each signing in turn.                                  |
| What is recorded | For every signature: the signer, their role and level, the time, and the document version signed. The signer is the logged-in user; signing needs a deliberate action (and confirmation), not just opening the document. |
| Rejection        | A signer can reject with a reason instead of signing. The reason is kept and the requester is notified.                                                                                                                  |
| Documents        | Invoices, quotations, orders, test results and any other document type that has an approval chain.                                                                                                                       |

**Digital signature is applied automatically when a document is printed.** When a signed document is printed or exported as PDF (for sending, downloading or archiving), the system sends the PDF to the signature provider (see Viettel Sign below), which applies the digital signature with the laboratory's certificate and returns the signed file. Users do not sign certificates by hand.

- The signed PDF is stored with the document, together with the signature details and the time, so the same file is returned every time it is downloaded.
- Only documents that have been fully signed (final level approved) are digitally signed on print. A document still under approval prints as a draft, clearly marked, without a digital signature.
- Every signed PDF can be verified: it shows who approved it (from the signature records), that the digital signature is valid, and that the content has not changed. Verification is available to the customer without logging in to the back office.
- If the provider is unavailable, the document is not printed as signed; the user is told and can retry. Nothing is shown as digitally signed unless the provider confirmed it.

Acceptance criteria:

- Printing a fully signed document returns a digitally signed PDF without any extra step from the user.
- Printing a document that is still under approval returns an unsigned, marked draft.
- A signed PDF fails verification if any of its content is changed.
- The signature record shows the signer, role, time and document version for every level.

#### SH-05 Audit trail

Every action in the system is recorded and can be reported on.

- **What is recorded:** user actions (login, create, edit, delete, approve, sign, download), system events (scheduled jobs, integrations, errors) and data changes with the old and the new value.
- **Each entry has:** who (user or system), when, what (document and field), the old and new value, and the source (screen, API or job).
- Audit entries cannot be edited or deleted by any user, including administrators.
- Authorised users (administrators and auditors) can search the trail by document, user, period and action, and open the full history of one document.
- **Audit reports** can be generated for a period and exported for compliance purposes.
- Personal data in the trail is limited to what is needed to identify who acted.
- An entry records one action; an edit lists each changed field with its old and new value. An entry written by a scheduled job links to the job run.

Acceptance criteria:

- Changing a price shows who changed it, when, and from what to what.
- An administrator cannot remove an entry from the trail.
- A report for a given period lists every signature, approval and deletion in that period.

#### SH-06 Locking of documents in use

Two users cannot change the same document at the same time.

- When a user starts editing a document, the document is locked for others; they can still read it.
- Others who try to edit see who holds the lock and since when, and can ask to be notified when it is released.
- The lock is released on save, on cancel, when the user leaves, or automatically after a period of inactivity, so a closed browser does not block the document.
- An administrator can release a lock that is stuck; this is audited.
- Long operations, such as sending a quotation or confirming a payment, lock the document for their duration so they cannot run twice.
- A document has at most one active lock. The inactivity period is a system parameter (SH-03).

Acceptance criteria:

- A second user opening a locked document sees who is editing it and cannot save changes.
- A lock abandoned by a closed browser is released after the inactivity period.

#### SH-07 Signed documents are locked

Once a document is signed it cannot be modified. Because approving is signing (SH-04), this applies from the first signature of the approval chain.

- From the first signature the document is read-only for everyone, including administrators.
- **Until the document's process is completed**, a signer at any level, the final level included, may withdraw their own signature once every higher level has withdrawn theirs. This reopens the document for editing; every withdrawal is audited and the document must be signed again from that level.
- **After the document's process is completed**, such as a test request completed, an order completed or an invoice paid, the document can no longer be reopened. To change it, a user raises a **change request** stating what to change and why.
- The change request follows an approval chain defined per document type, for example the Head of Sales for a quotation or the Lab Head for a test result.
- When the chain approves, the system creates a **new version** of the document, unsigned, linked to the signed one; the signed version is kept unchanged and marked as replaced. The new version must be signed again.
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
- Each run records when it started and ended, its result, how many items were done and failed, its log, and who ran it by hand.

Acceptance criteria:

- A job that fails shows its error in the run log and is retried.
- Running a payment-reminder job twice in a row sends each reminder once.

#### SH-10 Tasks and to-do list

Work waiting for someone is a task with a deadline, and every person sees their tasks in one to-do list.

- **Task types.** Each kind of task, such as sample collection, testing a parameter or signing a document, is a task type. A task type says what creates its tasks (an event, or people by hand), where new tasks go (a department's queue, the holders of a role, or a person), and the deadline when the document gives none. Administrators can turn automatic creation of a task type on or off.
- **Created by the system or by people.** The system creates a task when its event happens, such as a sample being received. People can also create a task and assign it with a deadline, such as sales scheduling a sample collection on an order.
- **Department queue.** A task routed to a department waits in that department's queue until the head of department assigns it to a person.
- **To-do list.** A person's to-do list shows their open tasks, soonest deadline first. Clicking a task opens its document at the action to take, such as entering a result or signing.
- **Lifecycle.** Every task goes through the same statuses: open, assigned, in progress, then done or cancelled. The state of the work itself, such as a sample or a result, belongs to that document.
- **Done.** A task created by the system is done when its work is done, such as when the result it asked for is approved. A task created by hand is marked done by its assignee. Done tasks move to the person's completed list.

Acceptance criteria:

- A task assigned to a person appears in their to-do list with its deadline.
- Clicking a task opens its document at its action.
- A testing task is done when its result is approved, without anyone marking it.
- Turning off automatic creation for a task type stops new tasks of that type; existing tasks are unchanged.

#### SH-11 Schedules and reminders

Tasks with a planned time and machine bookings appear on schedules, and people are reminded before they start.

| Schedule              | Shows                                                                                     |
| --------------------- | ----------------------------------------------------------------------------------------- |
| Personal schedule     | A person's planned tasks and machine bookings                                             |
| Machine schedule      | A machine's bookings and its queue                                                        |
| Test request schedule | The tasks, bookings and due dates of the samples of one test request                     |
| Outsourcing schedule  | Sample tests sent to subcontractors, with the date sent and the date results are expected |

- A reminder is sent a number of minutes before a task or booking starts, 15 by default, set by an administrator.
- A reminder is shown in the application as a pop-up, sent by email (Brevo) and pushed to the Medilab Mobile app through Firebase Cloud Messaging.
- **Notifications.** Every notification belongs to an event, such as a booking reminder, and has a key, so the same notification is never created twice. It is delivered once on each channel the person keeps on for that event; the deliveries are sent by a scheduled job (SH-09). Mandatory events, such as a password reset or a payment receipt, cannot be turned off.

Acceptance criteria:

- A booking appears on the personal schedule of the person who runs it and on the machine's schedule.
- A reminder arrives 15 minutes before a booking starts, once on each channel.

## II. External systems integration

All integrations are optional and enabled in the settings. Credentials come from configuration files (SH-03), never from the database. Every call is logged in the audit trail (SH-05), and a provider outage never loses a business action: it is queued and retried (SH-09).

### 1. Brevo (email)

The system sends all e-mail through Brevo.

- Used for: notifications, alerts, quotations and invoices with attachments, reminders and reports.
- Administrators configure the sender, the Brevo account and the templates. Templates are translatable (SH-08) and use the customer's contact (Sales documents) and notification preferences.
- Delivery status (sent, delivered, opened, bounced, failed) is recorded against the message, so staff can see whether a customer received a quotation.
- Bounced or invalid addresses are flagged on the customer's contact so that they are not used again.
- If Brevo is unavailable the message stays queued and is retried; the business action that triggered it is not rolled back.

### 2. PayOS (payments)

The system takes online payments through PayOS.

- Used for the advance and final invoices. The customer pays from the portal or from a payment link in an e-mail.
- Payment methods are whatever PayOS offers (for example bank transfer by QR code); administrators enable or disable them in the settings, and the portal shows only those enabled.
- A payment is confirmed only by the provider's signed notification, never by the customer's browser returning to the website. The signature is verified, and a repeated notification creates no second payment.
- A confirmed payment is recorded against the invoice and updates its payment status automatically; partial payments are supported.
- The status of each payment (created, pending, paid, failed, cancelled, expired) is stored and shown to the accountant.
- If notifications are missed, a scheduled job (SH-09) asks the provider for the status of pending payments.
- Refunds are outside this integration.

### 3. Viettel Sign (digital signature)

The system digitally signs printed documents through Viettel Sign (SH-04). It does not ask users to sign; approval in the system already did that.

- Administrators configure the provider account and the laboratory's certificate, and see its expiry. An expired or revoked certificate stops digital signing and alerts administrators before and when it happens.
- When a fully signed document is printed or exported, the system sends the PDF to the provider, which applies the digital signature automatically and returns the signed file; the file is stored with the document and the signature details.
- Verification of a signed PDF checks the digital signature against the provider and the approval records of the document, and shows the result to anyone who opens the document.
- If the provider is unavailable, the document is not issued as signed; the user is told and can retry, and the request is retried automatically (SH-09). No document is shown as digitally signed unless the provider confirmed it.

### 4. Firebase Cloud Messaging (mobile push)

The system pushes reminders and notifications to the Medilab Mobile app through Firebase Cloud Messaging (SH-11).

- When a person signs in on the app, the app registers the device's token for their user; signing out turns the token off.
- A push sent to a token Firebase rejects turns that token off.
- The Firebase credentials are configuration, not data (SH-03).

## III. Related documents

- [Overview](index.md)
- [E-commerce module](ecommerce_module/overview.md)
- [Inventory module](inventory_module/overview.md)
- [Laboratory module](laboratory_module/overview.md)
