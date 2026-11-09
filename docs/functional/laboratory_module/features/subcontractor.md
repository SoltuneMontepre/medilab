# Features of: Subcontractor

A subcontractor is an outside laboratory that tests the sample tests the laboratory outsources to it. Its people sign in to the system to see what was sent to them and enter the results. They see samples only by their lab code, never the laboratory's customer.

## I. User stories

- **US-SUB01** As a subcontractor, I want to see the dispatches sent to us with their sample tests and expected dates, so that I know what to test and by when.
- **US-SUB02** As a subcontractor, I want to enter the results of the sample tests sent to us, so that the laboratory gets them without retyping.

## II. Feature details

### 1. Outsourced tests (US-SUB01, US-SUB02)

Follows [Testing work and scheduling](../overview.md#testing-work-and-scheduling) and [Results](../overview.md#results).

| Rule         | Description                                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Access       | A subcontractor's people sign in to the portal with Odoo users linked to their contacts. They see only the sent and received dispatches of their subcontractor and those dispatches' sample tests. |
| Anonymity    | They see samples by lab code, sample type and parameters only, never the customer or the customer's name for the sample.         |
| Entering     | The results of an outsourced sample test are entered either by the subcontractor or by a lab QA of the laboratory; each result records who entered it. |
| Approval     | A result entered by a subcontractor goes to the head of department for approval as soon as it is entered, and the head is notified; it is approved like the laboratory's own results. |
| First say    | While a result the subcontractor entered waits for approval, a lab QA cannot enter another result for the test. |
| Rejection    | A rejected result stays on the dispatch page with the head's reason, beside the field to enter the new result, and the subcontractor is notified. |

Acceptance criteria:

- A subcontractor user sees the dispatches of their own subcontractor and no others.
- A subcontractor user never sees a sample's customer.
- A result entered by a subcontractor user shows that user as the one who entered it, and waits for approval like any other result.
- A lab QA cannot enter a result for a test whose subcontractor's result waits for approval.
- A subcontractor user is notified of a rejected result and sees it with the reason on the dispatch page.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Tester](tester.md)
- [Laboratory administrator: subcontractors](admin.md#3-subcontractors-us-ad12)
