# Features of: Lab head

The lab head signs the test report (certificate of analysis, CoA) of each test request once all its results are approved.

## I. User stories

- **US-LH01** As a lab head, I want to see the test requests whose results are all approved, so that I know which reports wait for my signature.
- **US-LH02** As a lab head, I want to sign a test report, or reject it with a reason and the results to check again, so that only checked reports are issued.
- **US-LH03** As a lab head, I want to approve change requests on issued reports, so that a corrected report is issued as a new version.

## II. Feature details

### 1. Test reports (US-LH01 to US-LH03)

Follows [Reports and change requests](../overview.md#reports-and-change-requests) and [SH-07](../../shared.md#sh-07-signed-documents-are-locked).

| Rule           | Description                                                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| One report     | A test request has one report covering all its samples, in Vietnamese, English or both side by side, as the request asks.    |
| Signing        | Samples have no sign-off of their own; once all results of a request are approved, the next signature is the lab head's on the report. |
| Draft          | When every sample test of a request is approved or cancelled, the system creates the draft report and a signing task for the lab head. |
| Content        | The report shows its report number and the test request's code, the customer and their address, when the samples were received and the report date, and for each sample its name, lab code and conclusion with a table of parameter, result, unit, limit and method. It prints the heads of department who approved the results and the lab head; testers' signatures are internal and not printed. Cancelled tests are left out. |
| Rejection      | The lab head can reject a report with a reason, naming the results to check again. Those results go back to the queue of their head of department, unassigned and unsigned, and the report waits until they are approved again. |
| Issued         | A signed report gets its report number and the digitally signed PDF.                                                          |
| Change request | A change to an issued report is a change request; approving it creates a new version that replaces the old one, which is kept unchanged. |

Acceptance criteria:

- A test request whose results are not all approved has no report waiting for the lab head.
- Approving the last result of a request, with its other tests approved or cancelled, creates the draft report and the lab head's signing task.
- A report prints the approving heads of department and the lab head, not the testers, and leaves out cancelled tests.
- Rejecting a report without a reason or without naming a result is refused; the named results go back to their head of department's queue, unassigned.
- Signing a report gives it a report number and a digitally signed PDF in the request's language.
- An approved change request creates a new report version; the old version stays readable and is marked as replaced.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Approval and signing chain](../../../business/approval-and-signing-chain.md)
