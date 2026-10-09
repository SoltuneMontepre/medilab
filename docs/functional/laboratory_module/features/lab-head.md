# Features of: Lab head

The lab head signs the test report (certificate of analysis, CoA) of each test request once all its results are approved.

## I. User stories

- **US-LH01** As a lab head, I want to see the test requests whose results are all approved, so that I know which reports wait for my signature.
- **US-LH02** As a lab head, I want to sign or reject a test report with a reason, so that only checked reports are issued.
- **US-LH03** As a lab head, I want to approve change requests on issued reports, so that a corrected report is issued as a new version.

## II. Feature details

### 1. Test reports (US-LH01 to US-LH03)

Follows [Reports and change requests](../overview.md#reports-and-change-requests) and [SH-07](../../shared.md#sh-07-signed-documents-are-locked).

| Rule           | Description                                                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| One report     | A test request has one report covering all its samples, in Vietnamese, English or both side by side, as the request asks.    |
| Signing        | Samples have no sign-off of their own; once all results of a request are approved, the next signature is the lab head's on the report. |
| Issued         | A signed report gets its report number and the digitally signed PDF.                                                          |
| Change request | A change to an issued report is a change request; approving it creates a new version that replaces the old one, which is kept unchanged. |

Acceptance criteria:

- A test request whose results are not all approved has no report waiting for the lab head.
- Signing a report gives it a report number and a digitally signed PDF in the request's language.
- An approved change request creates a new report version; the old version stays readable and is marked as replaced.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Approval and signing chain](../../../business/approval-and-signing-chain.md)
