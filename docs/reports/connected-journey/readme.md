# Connected journey

One story carried through every business flow by clicks alone, to check that the flows of [Business flows](../../functional/business-flows.md) connect through the screens. Each flow starts from the record the flow before it left and finds it as its actor does: a menu, a search, a to-do or a portal link. The Playwright project in `src/tests/playwright/` runs the story.

## Rules

The journey goes through each flow as the business does, never in a way that makes the app work; [Testing](../../conventions/testing.md#connected-journey) states the rules. In short: each spec walks its flow's main path; an actor takes only the steps the path gives them and keeps the demo's defaults; a business step the app refuses or has no screen for fails the flow there; a later flow that needs what a failed flow did not produce is skipped with the names of what it did not receive; a step the business takes on Medilab Mobile, on Medilab Sync, by e-mail or after days pass is listed as outside the browser.

## Story

Every name the journey types carries a run tag, written `{TAG}`, so the journey runs again on the same database.

| Spec | Flow | What happens |
| ---- | ---- | ------------ |
| 01 | SF-08 Laboratory setup | The administrator adds the test parameter `Journey nitrate {TAG}` with its way of testing, sample-type applicability, price, tax, sampling requirement and a second machine; the Lab Head authorizes the tester. |
| 02 | SF-06 Accreditation and registration renewal | The administrator records a certificate and imports the scope line that covers the new parameter. |
| 03 | SF-09-A2 Customer registration | The customer `Journey Foods {TAG}` registers on the portal and completes the profile, because WF-01 needs a customer. |
| 04 | WF-01 Order to confirmed test request | The customer orders the new parameter and Lead (Pb) for one Bottled water sample, with a requested date; Sales claims, prepares and sends the quotation with an advance; the advance is paid by bank transfer (WF-01-A4, for PayOS); Sales confirms the order. |
| 04a | SF-07-A1 Priority request | The customer orders with priority and Sales accepts it. A test of its own, beside the chain. |
| 05 | WF-02 Sample reception and handover | Staff receive the sample, the customer signs the handover record on Medilab Mobile, staff print the label and the head scans it. |
| 06 | SF-11 Laboratory file administration | The head creates the sample's folders; members and binding happen in Medilab Sync. |
| 07 | WF-03 Testing assignment and scheduling | The head assigns the tester and approves the proposed booking. |
| 08 | SF-10 Scheduling plan and revisions | The head reads the booking the plan placed and its reservations. |
| 09 | SF-05 Machine calibration and unavailability | The administrator puts the booked machine under repair; the booking moves to the other machine; the tester and head are told; the head approves; the machine returns to use after a calibration. |
| 10 | WF-04 Result entry and approval | The tester starts the booking, records, sends and signs the result; the head approves it. |
| 11 | WF-05 Outsourced testing | The head accepts the outsourcing suggestion for Lead, staff carry the dispatch, the subcontractor confirms receipt and enters the result on the portal, and the head approves it. |
| 12 | SF-01 Invoicing and payment collection | The customer pays the balance by bank transfer, the accountant confirms it, and the customer downloads the invoice and the receipt. |
| 13 | WF-06 Report signing, release and delivery | The Lab Head reviews and approves the report, it is issued unsigned (WF-06-A4), delivered in person (WF-06-A1), and the customer downloads it. |
| 14 | SF-03 Change request on a signed document | The tester raises a change request on the approved result, which also opens the report's (SF-03-A3); the Lab Head approves both; the corrected result is approved and the replacement report issued. |
| 15 | SF-04 Sample retention, return and disposal | The tester reads the sample's retention end; the end, the daily to-do and the disposal wait 30 days. |
| 16 | SF-09 Customer support and feedback, support | The customer asks about the order, the order's salesperson answers, the customer reads the answer. |
| 16a | SF-09-A4 Rating | The customer rates the completed order. A test of its own. |
| 17 | SF-02 Order cancellation | The customer reorders (WF-01-A3), Sales confirms the reorder, the customer requests its cancellation, Sales accepts, and the order and its test request are cancelled. |

## Results

A run from a fresh demo database with `task test:journey`:

| Spec | Flow | Chain run | Where it stops |
| ---- | ---- | --------- | -------------- |
| 01 | SF-08 | passes | |
| 02 | SF-06 | passes | |
| 03 | SF-09-A2 | passes | |
| 04 | WF-01 | fails | Sales confirms the order with the advance verified, and the test request reads Confirmed, not Paid. |
| 04a | SF-07-A1 | fails | Accept priority answers with a server error. |
| 05 to 11 | WF-02 to WF-05 | skipped | They start from a paid test request, which WF-01 did not produce. |
| 12 | SF-01 | fails | The customer pays and the order reads paid in full, but no page links to the payment's receipt. |
| 13 to 15 | WF-06, SF-03, SF-04 | skipped | They start from completed and reported results. |
| 16 | SF-09 | passes | |
| 16a, 17 | SF-09-A4, SF-02 | skipped | They start from a completed order. |

The skipped flows were also run on their own, each from a database where an earlier version of the journey had reached their starting records by taking steps the business does not take:

| Spec | Flow | Run on its own |
| ---- | ---- | -------------- |
| 05 to 08 | WF-02, SF-11, WF-03, SF-10 | pass |
| 09 | SF-05 | fails: nobody is told that the machine's downtime moved the booking. |
| 10 | WF-04 | passes |
| 11 | WF-05 | fails: the subcontractor's result is not among the head's results to approve; it waits for a tester to send it. |
| 13, 14 | WF-06, SF-03 | pass |
| 15, 16a | SF-04, SF-09-A4 | pass |
| 17 | SF-02 | fails: after Sales accepts the cancellation, the test request still reads Confirmed. |

## Where the flows do not connect

In the order a fix would let the chain go further:

1. **The balance holds the test request.** A portal order's balance is due at sample collection by default, so the test request stays Confirmed until the balance is paid, and reception cannot start; the documents make "before the report" the default and say the balance never holds collection ([WF-01](wf-01.md), [SF-01](sf-01.md)).
2. **Priority cannot be accepted.** Accept priority stops with a server error, because the feasibility check searches bookings by a test's priority, which is not stored ([SF-07](sf-07.md)).
3. **The receipt is out of reach.** A payment's receipt exists, but no page of the portal links to it ([SF-01](sf-01.md)).
4. **Machine downtime tells nobody.** The booking moves to the other machine, but neither the tester nor the head is told ([SF-05](sf-05.md)).
5. **The subcontractor's result does not reach the head.** It stays a draft until a tester of the department sends it, and nobody is told it waits ([WF-05](wf-05.md)).
6. **A cancelled order keeps its test request.** Accepting the cancellation cancels the order only ([SF-02](sf-02.md)).

Steps the business takes outside the browser, listed by the report: the customer's signature of the handover record (Medilab Mobile), folder members and binding (Medilab Sync), the notices of assignment, booking approval, results sent, report issue and support answers, which go by e-mail with the demo's defaults, and the bank transfers themselves. Observations that are not steps of a main path, such as the missing accreditation mark on the report, stay in each flow's plan.

The local editing service refused the report's conversion: its gateway allowed only `/ConvertService.ashx` while Odoo posts to `/converter`. It is fixed in `tools/onlyoffice/proxy.py`.

Questions the journey could not settle are in [E-commerce questions](../../../questions/ecommerce.md) and [Laboratory questions](../../../questions/laboratory.md).

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
