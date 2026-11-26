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
| 16 | SF-04 Sample retention, return and disposal | The tester disposes of the sample after the report. |
| 17 | SF-09 Customer support and feedback, support | The customer opens a support request about the order, Sales answers and the customer rates the order. |
| 18 | SF-02 Order cancellation | The customer reorders, Sales confirms the reorder, the customer requests its cancellation and Sales accepts. |

## Flow plans

Each plan lists what the flow receives, what it hands over, its steps as clicks, the data it types and what does not connect.

- [WF-02 Sample reception and handover](wf-02.md)
- [WF-04 Result entry and approval](wf-04.md)
- [WF-06 Report signing, release and delivery](wf-06.md)
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
