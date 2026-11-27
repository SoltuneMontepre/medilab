# Connected journey

One story carried through every business flow by clicks alone, to check that the flows of [Business flows](../../functional/business-flows.md) connect through the screens. Each flow starts from the record the flow before it left and finds it as its actor does: a menu, a search, a to-do or a portal link. The Playwright project in `src/tests/playwright/` runs the story.

## Story

Every name the journey types carries a run tag, written `{TAG}`, so the journey runs again on the same database.

| Step | Flow | What happens |
| ---- | ---- | ------------ |
| 1 | SF-08 Laboratory setup | The administrator adds the test parameter `Journey nitrate {TAG}` with its way of testing, sample-type applicability, price and tax. The Lab Head authorizes the tester for it. |
| 2 | SF-06 Accreditation and registration renewal | The administrator renews the accreditation of the subcontractor WF-05 uses and adds a certificate scope line that covers the new parameter. |
| 3 | SF-09 Customer support and feedback, account | The customer `Journey Foods {TAG}` registers on the portal and completes the profile. |
| 4 | WF-01 Order to confirmed test request | The customer orders the new parameter and a demo parameter for one sample. Sales claims, sends the quotation with an advance, records the payment, the accountant confirms it and Sales confirms the order. |
| 5 | SF-07 Result dates and priority orders | Inside step 4, the customer asks for a date and priority, and Sales accepts. |
| 6 | WF-02 Sample reception and handover | Sample delivery staff receive the sample, the customer signs the handover record and the head of department scans the label. |
| 7 | SF-11 Laboratory file administration | The head of department creates the sample's folders and adds the tester as member. |
| 8 | WF-03 Testing assignment and scheduling | The head assigns the tester and approves the proposed booking. |
| 9 | SF-10 Scheduling plan and revisions | The test is marked urgent and its booking moved. |
| 10 | SF-05 Machine calibration and unavailability | The booked machine goes under repair and returns to use; the booking ends scheduled again. |
| 11 | WF-04 Result entry and approval | The tester enters, sends and signs the result; the head approves it. |
| 12 | WF-05 Outsourced testing | The second test is outsourced, dispatched, answered by the subcontractor on the portal and approved. |
| 13 | SF-01 Invoicing and payment collection | The balance is paid and confirmed; invoices and receipts are downloadable. |
| 14 | WF-06 Report signing, release and delivery | The Lab Head approves the report, it is issued and delivered, and the customer downloads it. |
| 15 | SF-03 Change request on a signed document | A change request on the issued report produces a replacement through WF-06. |
| 16 | SF-04 Sample retention, return and disposal | The sample type keeps the sample 30 days after the report, so disposing of it and returning it are refused until its retention ends. |
| 17 | SF-09 Customer support and feedback, support | The customer opens a support request about the order, Sales answers and the customer rates the order. |
| 18 | SF-02 Order cancellation | The customer reorders, Sales confirms the reorder, the customer requests its cancellation and Sales accepts; staff then cancel the reorder's test request by hand. |

## Results

The whole story runs from a fresh demo database with `task test:journey` in about 13 minutes. Every flow starts from what the flow before it left, and every flow walks to its end. A step the screens do not allow, or that breaks a documented rule, is checked softly: the report shows it red and the journey goes on.

| Spec | Flow | Red steps |
| ---- | ---- | --------- |
| 01 | SF-08 Laboratory setup | none |
| 02 | SF-06 Accreditation and registration renewal | none |
| 03 | SF-09 Customer support and feedback, account | none |
| 04 | WF-01 Order to confirmed test request, with SF-07 | Accept priority answers with a server error |
| 05 | WF-02 Sample reception and handover | no way to take the customer's signature in the browser, on the staff form or the portal |
| 06 | SF-11 Laboratory file administration | the folder owner cannot add a member; no file can be added to a folder from the browser |
| 07 | WF-03 Testing assignment and scheduling | a notice reaches an open browser only after a reload |
| 08 | SF-10 Scheduling plan and revisions | none |
| 09 | SF-05 Machine calibration and unavailability | nobody is told that the machine's downtime moved the booking |
| 10 | WF-04 Result entry and approval | no result file can be saved from the browser; a result of a booking started early starts in the future |
| 11 | WF-05 Outsourced testing | the subcontractor's result waits for a tester to send it before the head can approve it |
| 12 | SF-01 Invoicing and payment collection | no screen links to the payment receipt |
| 13 | WF-06 Report signing, release and delivery | the report prints no accreditation mark |
| 14 | SF-03 Change request on a signed document | the Lab Head has no notice or task for the change request |
| 15 | SF-04 Sample retention, return and disposal | disposal and return after the retention period, which no click can reach |
| 16 | SF-09 Customer support and feedback, support | none |
| 17 | SF-02 Order cancellation | accepting the cancellation leaves the test request Paid and its sample Expected |

## Where the flows do not connect

Each item names the plan that holds its evidence.

- **Priority orders cannot be accepted.** Accept priority stops with a server error, because the feasibility check searches bookings by a test's priority, which is not stored. Every priority request can only be declined, so no test becomes urgent through SF-07 ([SF-07](sf-07.md)).
- **A cancelled order keeps its test request.** Accepting a cancellation cancels the order only; staff must cancel the test request and its samples by hand ([SF-02](sf-02.md)).
- **The balance holds sample reception by default.** The Send quotation dialog preselects a balance due before sample collection, which keeps the test request from being paid until the balance is; the documents say the balance never holds collection. The journey chooses "Before the report" ([WF-01](wf-01.md), [SF-01](sf-01.md)).
- **The subcontractor's result does not reach the head.** It waits as a draft until a tester of the department sends it, and nobody is told ([WF-05](wf-05.md)).
- **Result files stay outside the browser.** No file can be added to a sample folder from the back office, so saving and signing a result file need Medilab Sync ([SF-11](sf-11.md), [WF-04](wf-04.md)).
- **The handover record cannot be signed in the browser.** It stays Draft unless the phone signs it ([WF-02](wf-02.md)).
- **Notices go missing.** In-application notices reach an open browser only after a reload; machine downtime, a head moving a booking and a raised change request tell nobody; demo staff receive notices by e-mail only, which no screen shows ([WF-03](wf-03.md), [SF-05](sf-05.md), [SF-10](sf-10.md), [SF-03](sf-03.md)).
- **Documented rules the screens do not keep.** The report prints no accreditation mark; the catalog offers a parameter before anyone is authorized for it; Head of Sales approval above the thresholds is not built; the customer cannot accept a quotation that has an advance, which turns accepted when the accountant confirms the advance; the machine has no busy state ([WF-06](wf-06.md), [SF-08](sf-08.md), [WF-01](wf-01.md), [WF-04](wf-04.md)).
- **Records hard to find.** A test request cannot be found by its order number; the payment receipt and an order's invoices have no link from the order; sample delivery staff see a dispatch only once the head names them as carrier ([WF-02](wf-02.md), [SF-01](sf-01.md), [WF-05](wf-05.md)).
- **The local editing service refused the report's conversion.** Its gateway allowed only `/ConvertService.ashx` while Odoo posts to `/converter`; it is fixed in `tools/onlyoffice/proxy.py` ([WF-06](wf-06.md)).

## Flow plans

Each plan lists what the flow receives, what it hands over, its steps as clicks, the data it types and what does not connect.

- [WF-01 Order to confirmed test request](wf-01.md)
- [WF-02 Sample reception and handover](wf-02.md)
- [WF-03 Testing assignment and scheduling](wf-03.md)
- [WF-04 Result entry and approval](wf-04.md)
- [WF-05 Outsourced testing](wf-05.md)
- [WF-06 Report signing, release and delivery](wf-06.md)
- [SF-01 Invoicing and payment collection](sf-01.md)
- [SF-02 Order cancellation](sf-02.md)
- [SF-03 Change request on a signed document](sf-03.md)
- [SF-04 Sample retention, return and disposal](sf-04.md)
- [SF-05 Machine calibration and unavailability](sf-05.md)
- [SF-06 Accreditation and registration renewal](sf-06.md)
- [SF-07 Result dates and priority orders](sf-07.md)
- [SF-08 Laboratory setup](sf-08.md)
- [SF-09 Customer support and feedback](sf-09.md)
- [SF-10 Scheduling plan and revisions](sf-10.md)
- [SF-11 Laboratory file administration](sf-11.md)

## Related documents

- [Business flows](../../functional/business-flows.md)
- [Testing conventions](../../conventions/testing.md)
- [Browser test layout](../../../src/tests/cypress/e2e/README.md)
