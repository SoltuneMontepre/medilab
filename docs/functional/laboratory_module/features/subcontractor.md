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
| Access       | A subcontractor's people sign in with Odoo users linked to their contacts. They see only the dispatches sent to their subcontractor and those dispatches' sample tests. |
| Anonymity    | They see samples by lab code, sample type and parameters only, never the customer or the customer's name for the sample.         |
| Entering     | The results of an outsourced sample test are entered either by the subcontractor or by a lab QA of the laboratory; each result records who entered it. |
| Approval     | Results entered by a subcontractor go through the same approval as the laboratory's own results.                                  |

Acceptance criteria:

- A subcontractor user sees the dispatches of their own subcontractor and no others.
- A subcontractor user never sees a sample's customer.
- A result entered by a subcontractor user shows that user as the one who entered it, and waits for approval like any other result.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Tester](tester.md)
- [Laboratory administrator: subcontractors](admin.md#3-subcontractors-us-ad12)
