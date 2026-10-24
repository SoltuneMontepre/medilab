# Features of: Lab head

The lab head configures parameter authorizations, reviews laboratory-wide testing figures, reviews approved results, including a Head of Department's self-approved entries, and signs reports.

## I. User stories

- **US-LH01** As a lab head, I want to see the test requests whose results are all approved, so that I know which reports wait for my signature.
- **US-LH02** As a lab head, I want to sign a test report, or reject it with a reason and the results to check again, so that only checked reports are issued.
- **US-LH03** As a lab head, I want to approve change requests on issued reports, so that a corrected report is issued as a new version.

- **US-LH04** As a lab head, I want to configure the parameters each tester is authorized to test, so that only competent people are scheduled.
- **US-LH05** As a lab head, I want to review results self-approved by a Head of Department when signing their report, so that those results receive final review before issue.
- **US-LH06** As a lab head, I want testing figures for every department over a period, so that I can review the laboratory's workload and turnaround.

## II. Feature details

### 1. Test reports (US-LH01 to US-LH03)

Follows [Reports and change requests](../overview.md#reports-and-change-requests) and [SH-07](../../shared.md#sh-07-signed-documents-are-locked).

| Rule           | Description                                                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| One report     | A test request has one report covering all its samples, in Vietnamese, English or both side by side, as the request asks.    |
| Signing        | Samples have no sign-off of their own; once all results of a request are approved, the next signature is the lab head's on the report. |
| Draft          | When every sample test of a request is approved or cancelled, the system creates the draft report and a signing task for the lab head. |
| Content | The report identifies the customer, request, receipt and issue dates, report number, samples and lab codes, and prints parameter, measured result, unit and method. Comparison limits and conclusions appear only for the requested regulation scope, with wording limited to that scope and insufficient basis where applicable. Below-LOD/LOQ text prints the snapshot threshold and unit. Print the actual result approvers and the report signer; tester signatures stay internal. Cancelled tests are excluded. |
| Rejection      | The lab head can reject a report with a reason, naming the results to check again. Those results go back to the queue of their head of department, unassigned and unsigned: their signatures are withdrawn, their sample tests, samples and request go back to testing, and a new testing task with the reason waits unassigned in the queue of the department that tested them. The report waits until they are approved again; the lab head then gets a new signing task. |
| Issued         | A signed report gets its report number and the digitally signed PDF.                                                          |
| Change request | An issued report keeps its signed file while a change request is processed. Result corrections automatically create or link the report correction. After its required approvals and all corrected results are approved, create a replacement draft and a new signing task. Only issuing the signed replacement marks the old report replaced and notifies the customer that the new PDF is ready. |
| Regulation basis | Before issue, check regulation validity for every requested comparison. If a regulation expired during testing, the Lab Head confirms the applicable basis; testing may continue, but comparison is never silently dropped or switched. Sales obtains agreement for a changed comparison scope. |
| Pending corrections | Before applying a result correction, stop the report's pending signing and return it to draft. Rebuild it and create a fresh signing task once all corrected results are approved, including replacement reports. Old tasks cannot sign obsolete content. |

Acceptance criteria:

- A test request whose results are not all approved has no report waiting for the lab head.
- Approving the last result of a request, with its other tests approved or cancelled, creates the draft report and the lab head's signing task.
- A report prints the actual result approvers and report signer, keeps tester signatures internal and leaves out cancelled tests.
- A report without requested QCVN comparison contains measured results without a forced compliance conclusion.
- A report with expired regulation basis cannot issue its conclusion until the Lab Head confirms that basis.
- Rejecting a report without a reason or without naming a result is refused; the named results go back to their head of department's queue, unassigned.
- Signing a report gives it a report number and a digitally signed PDF in the request's language.
- A corrected report is issued only after its corrected results and required change requests are approved and the Lab Head signs the replacement. The previous report is kept and marked replaced on issue.
- Rejecting and correcting a replacement report creates a new signing task even when the request is already reported.

### 2. Parameter authorization (US-LH04)

| Rule | Description |
| --- | --- |
| Authorization list | The Lab Head maintains which parameters each person may test. Authorization is indefinite, without validity dates, and differs from application access permissions. Scheduling and claiming check this list. |

Acceptance criteria:

- A configured person remains authorized without renewal or an expiry date.
- A person not on the list for the parameter is not offered for assignment or allowed to claim it.

### 3. Final review of self-approved results (US-LH05)

| Rule | Description |
| --- | --- |
| Final review | The Head of Department may approve their own result entries. The Lab Head reviews those approved results when signing the report and may reject the report with a reason and the results to check again. No additional Lab Head result-approval step is required. |

Acceptance criteria:

- A Head of Department's self-approved result can enter a draft report; the report cannot be issued before the Lab Head reviews and signs it.
- Rejecting such a report returns the named results to the department queue under the report-rejection rules.

### 4. Testing figures (US-LH06)

| Rule | Description |
| --- | --- |
| Laboratory figures | For a period and across all departments, show completed sample tests, on-time share, average receipt-to-approval time, overdue sample tests, retests and workload per person, using the same measures as [department figures](head-of-department.md#5-testing-figures-us-hd17). |

Acceptance criteria:

- The Lab Head can view all departments together or filter a department for the same period.

## III. Related documents

- [Laboratory overview](../overview.md)
- [Head of department](head-of-department.md)
- [Approval and signing chain](../../../business/approval-and-signing-chain.md)
