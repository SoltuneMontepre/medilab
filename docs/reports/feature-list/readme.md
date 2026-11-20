# Feature list

The features of MediLab, F-01 to F-58. A feature is one capability of the system, built and tested as one piece. Its three acceptance criteria are its test cases: Main is `TC-Fnn-01`, Rule is `TC-Fnn-02` and Exception is `TC-Fnn-03`.

The mandatory features are the 25 of section 3 of the [Review 2 commitment (BM04) v1.1](../BM04_hoang/SWP490_GFA26SE153_R2_Commitment_v1.1.pdf). Their name, actor, criteria, workflow and owner are the text of that section.

Feature IDs are permanent. A new feature takes the next unused number, and a removed feature's ID is never reused.

The Workflow column names the one flow that owns a feature. [Business flows](../../functional/business-flows.md) lists the feature under that flow, and its browser tests live in that flow's folder, as the [browser test layout](../../../src/tests/cypress/e2e/README.md) describes. `Every flow` marks a feature of a shared requirement that every flow uses.

## Files

- [feature_list.py](feature_list.py): reads the tables of this document, checks them against Business flows and writes the workbooks
- [business_flows.py](business_flows.py): checks that Business flows lists the features each flow owns
- [comparison.py](comparison.py): compares the workbook with its previous version, word by word
- [SWP490_GFA26SE153_Feature_List_v1.1.xlsx](../BM04_hoang/SWP490_GFA26SE153_Feature_List_v1.1.xlsx): every feature, in the columns of section 3 of BM04
- [SWP490_GFA26SE153_Feature_List_v1.0-vs-v1.1.xlsx](../BM04_hoang/SWP490_GFA26SE153_Feature_List_v1.0-vs-v1.1.xlsx) and [its PDF](../BM04_hoang/SWP490_GFA26SE153_Feature_List_v1.0-vs-v1.1.pdf): the changes since [version 1.0](../BM04_hoang/SWP490_GFA26SE153_Feature_List_v1.0.xlsx), removed words struck through in red and added words underlined in blue

After changing a feature or the flow that owns it, regenerate the workbooks:

```bash
uv run --with openpyxl python docs/reports/feature-list/feature_list.py
```

The script stops without writing when the tables are inconsistent or Business flows lists other features for a flow. It prints the PDF with Chrome or Edge, and leaves the PDF unchanged when neither is installed.

## Features

| ID                                                                      | Feature                                                    | Actor                                     | Workflow   | Mandatory | Owner               |
| ----------------------------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------- | ---------- | --------- | ------------------- |
| [F-01](#f-01-catalog-structure-codes-and-archiving)                     | Catalog structure, codes and archiving                     | Administrator                             | SF-08      | No        |                     |
| [F-02](#f-02-prices-taxes-and-service-packages)                         | Prices, taxes and service packages                         | Administrator                             | SF-08      | No        |                     |
| [F-03](#f-03-customer-accounts-and-profiles)                            | Customer accounts and profiles                             | Customer, Sales                           | SF-09      | No        |                     |
| [F-04](#f-04-portal-cart-drafts-and-reorder)                            | Portal cart, drafts and reorder                            | Customer                                  | WF-01      | Yes       | Lê Sỹ Tuyền         |
| [F-05](#f-05-order-claiming-and-orders-on-behalf)                       | Order claiming and orders on behalf                        | Sales                                     | WF-01      | Yes       | Lê Sỹ Tuyền         |
| [F-06](#f-06-quotation-and-revisions)                                   | Quotation and revisions                                    | Sales                                     | WF-01      | Yes       | Lê Sỹ Tuyền         |
| [F-07](#f-07-order-templates)                                           | Order templates                                            | Sales                                     | WF-01      | No        |                     |
| [F-08](#f-08-estimated-result-date-and-priority-check)                  | Estimated result date and priority check                   | Sales, Customer                           | SF-07      | No        |                     |
| [F-09](#f-09-advance-invoice-and-online-payment)                        | Advance invoice and online payment                         | Customer                                  | WF-01      | Yes       | Lê Sỹ Tuyền         |
| [F-10](#f-10-quotation-approval-and-order-confirmation)                 | Quotation approval and order confirmation                  | Sales, Head of Sales                      | WF-01      | Yes       | Lê Sỹ Tuyền         |
| [F-11](#f-11-order-cancellation)                                        | Order cancellation                                         | Customer, Sales                           | SF-02      | No        |                     |
| [F-12](#f-12-invoices-and-adjustment-invoices)                          | Invoices and adjustment invoices                           | Accountant                                | SF-01      | No        |                     |
| [F-13](#f-13-payment-confirmation-and-reconciliation)                   | Payment confirmation and reconciliation                    | Accountant                                | SF-01      | No        |                     |
| [F-14](#f-14-finance-reports-and-sales-analytics)                       | Finance reports and sales analytics                        | Accountant, Sales                         | SF-01      | No        |                     |
| [F-15](#f-15-test-requests-and-lab-codes)                               | Test requests and lab codes                                | Sample delivery staff                     | WF-02      | Yes       | Nguyễn Nam Hoàng    |
| [F-16](#f-16-sample-collection-and-handover-record)                     | Sample collection and handover record                      | Sample delivery staff, Customer           | WF-02      | Yes       | Nguyễn Nam Hoàng    |
| [F-17](#f-17-reception-labels-and-department-handover)                  | Reception, labels and department handover                  | Sample delivery staff, Head of department | WF-02      | Yes       | Nguyễn Nam Hoàng    |
| [F-18](#f-18-insufficient-and-rejected-samples)                         | Insufficient and rejected samples                          | Sample delivery staff, Head of department | WF-02      | Yes       | Nguyễn Nam Hoàng    |
| [F-19](#f-19-people-roles-and-permissions)                              | People, roles and permissions                              | Administrator                             | SF-08      | No        |                     |
| [F-20](#f-20-machines-calibration-and-maintenance)                      | Machines, calibration and maintenance                      | Administrator                             | SF-05      | No        |                     |
| [F-21](#f-21-locations-and-rooms)                                       | Locations and rooms                                        | Administrator                             | SF-08      | No        |                     |
| [F-22](#f-22-settings-and-thresholds)                                   | Settings and thresholds                                    | Administrator                             | SF-08      | No        |                     |
| [F-23](#f-23-task-assignment-and-claiming)                              | Task assignment and claiming                               | Head of department, Tester                | WF-03      | Yes       | Phạm Anh Kiệt       |
| [F-24](#f-24-booking-proposal-and-head-approval)                        | Booking proposal and head approval                         | Head of department, Tester                | WF-03      | Yes       | Phạm Anh Kiệt       |
| [F-25](#f-25-schedules-and-reminders)                                   | Schedules and reminders                                    | Tester, Sample delivery staff             | WF-03      | Yes       | Phạm Anh Kiệt       |
| [F-26](#f-26-room-booking-with-the-machine)                             | Room booking with the machine                              | Tester                                    | WF-03      | No        |                     |
| [F-27](#f-27-urgent-tests-and-bumping)                                  | Urgent tests and bumping                                   | Tester, Head of department                | SF-10      | No        |                     |
| [F-28](#f-28-deadline-and-machine-warnings)                             | Deadline and machine warnings                              | Tester, Head of department                | SF-10      | No        |                     |
| [F-29](#f-29-test-parameters-and-ways-of-testing)                       | Test parameters and ways of testing                        | Administrator                             | SF-08      | No        |                     |
| [F-30](#f-30-testing-method-steps)                                      | Testing method steps                                       | Administrator, Tester                     | WF-04      | Yes       | Đinh Gia Huy        |
| [F-31](#f-31-chemicals)                                                 | Chemicals                                                  | Administrator                             | SF-08      | No        |                     |
| [F-32](#f-32-regulations-and-limits)                                    | Regulations and limits                                     | Administrator, Tester                     | WF-04      | Yes       | Đinh Gia Huy        |
| [F-33](#f-33-approval-chains-and-signing)                               | Approval chains and signing                                | Administrator, signers                    | SF-08      | No        |                     |
| [F-34](#f-34-result-entry-and-approval)                                 | Result entry and approval                                  | Tester, Head of department                | WF-04      | Yes       | Đinh Gia Huy        |
| [F-35](#f-35-unusual-result-warning)                                    | Unusual result warning                                     | Tester                                    | WF-04      | Yes       | Đinh Gia Huy        |
| [F-36](#f-36-sample-test-cancellation)                                  | Sample test cancellation                                   | Head of department                        | WF-04      | Yes       | Đinh Gia Huy        |
| [F-37](#f-37-subcontractors-and-accreditation-renewal)                  | Subcontractors and accreditation renewal                   | Administrator                             | SF-06      | No        |                     |
| [F-38](#f-38-outsourcing-suggestions-urgent-outsourcing-and-dispatches) | Outsourcing suggestions, urgent outsourcing and dispatches | Head of department, Sample delivery staff | WF-05      | Yes       | Lê Nguyễn Hoàng Anh |
| [F-39](#f-39-direct-outsourcing)                                        | Direct outsourcing                                         | Head of department                        | WF-05      | No        |                     |
| [F-40](#f-40-subcontractor-results)                                     | Subcontractor results                                      | Subcontractor                             | WF-05      | Yes       | Lê Nguyễn Hoàng Anh |
| [F-41](#f-41-accreditation-certificates)                                | Accreditation certificates                                 | Administrator                             | SF-06      | No        |                     |
| [F-42](#f-42-quality-registrations-and-expiry-warning)                  | Quality registrations and expiry warning                   | Administrator                             | SF-06      | No        |                     |
| [F-43](#f-43-report-signing-and-digital-signature)                      | Report signing and digital signature                       | Lab head                                  | WF-06      | Yes       | Phạm Anh Kiệt       |
| [F-44](#f-44-document-locking)                                          | Document locking                                           | Every user                                | Every flow | No        |                     |
| [F-45](#f-45-report-delivery-and-download)                              | Report delivery and download                               | Sample delivery staff, Customer           | WF-06      | Yes       | Phạm Anh Kiệt       |
| [F-46](#f-46-change-requests)                                           | Change requests                                            | Tester, Lab head                          | SF-03      | No        |                     |
| [F-47](#f-47-notifications-and-preferences)                             | Notifications and preferences                              | Customer                                  | WF-06      | Yes       | Phạm Anh Kiệt       |
| [F-48](#f-48-order-tracking-support-and-feedback)                       | Order tracking, support and feedback                       | Customer, Sales                           | SF-09      | No        |                     |
| [F-49](#f-49-languages-and-bilingual-reports)                           | Languages and bilingual reports                            | Every user                                | WF-06      | No        |                     |
| [F-50](#f-50-sample-retention-and-disposal)                             | Sample retention and disposal                              | Tester                                    | SF-04      | No        |                     |
| [F-51](#f-51-audit-trail)                                               | Audit trail                                                | Administrator                             | Every flow | No        |                     |
| [F-52](#f-52-scheduled-jobs-and-cleanup)                                | Scheduled jobs and cleanup                                 | Administrator                             | Every flow | No        |                     |
| [F-53](#f-53-laboratory-folders-and-sync)                               | Laboratory folders and sync                                | Tester                                    | WF-04      | Yes       | Đinh Gia Huy        |
| [F-54](#f-54-file-versions-conflicts-and-restore)                       | File versions, conflicts and restore                       | Tester                                    | WF-04      | Yes       | Đinh Gia Huy        |
| [F-55](#f-55-online-editing)                                            | Online editing                                             | Tester                                    | WF-04      | No        |                     |
| [F-56](#f-56-file-locks)                                                | File locks                                                 | Tester, Administrator                     | WF-04      | No        |                     |
| [F-57](#f-57-sample-folders-and-signing-file-versions)                  | Sample folders and signing file versions                   | Head of department                        | WF-04      | Yes       | Đinh Gia Huy        |
| [F-58](#f-58-devices-and-folder-administration)                         | Devices and folder administration                          | Administrator                             | SF-11      | No        |                     |

## Acceptance criteria

### F-01 Catalog structure, codes and archiving

- TC-F01-01 Main: A parameter in a sub-group appears when filtering by its parent group.
- TC-F01-02 Rule: A record without a code gets one from its sequence; a code already used is refused.
- TC-F01-03 Exception: Archiving a record still in use is refused with a message listing what uses it.

### F-02 Prices, taxes and service packages

- TC-F02-01 Main: A quotation shows each line's price and the VAT rate in force on its date.
- TC-F02-02 Rule: The order's invoices keep the quotation's rate after the VAT period ends; overlapping rate periods are refused.
- TC-F02-03 Exception: A parameter without a price and tax cannot be added to a cart or quotation.

### F-03 Customer accounts and profiles

- TC-F03-01 Main: A newly registered customer signs in and sees only their own documents.
- TC-F03-02 Rule: Merging duplicate profiles keeps every order on the remaining one; a used password reset link stops working.
- TC-F03-03 Exception: Opening another customer's quotation, invoice or result is denied.

### F-04 Portal cart, drafts and reorder

- TC-F04-01 Main: A visitor fills a cart without signing in and submits it with their details.
- TC-F04-02 Rule: A package is ordered whole; reordering creates a draft at current prices and leaves the original unchanged.
- TC-F04-03 Exception: Submitting without an e-mail address is refused.

### F-05 Order claiming and orders on behalf

- TC-F05-01 Main: A salesperson claims a submitted order, or creates one for a customer who called.
- TC-F05-02 Rule: A salesperson sees only their orders and the unclaimed queue; the Head of Sales sees all.
- TC-F05-03 Exception: An order already claimed cannot be claimed by another salesperson.

### F-06 Quotation and revisions

- TC-F06-01 Main: Sales confirms the ways and the expected samples calculated from the sampling requirements, applies a percentage discount and sends the quotation.
- TC-F06-02 Rule: Each item copies its price, discount and tax rate, so a sent quotation never changes; a revision makes the old version read-only.
- TC-F06-03 Exception: A quotation without tests cannot be sent, nor one above the Head of Sales's thresholds before it is approved.

### F-07 Order templates

- TC-F07-01 Main: A returning customer's order is saved as a template and reused for the next order.
- TC-F07-02 Rule: A template keeps no prices; reusing it creates an unsent draft at current prices and package contents.
- TC-F07-03 Exception: A salesperson cannot open another salesperson's templates.

### F-08 Estimated result date and priority check

- TC-F08-01 Main: Adding a parameter to a quotation updates its estimated return date.
- TC-F08-02 Rule: An accepted priority order makes its tests urgent when they are created.
- TC-F08-03 Exception: An earlier date the laboratory cannot meet is not accepted; the check shows the earliest date it can.

### F-09 Advance invoice and online payment

- TC-F09-01 Main: Sending a quotation with an advance creates exactly one posted advance invoice; paying it accepts the quotation.
- TC-F09-02 Rule: Online payment accepts any amount up to the remaining balance; a bank transfer or cash payment counts once the accountant confirms it.
- TC-F09-03 Exception: A repeated PayOS notification records no second payment.

### F-10 Quotation approval and order confirmation

- TC-F10-01 Main: A quotation above the Head of Sales's thresholds is approved before it is sent; confirming the accepted order creates its test request with the calculated expected samples.
- TC-F10-02 Rule: Quotations within the thresholds and confirmed orders need no approval; the customer pays the balance before testing unless they may order on credit.
- TC-F10-03 Exception: The salesperson who requested approval cannot approve; a declined quotation goes back to Sales with the reason; a quotation awaiting approval cannot be edited.

### F-11 Order cancellation

- TC-F11-01 Main: A customer cancels an unconfirmed order, or requests cancellation of a confirmed one, which sales accepts.
- TC-F11-02 Rule: Accepting cancels the order and everything under it; a paid advance is not refunded automatically.
- TC-F11-03 Exception: A request without a reason is refused; cancelling once any testing is completed is blocked.

### F-12 Invoices and adjustment invoices

- TC-F12-01 Main: The final invoice totals the order minus the advance and is e-mailed and downloadable as PDF.
- TC-F12-02 Rule: A posted invoice is never edited: an adjustment of −500,000 VND on 5,000,000 VND leaves 4,500,000 VND owed.
- TC-F12-03 Exception: An unpaid invoice past its due date reminds the customer at each interval, once per reminder.

### F-13 Payment confirmation and reconciliation

- TC-F13-01 Main: The accountant confirms a payment sales recorded, and a receipt is issued.
- TC-F13-02 Rule: Only confirmed payments count; a PayOS transaction with no payment is flagged; a locked day cannot change.
- TC-F13-03 Exception: A payment above the remaining amount is refused; a rejected payment tells the salesperson the reason.

### F-14 Finance reports and sales analytics

- TC-F14-01 Main: Revenue, outstanding and cash-flow reports for a period export to a spreadsheet.
- TC-F14-02 Rule: Revenue excludes VAT and counts on the invoice date; only confirmed payments count as collected.
- TC-F14-03 Exception: A salesperson sees only their own pipeline and performance.

### F-15 Test requests and lab codes

- TC-F15-01 Main: Staff create a test request with its samples, parameters, expected date and report delivery.
- TC-F15-02 Rule: Each sample gets a unique lab code, numbered again each month; a request staff create skips the paid step.
- TC-F15-03 Exception: Confirming without a sample, or a sample without a parameter, is refused; testers see only the lab code.

### F-16 Sample collection and handover record

- TC-F16-01 Main: Staff claim the collection task and plan its time; it appears on their schedule and to-do list, with a reminder.
- TC-F16-02 Rule: The customer confirms the actual samples and signs the handover record before labels are printed; signing stores the signature, time and device and e-mails the PDF.
- TC-F16-03 Exception: A signed handover record cannot be edited; a correction is a new record.

### F-17 Reception, labels and department handover

- TC-F17-01 Main: The condition is checked first; a sample in good condition is recorded as received with its time, amount and storage, and one testing task per sample test is queued.
- TC-F17-02 Rule: The label shows the lab code, request code, due date and QR code, never the customer.
- TC-F17-03 Exception: A label scanned by a person outside the department is refused.

### F-18 Insufficient and rejected samples

- TC-F18-01 Main: An insufficient sample goes on hold before receipt and its head of department is told.
- TC-F18-02 Rule: Asking for more creates a collection task recording who asked and when; more sample returns it to received.
- TC-F18-03 Exception: An unusable sample is rejected by the system with its condition note and gets no testing task.

### F-19 People, roles and permissions

- TC-F19-01 Main: A person gets every permission of their roles plus their own.
- TC-F19-02 Rule: A department or team scope hides other departments' or teams' records; a person's team belongs to their department.
- TC-F19-03 Exception: A user without a permission sees no menu or button for it, and the API refuses it.

### F-20 Machines, calibration and maintenance

- TC-F20-01 Main: Recording a calibration with a new due date makes a machine usable.
- TC-F20-02 Rule: A machine past its calibration date, under repair or retired gets no booking.
- TC-F20-03 Exception: A machine with a queued, scheduled or running booking cannot be archived.

### F-21 Locations and rooms

- TC-F21-01 Main: A location saved under a parent shows as a point on the parent's map.
- TC-F21-02 Rule: Bookings of one location never overlap; a location that is not bookable cannot be booked.
- TC-F21-03 Exception: A location cannot be its own ancestor; a location in use is archived, never deleted.

### F-22 Settings and thresholds

- TC-F22-01 Main: Administrators set the urgency hours, the due-date safety margin and the warning days.
- TC-F22-02 Rule: A setting applies to future documents only: due dates already worked out keep the old margin.
- TC-F22-03 Exception: A missing optional setting falls back to its documented default; every change is audited.

### F-23 Task assignment and claiming

- TC-F23-01 Main: Assigning a sample assigns all its testing tasks in the department to one person, who is notified.
- TC-F23-02 Rule: An assigned task leaves the queue and appears in the assignee's to-do list.
- TC-F23-03 Exception: A claimed task cannot be claimed again; another department's task cannot be claimed; reassigning without a reason is refused.

### F-24 Booking proposal and head approval

- TC-F24-01 Main: The system proposes a booking of the agreed way on the fit machine that finishes soonest before the due date; when it is feasible, the head approves it, the tester is notified, and the tester, required locations and machine are reserved together.
- TC-F24-02 Rule: A booking takes the run time rounded up to 15-minute slots; urgent tests first, then first in first out.
- TC-F24-03 Exception: Bookings of one machine never overlap; with no feasible booking the head reviews other dates, planned OverTime or outsourcing.

### F-25 Schedules and reminders

- TC-F25-01 Main: A booking appears on the person's calendar, the machine's schedule and the to-do list.
- TC-F25-02 Rule: A reminder arrives 15 minutes before it starts, once on each channel.
- TC-F25-03 Exception: An event the administrator turned off notifies nobody; a mandatory event cannot be turned off.

### F-26 Room booking with the machine

- TC-F26-01 Main: A run with a step in a bookable room is planned only when its tester, the room and any required machine are all available.
- TC-F26-02 Rule: The room booking shows on the tester's calendar and the room's schedule.
- TC-F26-03 Exception: Moving or cancelling a not-started run changes its required reservations together; a run-associated room reservation cannot be changed independently.

### F-27 Urgent tests and bumping

- TC-F27-01 Main: A test marked urgent with a reason gets the next free slot before tests that are not urgent.
- TC-F27-02 Rule: Bumping gives an urgent test the earliest fit slot; moved bookings are planned again and their people told; a running booking never moves.
- TC-F27-03 Exception: Marking urgent or bumping without a reason, and bumping non-urgent work, is refused; a tester cannot mark another person's test urgent.

### F-28 Deadline and machine warnings

- TC-F28-01 Main: A test that cannot meet its internal due date is at risk; its tester and head receive an initial notice and daily consolidated summaries until resolved.
- TC-F28-02 Rule: A booking that ended without a result makes its test at risk; entering the result clears it.
- TC-F28-03 Exception: Separate calibration/maintenance/recent-repair warning windows warn; they never bypass a booking block.

### F-29 Test parameters and ways of testing

- TC-F29-01 Main: A parameter saves several methods, groups and sample types.
- TC-F29-02 Rule: Its main group must be one of its groups; an in-house way of testing needs a department.
- TC-F29-03 Exception: An active pair with the same parameter, method and subcontractor is refused; a parameter is archived, never deleted.

### F-30 Testing method steps

- TC-F30-01 Main: The tester sees the method's steps with number, duration, what to do and note, in number order.
- TC-F30-02 Rule: Two steps of one method cannot share a number.
- TC-F30-03 Exception: A tester cannot change a step.

### F-31 Chemicals

- TC-F31-01 Main: A method shows the chemicals it uses, and a chemical the methods that use it.
- TC-F31-02 Rule: A chemical records its CAS number, formula, grade and storage conditions.
- TC-F31-03 Exception: A chemical that a method uses cannot be deleted.

### F-32 Regulations and limits

- TC-F32-01 Main: When a regulation comparison is requested, the result shows the related limit copied with its unit and is assessed.
- TC-F32-02 Rule: Later changes to the regulation leave existing results unchanged; a regulation holds one limit per parameter.
- TC-F32-03 Exception: A result with a requested comparison cannot be sent without its assessment.

### F-33 Approval chains and signing

- TC-F33-01 Main: Each document type is signed through its chain, level by level, and a signed document is locked.
- TC-F33-02 Rule: A signer withdraws only after every signature given after theirs has been withdrawn, and never after the process completes.
- TC-F33-03 Exception: A document type cannot have two chains for one purpose, nor a chain two levels in one position.

### F-34 Result entry and approval

- TC-F34-01 Main: The tester enters, signs and sends a result, which closes the testing task; the head approves it.
- TC-F34-02 Rule: A rejected result is kept, and a retest adds a new result with a new booking; only the latest is sent for approval.
- TC-F34-03 Exception: A tester cannot approve their own result, but the head may approve an entry they made; a rejection opens a new testing task and tells the tester the reason.

### F-35 Unusual result warning

- TC-F35-01 Main: A numeric result far from approved results of the same parameter, way of testing and sample type warns before sending.
- TC-F35-02 Rule: A result near the regulation limit warns; with too few approved results only the limit check runs.
- TC-F35-03 Exception: Sending anyway keeps the warning, which the approving head sees; the warning never names a customer.

### F-36 Sample test cancellation

- TC-F36-01 Main: The head cancels a waiting, assigned or testing sample test with a reason; its task and bookings are cancelled.
- TC-F36-02 Rule: A sample whose remaining tests are approved completes; a cancelled test is left out of the report.
- TC-F36-03 Exception: Cancelling without a reason, or a test with an approved result, is refused.

### F-37 Subcontractors and accreditation renewal

- TC-F37-01 Main: A subcontractor with a valid accreditation is chosen on a way of testing.
- TC-F37-02 Rule: A pair keeps its subcontractor after the accreditation expires; renewing the date makes it selectable again.
- TC-F37-03 Exception: An archived subcontractor, or one whose accreditation expired, cannot be chosen.

### F-38 Outsourcing suggestions, urgent outsourcing and dispatches

- TC-F38-01 Main: Accepting an outsourcing suggestion, or outsourcing a test urgently with a reason, puts its sample tests in a dispatch; when staff carry it, the system records the date sent, who took it and the expected date.
- TC-F38-02 Rule: Only a subcontracted way with the test's parameter and method can be chosen; the customer is neither told nor asked.
- TC-F38-03 Exception: A dispatch whose tests have results cannot be cancelled; when a delivery fails, the dispatch, still draft, is cancelled, its tests stay outsourced and the same sample goes back to sample reception.

### F-39 Direct outsourcing

- TC-F39-01 Main: The head initiates emergency outsourcing with a reason; a changed accepted way waits for the customer-agreed revised quotation.
- TC-F39-02 Rule: An emergency proposal does not require a scheduler suggestion, but does require customer agreement before replacing an accepted way.
- TC-F39-03 Exception: Outsourcing without a reason, or a test already in testing, is refused.

### F-40 Subcontractor results

- TC-F40-01 Main: The subcontractor receives the samples and enters the results of the tests sent to it, and the head is notified.
- TC-F40-02 Rule: The result shows that user as its author and goes straight to the head for approval like any other.
- TC-F40-03 Exception: A subcontractor user sees only its own dispatches and never a sample's customer.

### F-41 Accreditation certificates

- TC-F41-01 Main: Importing 30 scope rows links existing methods unchanged or creates missing methods, and retains each row's method, parameters and sample types on the certificate.
- TC-F41-02 Rule: An in-house sample test is accredited only while a valid certificate scope line covers its method, parameter and exact or ancestor sample type; subcontracted tests remain outside the laboratory's accreditation scope.
- TC-F41-03 Exception: Importing a row without a code refuses the whole import and creates nothing; an omitted title defaults to the code.

### F-42 Quality registrations and expiry warning

- TC-F42-01 Main: A covered parameter prints the dossier's mark on the report.
- TC-F42-02 Rule: Administrators are warned the configured days before a dossier expires and on the day it does.
- TC-F42-03 Exception: After its last valid day a dossier's mark is no longer printed.

### F-43 Report signing and digital signature

- TC-F43-01 Main: When every test of the request is approved or cancelled, the system creates the read-only draft report, validates its data, reserves a number and prepares the PDF in the request's language; the lab head reviews it, the PDF is digitally signed and stored, and issue makes the number official.
- TC-F43-02 Rule: The report prints the approving heads and the lab head, not the testers, and leaves out cancelled tests.
- TC-F43-03 Exception: With Viettel Sign down nothing is marked signed and signing is retried; rejecting without a reason or a named result is refused.

### F-44 Document locking

- TC-F44-01 Main: A user editing a document locks it; others can still read it and see who holds the lock.
- TC-F44-02 Rule: An abandoned lock is released after 15 minutes of inactivity.
- TC-F44-03 Exception: From the first signature a document is read-only for everyone, administrators included.

### F-45 Report delivery and download

- TC-F45-01 Main: Staff record the delivery of an issued report; an e-mail delivery sends the PDF.
- TC-F45-02 Rule: An issued report waits in the delivery list until its delivery is recorded.
- TC-F45-03 Exception: An unissued report cannot be delivered; a customer downloads only their own reports.

### F-46 Change requests

- TC-F46-01 Main: A result correction creates its linked new version. A report correction keeps the old report issued until the freshly approved replacement PDF is stored and issued; only then is it marked replaced, and both versions stay readable.
- TC-F46-02 Rule: The requester sees its status at every step: requested, approved, rejected, applied.
- TC-F46-03 Exception: A request without what to change or why is refused; a rejected one leaves the signed document untouched.

### F-47 Notifications and preferences

- TC-F47-01 Main: An issued report notifies the customer on the channels they chose.
- TC-F47-02 Rule: A new customer is notified by e-mail without configuring anything; a changed preference applies to the next notification.
- TC-F47-03 Exception: A mandatory notification cannot be turned off.

### F-48 Order tracking, support and feedback

- TC-F48-01 Main: An order shows Waiting, Testing, Completed or Cancelled to the customer.
- TC-F48-02 Rule: A reply from support sets the request to answered and notifies the customer.
- TC-F48-03 Exception: Feedback is given only on a completed order, once; no customer sees another's requests or feedback.

### F-49 Languages and bilingual reports

- TC-F49-01 Main: Every screen is available in Vietnamese and English.
- TC-F49-02 Rule: A report is issued in Vietnamese, English or both side by side, as its request says.
- TC-F49-03 Exception: Adding a language does not affect users of other languages.

### F-50 Sample retention and disposal

- TC-F50-01 Main: A tester records a sample's disposal with when, by whom and how.
- TC-F50-02 Rule: A sample whose retention ends within the reminder days is on the daily to-do; a disposed one is not.
- TC-F50-03 Exception: Disposing with no method on the sample or its type is refused; a disposal cannot be undone.

### F-51 Audit trail

- TC-F51-01 Main: A price change records who changed it, when, and the old and new value.
- TC-F51-02 Rule: The history of a test request includes its samples and sample tests; personal data in changed fields is masked.
- TC-F51-03 Exception: No user, administrators included, can edit or delete an entry.

### F-52 Scheduled jobs and cleanup

- TC-F52-01 Main: Administrators see every job with its last and next run, and can run one by hand.
- TC-F52-02 Rule: A failed job is retried with a growing delay; running a job twice never sends a duplicate.
- TC-F52-03 Exception: The cleanup job archives audit entries to a file before removing them, and never removes business records.

### F-53 Laboratory folders and sync

- TC-F53-01 Main: Saving a file in a folder bound in Medilab Sync adds a version with the tester, the computer, the size and the hash.
- TC-F53-02 Rule: Only files matching the folder's sync rules are uploaded; content the file already has is not stored twice.
- TC-F53-03 Exception: A person who is not a member of the folder, or cannot see its sample, gets nothing from it.

### F-54 File versions, conflicts and restore

- TC-F54-01 Main: Restoring version 3 of a file with 5 versions adds version 6 with the content of version 3.
- TC-F54-02 Rule: A file uploaded from an older version is kept as a conflict version and the current version stays.
- TC-F54-03 Exception: No one can change or delete a version, its hash or its size.

### F-55 Online editing

- TC-F55-01 Main: Saving an Office result file in the browser editor adds a version marked as edited online.
- TC-F55-02 Rule: A second person opening the file joins the same editing session.
- TC-F55-03 Exception: A raw-data file cannot be edited online; with the editing service down, syncing and restore keep working.

### F-56 File locks

- TC-F56-01 Main: A tester locks a working file that is not an Office document while editing it.
- TC-F56-02 Rule: A lock expires after 30 minutes unless renewed.
- TC-F56-03 Exception: Uploading a file someone else has locked is refused; an administrator's release is recorded in the audit trail.

### F-57 Sample folders and signing file versions

- TC-F57-01 Main: Creating a sample's folders adds its raw-data and result folders.
- TC-F57-02 Rule: A signature belongs to one version and its hash; a newer version shows as not signed.
- TC-F57-03 Exception: Creating the folders twice adds no second folder; rejecting a version without a reason is refused.

### F-58 Devices and folder administration

- TC-F58-01 Main: Revoking a device stops it at once, and the person's other devices keep working.
- TC-F58-02 Rule: Changing a folder's owner keeps the previous owner as a member; archiving sets its retention date.
- TC-F58-03 Exception: A turned-off folder refuses every upload and still allows downloads.

## Related documents

- [Review 2 commitment (BM04) v1.1](../BM04_hoang/SWP490_GFA26SE153_R2_Commitment_v1.1.pdf)
- [Business flows](../../functional/business-flows.md)
- [Reports](../readme.md)
