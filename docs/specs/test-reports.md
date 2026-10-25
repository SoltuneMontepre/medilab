# Test reports

Stories: US-AD36, US-LH01, US-LH02, US-LH03, US-SD14, SH-04, SH-07, SH-08

## Goal

Administrators edit report templates in ONLYOFFICE. MediLab generates a working DOCX from approved business data, authorized editors prepare it in the browser, and the Lab Head reviews the saved PDF before signing. Customers receive the issued PDF. The template, data and files behind an issued version remain traceable and unchanged.

## Design

### Ownership and access

Laboratory owns report templates and report preparation. ONLYOFFICE provides editing, comments, co-editing and conversion; MediLab owns business records, access decisions, version storage and issuance.

- Template administration is an assignable permission held by the administrator. Template versions have read, create, edit and archive permissions.
- Editing a report draft requires permission to edit test reports and access to its request. Signing uses the report's approval chain; edit permission alone never permits signing.
- Enforce access when opening the editor, reading content, accepting a save, generating a PDF and signing. Folder membership alone grants no report or customer access.
- Customers cannot open the editor or download internal DOCX drafts or unsigned PDFs. They download their issued PDF through the existing portal and delivery rules.

### Templates

A template has a name, report language and immutable available versions. Each version has its DOCX, required data bindings and state: draft, available or archived. The [administrator feature](../functional/laboratory_module/features/admin.md#6-report-templates-us-ad36) defines its lifecycle.

1. Edit a draft version in ONLYOFFICE, including comments and co-editing, and store the final save.
2. Validate the required bindings and preview a populated report before making that version available.
3. Use only an available version matching the request's Vietnamese, English or bilingual language.
4. Editing an available version creates a separate draft. Archiving prevents new drafts from using it; reports already linked to it keep it.

Template changes never rewrite earlier drafts or issued reports. Selecting a different available version for an unsigned draft regenerates it explicitly and invalidates its prepared PDF. Never silently replace the chosen template.

### Generating and editing a draft

Once every sample test of the request is approved or cancelled, generate the report's internal DOCX draft and create its signing task. Its source records identify:

- the request and report version;
- the exact template version and language;
- the approved result versions, customer and sample data, comparison plan version and its inherited or direct approval basis, criterion snapshots and assessment records used;
- every saved DOCX version and its editor and time.

The functional report content rules determine which data is printed. Each sample's block binds its type, received amount and condition, recorded analysis start and end dates, and report-relevant request or sample notes when provided. Use the recorded dates for that sample, rather than replacing them with the report's receipt or issue date. Keep these printed values in the report's source snapshot. Template editing does not add new business fields or change which comparisons were requested.

Editors may change layout and explanatory text. Generated customer and sample details, measurements, units, criterion requirements, comparison bases, decision rules, evidence scopes, assessment outcomes and approvers are bound to business data. Protect their bindings in the editor and validate their presence and values on the server before PDF preparation. A removed binding, altered value or stale source version blocks preparation; hiding the editor's controls is insufficient. Correct business data through its normal workflow, including change requests where required, then regenerate the draft and review it again.

Requested comparisons follow [Conformity assessments](conformity-assessments.md). Print each criterion's document, edition and applicable clause with its requirement, decision rule, evidence scope and outcome. One report can reference several QCVNs; shared measurements can be cross-referenced without pretending they were measured again. Do not turn an assessment of a tested portion into an unqualified lot or facility conformity statement. An explicit insufficient-basis outcome states its reason and limitation.

Use controlled working files for drafts, with immutable saved versions and the editing-session rules of [Laboratory files](laboratory-files.md#online-editing). Do not enable editing in raw-data or issued-report folders. Draft versions follow report locks and permissions even if a person may otherwise edit the working folder. This workflow creates its own working draft and issued PDF; it does not require general-purpose sample working and report folders.

### Preparing the PDF

Preparing a PDF freezes one candidate for approval:

1. Stop new editing joins and finish the active editor sessions. Wait for MediLab to store the final save; closing a browser or an editor save notification alone is not confirmation.
2. Refuse preparation while a save is pending or failed or a conflict remains unresolved. A late callback cannot change the selected immutable DOCX version or the candidate PDF.
3. Validate the chosen template, required content and business-data versions. For requested comparisons, accept the plan's inherited approval from an unchanged approved preset without requiring a request signature. Authored or changed criteria require direct technical approval. Require recorded outcomes for every assessment; pending assessments or criterion changes awaiting approval block preparation. Check criterion and result versions and preserve the exact snapshot used, including customer details that actually print.
4. Resolve all printed issue metadata, including the report number and visible signer information, and store it in the final DOCX source version before conversion. Reserve the number for this report version before review; reservation does not issue the report. An abandoned reservation remains in history and is not assigned to another report.
5. Convert that saved DOCX to PDF and store the candidate with its hash and the identifiers of its DOCX, template and data versions. Required generated metadata must be part of this candidate, rather than added by re-rendering after approval.
6. Present that candidate for review. Its draft status is clear in the interface; a marked draft print is a separate preview copy, never the source used for digital signing.

Signing checks that the reviewed candidate is still current and all required source approvals still stand, including the comparison plan and assessment evidence. A plan amendment or changed assessment invalidates the affected candidate. The deliberate signing action records its identity and content hash with the approval. An obsolete signing task or preview cannot approve another candidate. If a printed signer or issue detail changes, invalidate the candidate and review its replacement before signing.

### Changes, locks and issuance

- Before the first signature, reopening a draft invalidates the candidate PDF. Save, validate and prepare it again before review.
- Once any approval level signs, the draft and candidate are locked. Editing resumes only after signatures are withdrawn in the order allowed by SH-07; a stale editor callback cannot bypass that lock.
- Once the report's process is completed, its signatures cannot be withdrawn. Corrections use the existing change-request process and create a replacement draft and signing task. Keep the earlier report's files, sources and history.
- After the final approval, digital signing uses the stored candidate PDF. It adds the digital signature without regenerating the report from a newer template, business record or DOCX save. Retry uses the same candidate. With digital signing off, store that candidate as the issued PDF.
- Delivery and portal download use the stored issued PDF. After the replacement's own approvals and signing are complete, issue it; only issuance marks the earlier report replaced and notifies the customer that the new PDF is ready.

### Availability

An unavailable editor, failed save or failed conversion blocks preparation of a new candidate and clearly identifies the pending operation. It never falls back to an older draft for signing. An already prepared, unchanged candidate can proceed through approval and signing without reopening ONLYOFFICE. An ONLYOFFICE outage does not prevent downloading or delivering an already issued PDF. Viettel Sign outages follow [Digital signing](digital-signing.md#outage-and-retry).

## Acceptance criteria

- An administrator edits and previews a template in ONLYOFFICE and makes a valid saved version available; a missing required binding prevents availability.
- Generating a report uses an available template in the request's language and the approved result versions, excluding cancelled tests.
- A report can show criteria from several QCVNs with their own scopes, rules and outcomes. Inherited approval from unchanged preset reuse satisfies the plan approval requirement without a request signature. Authored or changed criteria awaiting approval, or a pending assessment, prevent PDF preparation and signing; an explicit insufficient-basis outcome can be printed with its limitation.
- Changing a plan or assessment makes an affected prepared PDF stale; an issued version keeps its original plan, evidence and files and requires the replacement-report workflow for correction.
- Two authorized editors can comment and co-edit the draft; history identifies the saved versions and editors.
- Editing or removing a generated business value cannot produce a candidate ready for signature. Correcting it through business records requires regeneration and fresh review.
- A pending, failed or conflicted save prevents PDF preparation. A late callback never changes a frozen candidate, and an old task cannot sign a new one.
- A signer's preview, approval record and signing input identify the same candidate PDF. Changing printed issue metadata requires another candidate and review.
- Reopening an unsigned draft invalidates its PDF. A draft with signatures stays locked until permitted withdrawals; an issued report requires a change request.
- A template update or customer-profile change leaves an issued report's files and printed data unchanged.
- A Viettel Sign retry uses the original candidate; it cannot pick up a newer DOCX or template.
- A customer receives only the issued PDF, and a person without request access cannot read its draft through a working folder or editor URL.
- Download and delivery of an issued PDF work when ONLYOFFICE is unavailable.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#reports-and-change-requests)
- [Administrator](../functional/laboratory_module/features/admin.md#6-report-templates-us-ad36)
- [Lab head](../functional/laboratory_module/features/lab-head.md#1-test-reports-us-lh01-to-us-lh03)
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Laboratory files](laboratory-files.md)
- [Digital signing](digital-signing.md)
- [Conformity assessments](conformity-assessments.md)
- [Shared technical implementations](../functional/shared.md)
