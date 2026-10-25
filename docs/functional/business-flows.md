# Business flows

The business flows of MediLab from the start of each one to its business result, with the actors who take part. Each flow lists the user stories it walks through, the states it moves, and an activity diagram with one lane per actor. The diagrams show who does what and leave out how the system works inside.

The core flows WF-01 to WF-06 carry a test request from order to report, and WF-07 keeps the laboratory files the testing work produces. The supporting flows SF-01 to SF-09 run beside them. Each path of a flow, its main path, alternative paths and exceptions, belongs to that flow alone; a flow that also touches a path names the flow that holds it. Each path starts from the state the flow names, so no path repeats the steps of the flows before it.

| Flow  | Name                                    | Actors                                                          |
| ----- | --------------------------------------- | --------------------------------------------------------------- |
| WF-01 | Order to approved test request          | Customer, Sales, Accountant, Head of Sales                      |
| WF-02 | Sample reception and handover           | Customer, Sample delivery staff, Head of department             |
| WF-03 | Testing assignment and scheduling       | Head of department, Tester                                      |
| WF-04 | Result entry and approval               | Tester, Head of department                                      |
| WF-05 | Outsourced testing                      | Head of department, Sample delivery staff, Subcontractor        |
| WF-06 | Report signing, release and delivery    | Lab head, Head of department, Sample delivery staff, Customer   |
| WF-07 | Laboratory files                        | Tester, Head of department, Administrator                       |
| SF-01 | Invoicing and payment collection        | Accountant, Sales, Customer                                     |
| SF-02 | Order cancellation                      | Customer, Sales                                                 |
| SF-03 | Change request on a signed document     | Requester, signers of the change-request chain                  |
| SF-04 | Sample retention and disposal           | Tester                                                          |
| SF-05 | Machine calibration and unavailability  | Administrator, Head of department, Tester                       |
| SF-06 | Accreditation and registration renewal  | Administrator                                                   |
| SF-07 | Priority order and urgent tests         | Customer, Sales, Head of department, Tester                     |
| SF-08 | Laboratory setup                        | Administrator                                                   |
| SF-09 | Customer support and feedback           | Customer, Sales                                                 |

## WF-01 Order to approved test request

- **Trigger:** a customer submits a cart on the portal, or sales creates an order for a customer.
- **Result:** the order is approved and its test request is confirmed, with one expected sample for each sample on the quotation.
- **Stories:** US-C08, US-C09, US-C13, US-C14, US-C15, US-S01, US-S02, US-S05, US-S06, US-S07, US-S08, US-S10, US-S12, US-S13, US-S14, US-S15, US-A03, US-A06, US-A08.
- **Starts from:** a catalog with priced parameters and packages, and demo customers.
- **Main path:** A customer orders on the portal; sales claims it, puts the lines on samples and sends the quotation with an advance; the customer pays online; sales confirms and requests approval; the Head of Sales signs.
- **Alternative paths:**
  - WF-01-A1: Sales creates the order for a customer who called, instead of the customer ordering on the portal.
  - WF-01-A2: A visitor who is not signed in submits a cart with their details and e-mail address.
  - WF-01-A3: A returning customer reorders a completed order, or sales creates the order from the customer's template.
  - WF-01-A4: The customer pays the advance by bank transfer or in cash; sales records it and the accountant confirms it.
  - WF-01-A5: The customer declines the quotation with a reason; sales revises it and sends the new version, which the customer accepts.
  - WF-01-A6: The quotation passes its payment deadline and is flagged expired; sales extends it.
  - WF-01-A7: The Head of Sales sends a quotation without an advance to a customer allowed to order on credit; the order goes ahead unpaid.
  - WF-01-A8: The Head of Sales rejects the approval with a reason; sales is told, corrects the order and requests approval again.
  - WF-01-A9: Sales withdraws the approval request to change the order, then requests it again.
- **Exceptions:**
  - WF-01-E1: A quotation with a line not on a sample cannot be sent.
  - WF-01-E2: Submitting a cart without an e-mail address is refused.
  - WF-01-E3: The salesperson who requested approval cannot approve the order.
  - WF-01-E4: The old version of a revised quotation cannot be sent or confirmed.
  - WF-01-E5: The test request of an unpaid order whose customer may not order on credit cannot be confirmed.
- **Paths in other flows:** SF-02 for cancelling an order; SF-07 for the estimated date and priority orders.
- **States:** quotation draft → sent → accepted; order submitted → claimed → confirmed, approval requested → approved; test request draft → confirmed → paid.

```mermaid
flowchart TD
    subgraph lane1 ["Customer"]
        c1[Fill a cart from the catalog] --> c2[Submit the order]
        c3[Read the quotation] --> c4{Accept?}
        c4 -->|pay the advance| c5[Pay online, by transfer or in cash]
        c4 -->|decline with a reason| c6[Quotation declined]
    end
    subgraph lane2 ["Sales"]
        s1[Claim the order] --> s2[Group lines into samples, price and discount]
        s2 --> s3[Send the quotation with the advance request]
        s4[Confirm the order] --> s5[Request approval]
        s6[Revise the quotation]
    end
    subgraph lane3 ["Accountant"]
        a1[Confirm a transfer or cash payment]
    end
    subgraph lane4 ["Head of Sales"]
        h1{Sign the approval?}
    end
    c2 --> s1
    s3 --> c3
    c5 -->|online payment is matched automatically| s4
    c5 -->|transfer or cash| a1 --> s4
    c6 --> s6 --> s3
    s5 --> h1
    h1 -->|reject with a reason| s2
    h1 -->|sign| done(["Order approved; sample collection can start"])
```

## WF-02 Sample reception and handover

- **Trigger:** samples arrive at the laboratory, or sample delivery staff collect them from the customer.
- **Result:** every sample is coded, labelled and received, and its testing tasks wait in the queue of each department that tests it.
- **Stories:** US-SD01, US-SD02, US-SD03, US-SD04, US-SD05, US-SD06, US-SD07, US-SD08, US-SD09, US-SD10, US-SD11, US-SD12, US-HD06, US-HD07.
- **Starts from:** an approved order whose test request expects its samples.
- **Main path:** The customer brings the samples; sample delivery staff record each receipt in good condition, print its label, the customer signs the handover record and the department scans the label.
- **Alternative paths:**
  - WF-02-A1: Sample delivery staff collect the samples at the customer's site from their collection task, take photos and have the customer sign on the phone.
  - WF-02-A2: Sample delivery staff create a test request at reception for a customer without an order; it skips the paid step.
  - WF-02-A3: A sample tested by two departments is handed to both, and each records its own receipt.
  - WF-02-A4: An insufficient sample goes on hold; the head of department asks for more; the collection task brings it back to received.
  - WF-02-A5: A mistake in a signed handover record is corrected with a new record; the old one is kept.
- **Exceptions:**
  - WF-02-E1: An unusable sample is rejected with its condition note and gets no testing task.
  - WF-02-E2: A person outside the department scanning the label is refused.
  - WF-02-E3: Confirming a test request without a sample, or a sample without a parameter, is refused.
  - WF-02-E4: A signed handover record cannot be edited.
- **States:** sample expected → received, or → on hold → received, or → rejected; test request paid → sample received.

```mermaid
flowchart TD
    subgraph lane5 ["Customer"]
        c1[Hand the samples over] --> c2[Sign the handover record on the phone]
    end
    subgraph lane6 ["Sample delivery staff"]
        d1[Collect or receive the samples] --> d2{Condition?}
        d2 -->|good| d3[Record the receipt and where it is stored]
        d3 --> d4[Print the label with lab code and QR code]
        d4 --> d5[Hand the sample to each department]
        d2 -->|unusable| d6[Reject with the condition note]
        d2 -->|insufficient| d7[Put on hold]
        d8[Collect more sample]
    end
    subgraph lane7 ["Head of department"]
        h1[Ask for the sample to be collected again]
        h2[Scan the label to receive the sample]
    end
    c2 --> d1
    d7 --> h1 --> d8 --> d3
    d5 --> h2 --> done([Testing tasks wait in the department queue])
```

## WF-03 Testing assignment and scheduling

- **Trigger:** a testing task enters the queue of its department.
- **Result:** the test is assigned and booked on a fit machine, and the rooms of its method's steps, before its due date.
- **Stories:** US-HD01, US-HD02, US-HD03, US-HD04, US-HD05, US-HD12, US-HD14, US-T01, US-T02, US-T03, US-T04, US-T19, US-T20, US-T21.
- **Starts from:** received samples whose testing tasks wait in the department queue, and fit machines.
- **Main path:** The head of department assigns a sample to a tester; the tester books the recommended machine and slot, which shows on the schedule with a reminder.
- **Alternative paths:**
  - WF-03-A1: A tester claims an unassigned task of their department instead of waiting to be assigned.
  - WF-03-A2: The head of department moves a task to another person or department with a reason.
  - WF-03-A3: The tester moves or cancels a booking; the slot goes back to the queue.
  - WF-03-A4: A sample test's due date is changed by hand; the scheduler says whether the new date can be met.
  - WF-03-A5: A test with a step in a bookable room books the machine and the room together.
  - WF-03-A6: A tester marks a test urgent with a reason; it takes the next free slot first.
  - WF-03-A7: The head of department bumps an urgent test and decides what happens to the tests it would make late.
  - WF-03-A8: A booking that ends after its due date makes the test at risk; its tester and head are told once.
- **Exceptions:**
  - WF-03-E1: A second tester claiming the same task is told it is already claimed.
  - WF-03-E2: Claiming a task of another department is refused.
  - WF-03-E3: Moving a task without a reason is refused.
  - WF-03-E4: Bumping without a reason, or bumping a test that is not urgent, is refused.
- **Paths in other flows:** WF-05 when no machine can finish a test in time; SF-05 for machines past calibration or under repair.
- **States:** sample test waiting → assigned → testing; machine booking queued → scheduled → in progress → done.

```mermaid
flowchart TD
    subgraph lane8 ["Head of department"]
        h1[Assign the sample's tasks to a person] 
        h2[Bump an urgent test with a reason]
        h3[Decide on the outsourcing suggestion]
    end
    subgraph lane9 ["Tester"]
        t1[Claim an unassigned task]
        t2[Open the recommendation] --> t3{Fit machine and slot before the due date?}
        t3 -->|yes| t4[Book the slot]
        t4 --> t5[Get the reminder and start the test]
        t6["Warned: test at risk or machine due for calibration"]
    end
    queue([Task in the department queue]) --> h1 --> t2
    queue --> t1 --> t2
    t3 -->|no| h3 --> wf05([WF-05 Outsourced testing])
    t4 -.-> t6
    t6 -.-> h2 --> t4
    t5 --> wf04([WF-04 Result entry and approval])
```

## WF-04 Result entry and approval

- **Trigger:** a booked test is run.
- **Result:** the reported result is approved against the sample's regulation limit, and the sample is completed once all its tests are.
- **Stories:** US-T05, US-T06, US-T07, US-T08, US-T17, US-T22, US-HD08, US-HD09.
- **Starts from:** sample tests in testing with their bookings, on samples with and without a regulation.
- **Main path:** The tester follows the method's steps, enters a number and its conclusion, sends and signs it; the head approves it and the sample is completed.
- **Alternative paths:**
  - WF-04-A1: The tester enters a text result, such as Not detected.
  - WF-04-A2: The head rejects the result with a reason; the tester retests, the rejected result stays on record and the new one is approved.
  - WF-04-A3: The tester withdraws a result they sent before the head acts.
  - WF-04-A4: An unusual result warns before sending; the tester sends it anyway and the head sees the warning.
  - WF-04-A5: The head cancels a test that cannot be done, with a reason; the sample completes with its other tests approved.
- **Exceptions:**
  - WF-04-E1: The person who entered a result cannot approve it.
  - WF-04-E2: A result on a sample with a regulation cannot be sent without a conclusion.
  - WF-04-E3: Cancelling a test without a reason, or a test with an approved result, is refused.
- **Paths in other flows:** SF-03 for changing a result whose process is completed.
- **States:** sample test testing → result entered → approved, or → testing when rejected; sample testing → awaiting approval → completed.

```mermaid
flowchart TD
    subgraph lane10 ["Tester"]
        t1[Follow the method's steps] --> t2[Enter the result in the method's unit]
        t2 --> t3[Set the conclusion against the copied limit]
        t3 --> t4{Unusual or near the limit?}
        t4 -->|warned, check and send| t5[Send and sign]
        t4 -->|no| t5
        t6["Retest; the rejected result stays on record"]
    end
    subgraph lane11 ["Head of department"]
        h1{Approve the result?}
        h2[Cancel a test that cannot be done, with a reason]
    end
    t5 --> h1
    h1 -->|reject with a reason| t6 --> t2
    h1 -->|approve| done(["Task done; sample completed when all its tests are"])
    done --> wf06([WF-06 when every test of the request is approved or cancelled])
```

## WF-05 Outsourced testing

- **Trigger:** no fit machine can finish a test before its due date, or the head of department outsources it straight away in an emergency.
- **Result:** the subcontractor's result is approved like any other result.
- **Stories:** US-HD05, US-HD10, US-HD11, US-HD13, US-SD13, US-SUB01, US-SUB02, US-T09, US-HD08.
- **Starts from:** sample tests with an outsourcing suggestion, and accredited subcontractors.
- **Main path:** The head accepts the suggestion; sample delivery staff carry the dispatch; the subcontractor enters the result; the head approves it.
- **Alternative paths:**
  - WF-05-A1: A dispatch goes by a delivery service with its tracking number.
  - WF-05-A2: A lab QA enters the results the subcontractor sent back.
  - WF-05-A3: The head outsources a test straight away in an emergency, with a reason.
  - WF-05-A4: The head rejects the subcontractor's result; the test goes back to outsourced and a new result is entered.
  - WF-05-A5: A dispatch is cancelled before any result; its tests stay outsourced for another dispatch.
- **Exceptions:**
  - WF-05-E1: A dispatch whose tests have results cannot be cancelled.
  - WF-05-E2: A subcontractor user sees only its own dispatches and never a sample's customer.
  - WF-05-E3: Outsourcing straight away without a reason, or a test already in testing, is refused.
- **Paths in other flows:** SF-06 for subcontractor accreditation expiry.
- **States:** sample test waiting → outsourced → result entered → approved; dispatch draft → sent → received.

```mermaid
flowchart TD
    subgraph lane12 ["Head of department"]
        h1[Accept the outsourcing suggestion] --> h2[Put the tests in a dispatch]
        h0[Outsource straight away with a reason] --> h2
        h3[Record when it is sent and the expected date]
        h4{Approve the result?}
    end
    subgraph lane13 ["Sample delivery staff"]
        d1[Carry the dispatch to the subcontractor]
    end
    subgraph lane14 ["Subcontractor"]
        s1[See the dispatch and its tests] --> s2[Enter the results]
    end
    h2 --> d1 --> h3 --> s1
    s2 --> h4
    h4 -->|reject| s2
    h4 -->|approve| done([Outsourced test approved])
```

## WF-06 Report signing, release and delivery

- **Trigger:** every sample test of a test request is approved or cancelled, and the system creates the draft report and a signing task for the lab head.
- **Result:** the signed report is issued, delivered to the customer and downloadable on the portal.
- **Stories:** US-LH01, US-LH02, US-SD14, US-C07, US-C18, US-C19.
- **Starts from:** test requests whose sample tests are all approved or cancelled, with their draft reports.
- **Main path:** The lab head signs the report; it gets a number and a signed PDF; staff record an e-mail delivery; the customer is notified and downloads it.
- **Alternative paths:**
  - WF-06-A1: The report is delivered in person or by post; recording it sends no e-mail.
  - WF-06-A2: The request asks for an English, a Vietnamese or a bilingual report.
  - WF-06-A3: The lab head rejects the report naming results and a reason; the results go back to the head of department's queue, are approved again and the lab head signs the new task.
  - WF-06-A4: A request with a cancelled test issues a report without it.
  - WF-06-A5: The lifecycle test: one order runs from the portal through reception, testing and approval to the issued report.
- **Exceptions:**
  - WF-06-E1: With Viettel Sign unavailable the report is not marked signed, and signing is retried.
  - WF-06-E2: Rejecting a report without a reason or without naming a result is refused.
  - WF-06-E3: An unissued report cannot be delivered, and a customer downloads only their own reports.
- **Paths in other flows:** SF-03 for a change request on an issued report; SF-04 for the samples after the report.
- **States:** test report draft → signing → issued; test request completed → reported; order completed.

```mermaid
flowchart TD
    subgraph lane15 ["Lab head"]
        l1[Review the requests ready for release] --> l2{Sign the report?}
    end
    subgraph lane16 ["Head of department"]
        h1[Results sent back wait in the queue unassigned]
    end
    subgraph lane17 ["Sample delivery staff"]
        d1[Deliver in person, by post or by e-mail] --> d2[Record the delivery]
    end
    subgraph lane18 ["Customer"]
        c1[Notified that the report is issued] --> c2[Download the report]
    end
    l2 -->|reject naming the results and the reason| h1 --> wf04([WF-04 approves them again])
    l2 -->|sign| issued[Report number and digitally signed PDF]
    issued --> d1
    issued --> c1
    issued -.->|Viettel Sign unavailable| retry["Not marked signed; signing retried"] -.-> issued
```

## WF-07 Laboratory files

- **Trigger:** a tester saves a file in a folder bound in Medilab Sync, or a head of department creates a sample's folders.
- **Result:** every version of every laboratory file is kept and traceable, conflicts keep both versions, and the version a report relies on is signed.
- **Stories:** US-T23, US-T24, US-T25, US-T26, US-T27, US-T28, US-T29, US-HD15, US-HD16, US-AD29, US-AD30, US-AD31.
- **States:** upload prepared → uploading → finalizing → completed or conflict; editing session open → saving → committed; lock active → released or expired.
- **Starts from:** sample folders with members, bound on two testers' computers, and the editing service running.
- **Main path:** A tester saves a result file in a bound folder; Medilab Sync uploads it as a new version; the head of department signs that version.
- **Alternative paths:**
  - WF-07-A1: The head of department creates a sample's raw-data and result folders, and the owner adds the testers as members.
  - WF-07-A2: A colleague's new version downloads to a two-way folder on another computer.
  - WF-07-A3: Two testers change the same file from one version; the second upload is kept as a conflict, and the tester takes the server's version with a backup of their own.
  - WF-07-A4: A tester restores an earlier version, which becomes the new current version.
  - WF-07-A5: Two testers edit a result spreadsheet together in the browser; saving adds a version.
  - WF-07-A6: A tester locks a working file, edits and unlocks it; an administrator releases a lock someone left.
  - WF-07-A7: A tester browses and downloads a sample's files in the back office.
  - WF-07-A8: An administrator archives a folder; it keeps every version until its retention date.
- **Exceptions:**
  - WF-07-E1: A file outside the folder's sync rules is not uploaded.
  - WF-07-E2: Uploading a file someone else has locked is refused.
  - WF-07-E3: A revoked device can no longer sync, and the person's other devices keep working.
  - WF-07-E4: A removed member's pending files are paused and nothing on their computer is deleted.
  - WF-07-E5: A turned-off folder refuses uploads and still allows downloads.
  - WF-07-E6: With the editing service down, syncing, history and restore keep working.
  - WF-07-E7: Rejecting a file version without a reason is refused.

```mermaid
flowchart TD
    subgraph lane40 ["Tester"]
        t1[Save the file in the bound local folder] --> t2{Made from the current version?}
        t2 -->|no| t3["Conflict: keep own file or take the server's"]
        t4[Restore an earlier version]
        t5[Edit an Office file online with colleagues]
        t6[Lock a working file while editing it]
    end
    subgraph lane41 ["Head of department"]
        h1[Create the sample's raw-data and result folders]
        h2{Sign the result version?}
    end
    subgraph lane42 ["Administrator"]
        a1[Revoke a device, turn a folder off, archive it]
        a2[Release a lock someone left]
    end
    h1 --> t1
    t2 -->|yes| v[New current version, uploaded straight to the bucket]
    t4 --> v
    t5 --> v
    t6 --> t1
    v --> others([Two-way folders on other computers download it])
    v --> h2
    h2 -->|reject with a reason| t1
    h2 -->|sign| signed([Version signed with its hash])
    a2 --> t1
```
## SF-01 Invoicing and payment collection

- **Trigger:** an order needs its final invoice, or a payment arrives.
- **Result:** every invoice is paid, and each day's online payments match the PayOS transactions and are locked.
- **Stories:** US-A01, US-A02, US-A04, US-A05, US-A07, US-A08, US-A09, US-A10, US-A11, US-A12, US-A13, US-C16, US-C17, US-S11.
- **Starts from:** orders with a paid advance whose testing is completed.
- **Main path:** The accountant creates and e-mails the final invoice; the customer pays it online; a receipt is issued and the order is paid.
- **Alternative paths:**
  - SF-01-A1: The customer pays part online, then the rest; the invoice is partially paid, then paid.
  - SF-01-A2: Sales records a cash payment; the accountant confirms it.
  - SF-01-A3: The accountant rejects a payment sales recorded; the salesperson is told the reason and the invoice returns to its previous status.
  - SF-01-A4: An adjustment invoice lowers or raises what is owed; the original invoice is unchanged.
  - SF-01-A5: An invoice unpaid after its due date reminds the customer at each interval.
  - SF-01-A6: A PayOS transaction with no payment is flagged; the accountant creates its payment, the flag clears and the day is locked.
- **Exceptions:**
  - SF-01-E1: A payment above the amount still owed is refused.
  - SF-01-E2: A posted invoice cannot be edited.
  - SF-01-E3: An online payment of a locked day cannot be changed.
  - SF-01-E4: A repeated PayOS notification records no second payment.
- **States:** invoice posted → partially paid → paid; payment pending → confirmed or rejected; reconciliation day open → locked.

```mermaid
flowchart TD
    subgraph lane19 ["Accountant"]
        a1["Create the final invoice: total minus the advance"] --> a2[E-mail the invoice]
        a3{Confirm the payment?}
        a4[Reconcile the day's PayOS transactions] --> a5{All matched?}
        a5 -->|yes| a6[Lock the day]
        a5 -->|no| a7[Create the payment of a flagged transaction]
        a8[Correct with an adjustment invoice]
    end
    subgraph lane20 ["Sales"]
        s1[Record a cash or transfer payment]
    end
    subgraph lane21 ["Customer"]
        c1[Pay online, in full or in part]
        c2[Download the invoice and the receipt]
    end
    a2 --> c1
    a2 --> s1 --> a3
    a3 -->|reject with a reason| s1
    a3 -->|confirm| r["Receipt issued; payment status updated"] --> c2
    c1 --> r
    a7 --> a5
    r -.->|unpaid after the due date| reminder[Customer reminded at each interval]
```

## SF-02 Order cancellation

- **Trigger:** a customer wants to cancel an order.
- **Result:** the order and everything the laboratory created for it are cancelled, or the request is declined with a reply.
- **Stories:** US-C11, US-C12, US-S16, US-S17.
- **Starts from:** orders in each status, some with completed tests.
- **Main path:** A customer requests the cancellation of a confirmed order with a reason; sales accepts; the order and its test request are cancelled.
- **Alternative paths:**
  - SF-02-A1: The customer cancels an order that is not confirmed yet, without asking.
  - SF-02-A2: Sales declines the request with a reply the customer sees on the order.
  - SF-02-A3: Sales cancels an order on their own while no testing is completed.
  - SF-02-A4: An approved order is cancelled through a change request the Head of Sales approves.
- **Exceptions:**
  - SF-02-E1: A request without a reason is refused.
  - SF-02-E2: Cancelling an order with a completed test is blocked.
- **States:** cancellation request open → accepted or declined; order → cancelled.

```mermaid
flowchart TD
    subgraph lane22 ["Customer"]
        c1{Order confirmed?}
        c1 -->|no| c2[Cancel the order]
        c1 -->|yes| c3[Request cancellation with a reason]
        c4[Read the reply on the order]
    end
    subgraph lane23 ["Sales"]
        s1{Any testing completed or results released?}
        s1 -->|yes| s2[Decline with a reply]
        s1 -->|no| s3{Accept?}
        s3 -->|no| s2
    end
    c3 --> s1
    s2 --> c4
    s3 -->|yes| cancel(["Order and its test request cancelled; a paid advance is settled outside the system"])
    c2 --> cancel
```

## SF-03 Change request on a signed document

- **Trigger:** a person who can edit a type of document finds a mistake in one whose process is completed, such as a result or a report.
- **Result:** a new version replaces the signed one, which is kept unchanged, or the request is rejected and the document stays as it is.
- **Stories:** US-T11, US-LH03, SH-07.
- **Starts from:** completed results and issued reports, and signed documents still in process.
- **Main path:** A tester raises a change request on a completed result; the change-request chain signs it; a new version replaces the old one, which stays readable.
- **Alternative paths:**
  - SF-03-A1: A change request on an issued report is approved by the lab head and creates a new report version.
  - SF-03-A2: The chain rejects a change request; the signed document stays unchanged and the reason is kept.
  - SF-03-A3: Before the process is completed, signers withdraw in the reverse order they signed and the document can be edited again.
- **Exceptions:**
  - SF-03-E1: A change request without what to change or why is refused.
  - SF-03-E2: Withdrawing a signature while a signature given after it stands, by a signer who can no longer sign, or after the process is completed, is refused.
- **States:** change request requested → approved → applied, or → rejected; document version → replaced.

```mermaid
flowchart TD
    subgraph lane24 ["Requester"]
        r1["Raise a change request: what to change and why"]
        r2[Follow its status]
    end
    subgraph lane25 ["Signers of the change-request chain"]
        s1{Sign each level in order?}
    end
    r1 --> s1
    s1 -->|reject with a reason| kept([Signed document unchanged])
    s1 -->|last level signs| v[New unsigned version linked to the old one]
    v --> old[Old version marked replaced, still readable]
    v --> sign([New version signed through its own chain])
    r1 -.-> r2
```

## SF-04 Sample retention and disposal

- **Trigger:** the report of a sample's test request is issued.
- **Result:** every sample that is not kept, or whose retention period is over, is disposed of with a record of when, by whom and how.
- **Stories:** US-T10.
- **Starts from:** reported samples, kept and not kept, and samples of cancelled requests.
- **Main path:** A kept sample's retention period ends; it appears on the tester's daily to-do and the tester records its disposal.
- **Alternative paths:**
  - SF-04-A1: A sample that is not kept is disposed of right after its report.
  - SF-04-A2: A sample of a cancelled request is disposed of.
- **Exceptions:**
  - SF-04-E1: Disposing of a sample with no method on it or its sample type is refused.
  - SF-04-E2: A disposed sample cannot be disposed of again or changed back.
- **States:** sample reported → retained → disposed, or reported → disposed.

```mermaid
flowchart TD
    subgraph lane26 ["Tester"]
        t1["Daily to-do: samples whose retention ends soon or has ended"]
        t2[Dispose of the sample by its method]
        t3[Record when, by whom and how]
    end
    start([Report issued]) --> keep{Kept after testing?}
    keep -->|yes| retained[Retained until report date plus retention days] --> t1 --> t2
    keep -->|no| t2
    t2 --> t3 --> done(["Sample disposed; cannot be undone"])
```

## SF-05 Machine calibration and unavailability

- **Trigger:** a machine's calibration falls due, or a machine is under repair.
- **Result:** no test runs on an unfit machine; its bookings move to other machines or are suggested for outsourcing, and the machine returns to use once serviced.
- **Stories:** US-AD09, US-AD10, US-T21, US-HD03, US-HD05.
- **Starts from:** machines with scheduled bookings, calibration dates and service records.
- **Main path:** The administrator sets a machine under repair; its bookings move to another fit machine and their testers are told; recording the repair makes it usable again.
- **Alternative paths:**
  - SF-05-A1: A machine passes its calibration date; it gets no new booking until a calibration is recorded.
  - SF-05-A2: Booking a machine whose calibration is due soon, or that was repaired recently, warns and still books.
- **Exceptions:**
  - SF-05-E1: A moved booking that no other machine can finish in time gets an outsourcing suggestion.
  - SF-05-E2: A machine with queued, scheduled or running bookings cannot be archived.
- **States:** machine in use → under repair → in use; booking scheduled → queued → scheduled on another machine.

```mermaid
flowchart TD
    subgraph lane27 ["Tester"]
        t1["Warned at booking: calibration due soon or recent repair"]
        t2[Told that the booking moved]
    end
    subgraph lane28 ["Head of department"]
        h1[Decide on the outsourcing suggestions]
    end
    subgraph lane29 ["Administrator"]
        a1[Record the repair status]
        a2[Record the calibration or repair with the next due date]
    end
    due([Calibration due within the warning days]) --> t1
    over([Calibration overdue or machine under repair]) --> a1 --> q[Its bookings go back to the queue]
    q --> other{Another fit machine in time?}
    other -->|yes| t2
    other -->|no| h1
    a2 --> back([Machine usable again])
```

## SF-06 Accreditation and registration renewal

- **Trigger:** the laboratory receives an accreditation certificate or registers a quality dossier, or one of them, or a subcontractor's accreditation, nears its expiry.
- **Result:** reports carry the accredited and registered marks only while they are valid, and renewed dates restore them.
- **Stories:** US-AD08, US-AD12, US-AD28.
- **Starts from:** accreditation certificates, quality dossiers and subcontractors near and past their expiry.
- **Main path:** The administrator imports a certificate's methods; the ways of testing are accredited while it is valid and lose it the day after its last valid day.
- **Alternative paths:**
  - SF-06-A1: A quality dossier warns before and on its expiry day; after it, its mark is no longer printed; renewing it prints the mark again.
  - SF-06-A2: A subcontractor whose accreditation expired cannot be chosen; renewing the date makes it selectable again.
  - SF-06-A3: Archiving a certificate removes the accreditation of its methods; restoring it gives it back.
- **Exceptions:**
  - SF-06-E1: Importing a row without a code or title is refused and creates nothing.
  - SF-06-E2: A subcontracted way of testing is never accredited.
- **States:** certificate, dossier or subcontractor accreditation valid → expired → valid again when renewed.

```mermaid
flowchart TD
    subgraph lane30 ["Administrator"]
        a1[Record the certificate and import its methods]
        a2[Record the dossier and the ways of testing it covers]
        a3[Warned days before a dossier expires and on the day]
        a4[Record the renewed dates]
    end
    a1 --> acc[Ways of testing accredited while the certificate is valid]
    a2 --> mark[Dossier mark printed on reports]
    mark --> a3
    acc --> exp{Past the last valid day?}
    a3 --> exp
    exp -->|yes| off["Not accredited; mark not printed; subcontractor cannot be chosen"]
    off --> a4 --> valid([Valid again])
```

## SF-07 Priority order and urgent tests

- **Trigger:** a customer asks for results earlier than the laboratory's estimate, or a test must go ahead of others.
- **Result:** an order the laboratory can meet is accepted as a priority order, and its urgent tests are scheduled first.
- **Stories:** US-S21, US-S22, US-T19, US-HD12, US-HD13, US-HD14.
- **Starts from:** quotations in preparation and a laboratory schedule with free and busy machines.
- **Main path:** The customer asks for an earlier date the laboratory can meet; sales accepts it as a priority order and its tests are urgent when created.
- **Alternative paths:**
  - SF-07-A1: Adding a parameter to the quotation updates the estimated return date.
- **Exceptions:**
  - SF-07-E1: A date the laboratory cannot meet is not accepted, and the earliest possible date is shown.
- **Paths in other flows:** WF-03 for marking tests urgent and bumping; WF-05 for outsourcing straight away.
- **States:** sample test created urgent; booking queued ahead of tests that are not urgent; bumped bookings planned again.

```mermaid
flowchart TD
    subgraph lane31 ["Customer"]
        c1[Ask for an earlier result date]
    end
    subgraph lane32 ["Sales"]
        s1[See the estimated return date while quoting] --> s2{Can the laboratory meet the earlier date?}
        s2 -->|no| s3[Offer the earliest date it can]
    end
    subgraph lane33 ["Head of department"]
        h1[Bump an urgent test ahead of bookings not started]
        h2[Outsource straight away with a reason]
    end
    subgraph lane34 ["Tester"]
        t1[Mark one of their tests urgent with a reason]
    end
    c1 --> s1
    s2 -->|yes| urgent["Priority order: its tests are urgent when created"]
    urgent --> queue[Urgent tests take the next free slots first]
    t1 --> queue
    queue --> h1
    queue --> h2
```

## SF-08 Laboratory setup

- **Trigger:** a laboratory starts using MediLab, or its catalog, people or rules change.
- **Result:** everything an order needs exists: the catalog with its ways of testing, prices and taxes, people and roles, approval chains and settings.
- **Stories:** US-AD01, US-AD02, US-AD03, US-AD04, US-AD05, US-AD06, US-AD07, US-AD09, US-AD10, US-AD11, US-AD13, US-AD14, US-AD15, US-AD16, US-AD17, US-AD18, US-AD19, US-AD20, US-AD26, US-AD27, SH-03.
- **Starts from:** an empty laboratory with the modules installed.
- **Main path:** The administrator creates a parameter with its way of testing, regulation limit and price; a customer can order it and a tester can run it.
- **Alternative paths:**
  - SF-08-A1: The administrator creates a service package; the customer orders it whole at its own price.
  - SF-08-A2: The administrator gives a person a role; the person sees the menus of that role and no others.
  - SF-08-A3: A VAT rate changes from a date; quotations dated after it use the new rate.
  - SF-08-A4: The administrator sets the approval chain of a document type; its documents are signed level by level.
- **Exceptions:**
  - SF-08-E1: A parameter without a price and tax cannot be added to a cart.
  - SF-08-E2: Archiving a record still in use is refused with the list of what uses it.
  - SF-08-E3: A code that already exists is refused.

```mermaid
flowchart TD
    subgraph lane35 ["Administrator"]
        a1[Units, sample types and parameter groups] --> a2[Test parameters]
        a2 --> a3["Ways of testing: method, steps, machines, department or subcontractor"]
        a3 --> a4[Regulations and their limits]
        a2 --> a5[Prices, taxes and service packages]
        a6[Departments, teams and people] --> a7[Roles and permissions]
        a7 --> a8[Approval chains and task routing]
        a9["Settings: numbering, deadlines, thresholds"]
    end
    a4 --> ready([Ready to take orders])
    a5 --> ready
    a8 --> ready
    a9 --> ready
```

## SF-09 Customer support and feedback

- **Trigger:** a customer registers, or contacts the laboratory through the portal.
- **Result:** the customer's account and contacts are kept, their questions are answered, and a completed order can be rated.
- **Stories:** US-C01, US-C02, US-C03, US-C04, US-C05, US-C06, US-C20, US-C21, US-S03, US-S04, US-S20.
- **Starts from:** registered customers with completed and open orders.
- **Main path:** A customer opens a support request about an order; the order's salesperson answers; the request is answered and the customer notified.
- **Alternative paths:**
  - SF-09-A1: A support request about no order is visible to every salesperson until one takes it.
  - SF-09-A2: A customer registers, keeps their profile and contacts, and uploads a logo.
  - SF-09-A3: Sales invites a customer to the portal and merges a duplicate profile.
  - SF-09-A4: The customer rates a completed order.
- **Exceptions:**
  - SF-09-E1: Rating an order that is not completed, or rating it twice, is refused.
  - SF-09-E2: Another customer never sees the customer's support requests or feedback.
- **States:** support request open → answered → closed; order completed → rated.

```mermaid
flowchart TD
    subgraph lane36 ["Customer"]
        c1[Register, or accept the invitation from sales] --> c2[Keep the profile and contacts]
        c3[Open a support request, optionally about an order]
        c4[Read the answer]
        c5[Rate a completed order once]
    end
    subgraph lane37 ["Sales"]
        s1[Invite the customer and merge duplicate profiles]
        s2["Take the request: the order's salesperson, or anyone for no order"]
        s3[Answer]
    end
    s1 --> c1
    c3 --> s2 --> s3 --> c4
    c4 --> closed([Request closed])
    c5 --> rated([Feedback visible to sales and management])
```

## Related documents

- [Overview](index.md)
- [Laboratory overview](laboratory_module/overview.md)
- [E-commerce overview](ecommerce_module/overview.md)
- [Shared technical features](shared.md)
- [Business rules](../business/readme.md)
