# Old backlog questions

Open points of the SEP490 backlog of medilab-past (09-10-2026 and 10-10-2026) that no document, question or issue covers. Each gives that backlog's proposed answer, which the owner has not decided.

## Catalog

- **Typed codes and sequences.** Does a code sequence skip numbers already taken by typed codes? Proposed answer, not decided: the sequence takes the next free number, and a typed code that matches the sequence's format is warned about.
- **Subcontractor contacts and companies with two roles.** What happens when a subcontractor's default contact is archived, or the company is also a customer? Proposed answer, not decided: archiving the default contact warns, and another is chosen before samples are sent; a company may be both, but never tests its own samples as a subcontractor.
- **Quality registration warnings.** Does a renewed dossier warn again, and is a missed warning sent late? Proposed answer, not decided: a dossier without an expiry date never warns; a renewal warns again from the new date; the warning goes out once N days or fewer remain and that date has not been warned about, so a missed run catches up; the lab head and administrators receive it.
- **Removing a sample type from a parameter in use.** What happens to open orders, order templates and packages? Proposed answer, not decided: the pair is no longer offered; orders already placed keep it; an order template reused later drops that line and says so; packages are still sold for other sample types.

## Sampling and collection

- **Sampling requirements in practice.** Is a way of testing offered when it has no sampling requirement for the sample type, which amount wins between the sample type's minimum and the methods' total, and how are amounts in different units, or too much for one container, handled? Proposed answer, not decided: a way of testing without a sampling requirement is not offered; expected samples use the methods' amounts, with the sample type's minimum as the floor when a method states none; amounts of one category are converted to one unit and others listed apart; container types and preservation conditions come from configurable lists; the total is guidance, and a sample in several containers is recorded in the amount received, such as "3 × 1 L bottles".
- **Holding extra samples.** How long are extra samples held while the revised quotation is unpaid, and what if it is declined or the samples spoil? Proposed answer, not decided: at most N days, by the sample type's preservation condition; once declined or overdue they are closed as not ordered, then returned or disposed of with a record.
- **Collections without a signature or without samples.** Can a collection task be done while its handover record is unsigned, and how is a trip with no sample closed? Proposed answer, not decided: the task cannot be done while its handover record is unsigned; a trip with no sample cancels the task with a reason and tells sales.
- **Customer refuses to sign.** What happens when the customer refuses to sign the handover record? See also "Samples without the customer present" in [Laboratory questions](laboratory.md). Proposed answer, not decided: the refusal is recorded with a reason and photos and the sample delivery staff sign to confirm; the samples are received but not handed over to departments until sales agrees with the customer; the record's legal value is for the owner to decide.
- **Custody history.** How is a move of a sample, such as to another fridge, recorded? Proposed answer, not decided: every change of a sample's holder or location is a custody entry (from, to, person, time, condition) that is never edited or deleted; the sample's current holder and location are those of its latest entry.
- **Disposal reminders.** Do samples not kept, and samples of cancelled requests, appear on the disposal reminder, and who receives it? Proposed answer, not decided: both join the list to dispose of from that day; each sample gets one task in the queue of the department holding it, or of testers when none does.
- **Changed retention days.** Does changing a sample type's retention days change the retention end of samples already retained? Proposed answer, not decided: no; a retained sample keeps the date it got, like a copied limit.
- **Disposal holds.** Can a sample be disposed of while a change request is open? Proposed answer, not decided: no; a sample cannot be disposed of while a change request on one of its results or on its request's report is open, or while it waits for the customer's agreement; the hold reason is shown.

## Testing and results

- **Subcontractor accreditation lapsing.** What happens when the subcontractor of an accepted quotation loses its accreditation before the dispatch? Proposed answer, not decided: as for a machine fault, no dispatch is made; the laboratory waits for the renewal, or sales tells the customer and the way of testing changes only through a revised quotation.
- **Machines and departments.** Which department manages a machine and its bookings? Proposed answer, not decided: a machine names the department that manages it, so department permissions apply to it and its bookings.
- **Attempts in a run.** When may an attempt be put in a test run? Proposed answer, not decided: only when its sample was received by the department, is not held waiting for the customer's agreement and its sample test is not cancelled.

## Reports and laboratory files

- **Bilingual names.** What happens when an entry of a bilingual report has no English name, and may printed names be in italics? Proposed answer, not decided: setting or approving the entry warns about the missing name; italics are allowed in printed names.
- **Undelivered reports.** What happens when a report's email bounces or nobody collects it? Proposed answer, not decided: a bounced email puts the report back on the list to deliver, with the reason; a report not collected in person after a configured number of days reminds the customer; the portal download stays available.
- **Raw data and machines.** Is a raw-data version linked to the machine or booking that produced it? Proposed answer, not decided: an optional link from a raw-data version to that machine or booking.
- **Turning off raw-data folders.** Are saves between syncs lost when a raw-data folder is turned off during testing? Proposed answer, not decided: a raw-data folder cannot be turned off while its sample is being tested, or the computer keeps a local copy of every save.
- **Names that reveal the customer.** May file names, and printed subcontract dispatches, name the customer? See also "Anonymity beyond the label" in [Laboratory questions](laboratory.md). Proposed answer, not decided: sample folders are named by lab code, and file names follow a convention set through sync rules, with a warning or a refusal for the owner to choose; a printed dispatch shows only the lab code, sample type, parameters, methods and due date, never the customer, order or price.

## E-commerce

- **Signing invoices.** [SH-04](../docs/functional/shared.md) names invoices among signed documents, but advance and adjustment invoices are posted without signing. Do invoices have an approval chain, and how is an invoice posted by the system signed? See also [#214](https://github.com/SoltuneMontepre/medilab/issues/214). Proposed answer, not decided: the salesperson's sending of the quotation signs its advance invoice, or only final and adjustment invoices have a chain.
- **Head of Sales approving their own order.** Who approves when the only Head of Sales prepared or asked for the approval? Proposed answer, not decided: another salesperson asks for the approval, or the administrator sets a substitute approver in the chain.
- **Measuring approval thresholds.** Is the discount threshold measured per line or on the whole quotation, and before or after VAT? Proposed answer, not decided: the discount share is (catalog total − total after every discount) / catalog total before VAT, worked out for the whole quotation and for each line, taking the larger; the amount threshold is compared with the total after discounts, VAT included.
- **Price changes before quoting.** Which price applies when the catalog changes between submitting an order and pricing its quotation? Proposed answer, not decided: an order line keeps the price of when it was submitted; a draft quotation warns when the catalog price has changed; a sent quotation keeps its prices.
- **Packages with untestable parameters.** Is a package offered when one of its parameters has no way of testing available? Proposed answer, not decided: a package is shown only when each of its parameters has an available way of testing; archiving a parameter warns the administrator about the packages that contain it.
- **Reorders when a way of testing is gone.** Do reorders and order templates keep the chosen way of testing, and what replaces one that is gone? Proposed answer, not decided: the original is kept when available; otherwise a line whose way the customer chose is dropped with a notice, and a line on the default takes today's default with a notice.
- **Duplicate open orders.** Is sales told when a customer has an identical open order? Proposed answer, not decided: nothing is blocked; claiming an order warns when the customer has an open order with the same content, so sales can ask the customer.
- **Credit customers with overdue invoices.** Are customers allowed to order on credit warned or blocked when they have overdue invoices, and is there a credit limit? Proposed answer, not decided: the credit gate is checked when the test request is confirmed; turning the flag off does not affect orders already through it; the Head of Sales is warned when a credit customer has overdue invoices; an amount limit is for the owner to decide.
- **A salesperson who leaves.** Who takes over a leaver's orders, requests and pending payments, and who keeps the KPIs? Proposed answer, not decided: the Head of Sales reassigns their orders; support requests follow their order, and the others go back to the shared queue; pending payments stay valid for the accountant; KPIs keep the person in charge at each step.
- **An individual's tax code.** Is an individual customer's tax code their citizen ID? Proposed answer, not decided: the individual enters the citizen ID, and the tax code is filled in with it and can be changed; to confirm with the accountant under Thông tư 86/2024/TT-BTC.
- **Several portal users of one business customer.** May every portal user of a business customer pay, decline quotations and cancel orders? Proposed answer, not decided: every portal account of the customer has full rights on its documents; rights per person, such as only the customer's accountant paying, are for the owner to decide.
- **Overdue reminders during a cancellation or dispute.** Do overdue reminders pause while a cancellation request or a dispute is open? Proposed answer, not decided: the amount owed includes adjustment invoices; reminders pause while the order has an open cancellation request; the accountant can pause an invoice's reminders with a reason; one reminder per invoice and period.
- **Approval withdrawn after a collection is booked.** What happens to a booked or ongoing collection when the order's approval is withdrawn? Proposed answer, not decided: a collection not started waits until the order is approved again; a trip under way completes the handover, but its samples are not handed over to departments until then.
- **Collection notices.** Does "collection" on the portal mean picking up samples or results, and is the customer told about appointments and rejected samples? Proposed answer, not decided: the order's contact is told when a collection is scheduled, changed or cancelled, receives the signed handover record by email after each handover, and is told when a sample is rejected, through their preferred channels.
- **Editing a submitted order.** May a customer edit an order already submitted, before or after sales claims it, and which fields? Proposed answer, not decided: the customer edits it while it is submitted and unclaimed; once claimed, the portal shows it read-only and changes go through sales; on their own draft, a customer changes only its lines (parameter, chosen way of testing, package, quantity), contact and notes, which the API enforces too; editing and claiming take the same record lock.
- **Portal users who leave the customer.** Who revokes the portal account of a person who leaves the customer's company? Proposed answer, not decided: the customer asks sales or support; the Head of Sales revokes the account at once and keeps its history; an account never moves to another company.
- **Login and contact email.** Is the login email separate from the contact email, and is it verified? Proposed answer, not decided: they are separate; changing the login email is confirmed through the new address; notices and password reset links go only to a confirmed address.
- **Failed online payments.** Is the customer told when an online payment fails or is cancelled? Proposed answer, not decided: a "payment failed" event with a link to try again, which the customer can turn off.
- **Expected result date.** Is the expected result date required, and what if the due date has already passed? Proposed answer, not decided: it is required when the test request is confirmed; a date already past when the samples are received marks the tests urgent at once and tells the head of department.
- **What customers see of ways of testing.** What do customers see of ways of testing and subcontracting when they order? Proposed answer, not decided: parameters, groups, sample types, the parameter's price and the methods offered, marked "performed by a subcontractor" without its name; never departments, machines, chemicals or subcontractor names.
- **Confirming an unpaid quotation.** May sales confirm a sent quotation that is not paid yet? Proposed answer, not decided: yes, with a warning; the credit gate still stops the laboratory side.
- **Extending an expired quotation.** Does extending an expired quotation make it sent again? Proposed answer, not decided: yes, extending moves it from expired back to sent.
- **Payment gateway test mode.** May the gateway's test mode be on while it takes real payments? Proposed answer, not decided: no; enabling refuses test or simulator mode and placeholder credentials, and simulator routes answer 404 in production.
- **Revenue when parameter groups change.** Is revenue per parameter group counted on today's group tree or fixed per invoice line? See also "Package revenue over time" in [E-commerce questions](ecommerce.md). Proposed answer, not decided: one step moves parameters to a subgroup, and the revenue report states that it counts by today's group tree.

## Shared

- **Bounced mandatory emails.** How does a customer still get a mandatory email that bounced? Proposed answer, not decided: the notice stays in the portal, sales is told to contact the customer, and nothing is sent again to an address flagged as bouncing.
- **Uninstalling E-commerce.** What happens to test requests linked to orders when E-commerce is uninstalled? Proposed answer, not decided: test requests keep the order number as text, and uninstalling warns first.
- **Changing a chain while documents are being signed.** Does a document being signed keep its chain's old levels or take the new ones? Proposed answer, not decided: a document keeps the levels it had at its first signature; a changed chain applies to documents signed afterwards.
- **Signers on leave.** Can a signing level be handed to a backup while its only signer is away? Proposed answer, not decided: the level's role is given to a backup for a limited time, audited, so nobody signs on another's behalf; overdue signing tasks remind.
- **Notices about one's own actions.** Is a person notified of their own action, such as claiming a task? Proposed answer, not decided: nobody is notified of their own action; one open notice per task, person and event type.
- **Tasks for a role nobody holds.** Where does a task go when nobody holds its role or claims it? Proposed answer, not decided: administrators are told, and the task is listed as unassigned; archiving the last holder of a role an active task type uses warns.
- **Two signatures by one person.** May one person sign two levels of the same document? Proposed answer, not decided: no; the person who entered a result cannot approve it, and one person cannot hold two standing signatures on the same document version.


## Security

- **Internal users without a person.** Must internal users be created only through people? Proposed answer, not decided: yes; administrators see the internal users not linked to a person, to link or archive them.

## Related documents

- [Laboratory questions](laboratory.md)
- [E-commerce questions](ecommerce.md)
- [Shared questions](shared.md)
- [Scheduling questions](scheduling.md)
- [Security questions](security.md)
- [Conceptual model](../docs/functional/conceptual-model.md)
