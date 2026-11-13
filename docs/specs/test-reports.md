# Test reports

Stories: US-AD36, US-LH01, US-LH02, US-LH03, US-SD14, SH-04, SH-07, SH-08

## Goal

Administrators edit report templates in ONLYOFFICE. MediLab generates a DOCX from approved business data and converts it to a read-only PDF, and the Lab Head reviews that PDF before signing. Nobody edits a report draft. Customers receive the issued PDF. The template, data and files behind an issued version remain traceable and unchanged.

## Design

### Ownership and access

Laboratory owns report templates and report preparation. ONLYOFFICE provides template editing, comments, co-editing and report conversion; MediLab owns business records, access decisions, version storage and issuance.

- Template administration is an assignable permission held by the administrator. Template versions have read, create, edit and archive permissions.
- Nobody edits a report draft. Signing uses the report's approval chain; the Lab Head, as its signer, may choose another available template version.
- Enforce access when reading content, generating a PDF and signing. Folder membership alone grants no report or customer access.
- Customers cannot download internal DOCX drafts or unissued PDFs. They download their issued PDF through the existing portal and delivery rules; it is digitally signed when digital signing is on.

### Templates

A template has a name, report language and immutable available versions. Each version has its DOCX, required data bindings and state: draft, available or archived. The [administrator feature](../functional/laboratory_module/features/admin.md#6-report-templates-us-ad36) defines its lifecycle.

1. Edit a draft version in ONLYOFFICE, including comments and co-editing, and store the final save.
2. Validate the required bindings and preview a populated report before making that version available.
3. Use only an available version matching the request's Vietnamese, English or bilingual language.
4. Editing an available version creates a separate draft. Archiving prevents new drafts from using it; reports already linked to it keep it.

Template changes never rewrite earlier drafts or issued reports. Selecting a different available version for an unsigned draft regenerates it explicitly and invalidates its prepared PDF. Never silently replace the chosen template.

A template (`medilab.report.template`) is created with its first draft version (`medilab.report.template.version`) and one DOCX file in the shipped **Report Templates** laboratory folder. The file's versions are the template's saves; making a version available freezes the file's last save as the version's DOCX, and a new draft starts from an available version's DOCX, restored as the file's newest version. A template has at most one draft at a time. Making a version available needs every required binding, an editor that has finished saving and a preview of its last save: MediLab fills the DOCX with example values, ONLYOFFICE converts it to PDF and the PDF is kept on the version. Archiving is final; an archived version is never offered for a new draft and stays on the reports that use it. Template administration is the template and version permissions; the administrator holds them, and the version's `read` permission lets report editors and signers see which version a report uses.

New reports of a language use the latest available version of the first template of that language, in the templates' order. The Lab Head chooses another available version of the report's language with **Change Template**, which generates the draft again and prepares a new PDF for review.

#### Bindings

A binding is a content control whose tag is `medilab:` followed by the binding's name, in the body, a header or a footer. A new template holds every binding after its label. MediLab fills each one and locks it against deletion and editing (`sdtContentLocked`); the editor keeps the lock, and the server still checks every value.

| Binding | Prints |
| --- | --- |
| `report_number` | The report number, filled when the PDF is prepared |
| `report_date` | The day the PDF is prepared, filled then |
| `request_code` | The test request's code |
| `customer_name`, `customer_address` | The customer's name and address |
| `received_dates` | The first and last day the reported samples were received |
| `samples` | For each sample: its name and lab code, sample type, amount received, condition, first recorded analysis start, conclusion, and a table of parameter, result, unit, limit and method; a paragraph of its own |
| `approvers` | The approvers of the reported results and their levels; a paragraph of its own |

A template version cannot become available while it misses one of these bindings, names a `medilab:` binding MediLab does not fill, or places `samples` or `approvers` inside a line of text.

### Generating a draft

Once every sample test of the request is approved or cancelled, generate the report's internal DOCX draft and create its signing task. Its source records identify:

- the request and report version;
- the exact template version and language;
- the approved result versions, customer and sample data, and requested regulation comparison data used;
- the generated DOCX version.

The functional report content rules determine which data is printed. Each sample's block binds its type, received amount and condition, recorded analysis start and end dates, and report-relevant request or sample notes when provided. Use the recorded dates for that sample, rather than replacing them with the report's receipt or issue date. Keep these printed values in the report's source snapshot. Template editing does not add new business fields or change which comparisons were requested.

Nobody edits the draft. Its explanatory text comes from the template version and the remarks of the approved results. Generated customer and sample details, measurements, units, comparison limits, conclusions and approvers are bound to business data; validate their presence and values on the server before PDF preparation. A missing binding, altered value or stale source version blocks preparation. Correct business data through its normal workflow, including change requests where required, then generate the draft again and review its new PDF.

Drafts are controlled files with immutable versions and are never opened in the online editor. Draft versions follow report locks and permissions even if a person may otherwise edit the working folder. This workflow creates its own working draft and issued PDF; it does not require general-purpose sample working and report folders.

A report's draft is one DOCX file in the shipped **Test Report Drafts** laboratory folder. MediLab generates it when the report is created, and again with **Generate Draft Again** or **Change Template**. Each generation is a `medilab.test.report.draft` record naming the template version, the generated DOCX version, the result versions and the values it printed; issue bindings stay empty in a draft. Generation and its storage never run when a result is approved, so approving results never depends on ONLYOFFICE or the bucket. 
### Preparing the PDF

Preparing a PDF freezes one candidate for approval:

1. Validate the chosen template, required content and business-data versions. Check result versions and preserve the exact snapshot used, including customer details that actually print.
2. Resolve all printed issue metadata, including the report number and visible signer information, and store it in the final DOCX source version before conversion. Reserve the number for this report version before review; reservation does not issue the report. An abandoned reservation remains in history and is not assigned to another report.
3. Convert that DOCX to PDF and store the candidate with its hash and the identifiers of its DOCX, template and data versions. Required generated metadata must be part of this candidate, rather than added by re-rendering after approval.
4. Present that candidate for review. Its draft status is clear in the interface; a marked draft print is a separate preview copy, never the source used for digital signing.

**Prepare PDF** on an unsigned draft report does this in one transaction, holding the report's operation lock and the draft file's row:

- It refuses while ONLYOFFICE's health check fails.
- It refuses when the draft was not generated from the report's template version, when a required binding is missing, or when a business binding no longer prints what the business records give now.
- It reserves the report number from the report sequence, fills `report_number` and `report_date` into a new DOCX version of the draft, has ONLYOFFICE convert that version to PDF, and stores a `medilab.test.report.candidate` waiting for review with the PDF, its SHA-256, the template version, the DOCX version, the result versions, the printed number and date, and the printed business values. A failed conversion stores nothing and keeps no number.
- **Generate Draft Again**, **Change Template** and the lab head's rejection make a waiting candidate obsolete. The report keeps its reserved number for every later candidate of the same report version.
- A candidate is current while it waits for review and its report still has the same template version, its DOCX version was prepared from the draft's latest generation, the same result versions and the same printed business values. The report form shows a waiting candidate as a draft PDF, not issued, and warns when it is no longer current. The lab head opens it with **Review PDF**.

Reports issued before report templates keep their PDF unchanged: the upgrade records each as an issued, migrated candidate with the PDF's SHA-256 and no template or DOCX.

Signing checks that the reviewed candidate is still current and all required source approvals still stand. Changed source data invalidates the affected candidate. The deliberate signing action records its identity and content hash with the approval. An obsolete signing task or preview cannot approve another candidate. If a printed signer or issue detail changes, invalidate the candidate and review its replacement before signing.

### Changes, locks and issuance

- Before the first signature, generating the draft again or changing its template invalidates the candidate PDF; MediLab prepares a new one for review.
- Once any approval level signs, the draft and candidate are locked. Regeneration resumes only after signatures are withdrawn in the order allowed by SH-07.
- Once the report's process is completed, its signatures cannot be withdrawn. Corrections use the existing change-request process and create a replacement draft and signing task. Keep the earlier report's files, sources and history.
- After the final approval, digital signing uses the stored candidate PDF. It adds the digital signature without regenerating the report from a newer template, business record or DOCX save. Store the verified signed PDF before issuing the report. Retry uses the same candidate and checks that the candidate and its approvals still stand. With digital signing off, store that candidate without a digital signature, then issue the report.
- If digital signing fails, keep the approvals and show pending digital signing; the report remains unissued. It cannot be delivered or downloaded by the customer, sends no release notification and does not replace an earlier report. Signing resumes through the existing retry process.
- Delivery and portal download use the stored issued PDF. After the replacement's own approvals and signing are complete, issue it; only issuance marks the earlier report replaced and notifies the customer that the new PDF is ready.

A report is signed only while its candidate waits for review and is current. **Sign** names the candidate shown when the signer opened the report, and refuses once another one was prepared; the signature records the candidate's SHA-256. When the last level signs, the report becomes **Pending Digital Signing** until its PDF is stored: the candidate's PDF signed by Viettel Sign while digital signing is on, or a copy of it while it is off, attached to the report under the reserved number. Storing it issues the report: the candidate becomes issued, the report it replaces becomes replaced, its request and samples become reported, the kept samples are retained and the customer is told, once.

- A report pending digital signing keeps its approvals and is listed neither to sign nor to deliver, nor in the portal. The signing job, **Retry Digital Signing** and printing retry it, each checking that the report is still pending, its last level still signed and its candidate still current; a failed check leaves it pending and issues nothing.
- Withdrawing a signature of a pending report returns it to signing or draft, so its queued signing no longer issues it; signing it again signs the same candidate while it is current.
- A report still pending once digital signing is turned off is issued with its candidate's PDF at its next retry. An issued report prints its stored PDF, also after digital signing is turned on.
- A change request raised on a result printed on an issued report joins that report's change request (`report_change_request_id`): its open one, the one whose replacement is still unissued, or a new one raised in the result requester's name. A document has one requested or approved change request at a time, and an issued report takes none while its replacement is unissued.
- An approved report change request creates its replacement, a draft with a signing task, once none of its result corrections is still requested and every result the report prints is approved; until then it stays approved, and approving the last corrected result, or rejecting a linked correction, applies it.
- Applying a result correction stops the signing of the request's unissued report, first version or replacement: its signatures are withdrawn, its candidate becomes obsolete and its signing task is cancelled. Once its results are approved again, a first version gets its task when the request completes and a replacement gets a fresh one; MediLab then generates its draft again and prepares its PDF.

### Availability

A failed conversion blocks preparation of a new candidate and clearly identifies the pending operation. It never falls back to an older draft for signing. An already prepared, unchanged candidate can proceed through approval and signing without ONLYOFFICE. An ONLYOFFICE outage does not prevent downloading or delivering an already issued PDF. Viettel Sign outages follow [Digital signing](digital-signing.md#outage-and-retry).

## Acceptance criteria

- An administrator edits and previews a template in ONLYOFFICE and makes a valid saved version available; a missing required binding prevents availability.
- Generating a report uses an available template in the request's language and the approved result versions, excluding cancelled tests.
- Nobody can edit a report draft. Correcting a generated business value goes through business records, regeneration and fresh review.
- A failed conversion prevents PDF preparation, and an old task cannot sign a new candidate.
- A signer's preview, approval record and signing input identify the same candidate PDF. Changing printed issue metadata requires another candidate and review.
- Changing the template of an unsigned draft invalidates its PDF. A draft with signatures stays locked until permitted withdrawals; an issued report requires a change request.
- A template update or customer-profile change leaves an issued report's files and printed data unchanged.
- A Viettel Sign retry uses the original candidate; it cannot pick up a newer DOCX or template.
- With digital signing on, a report stays unissued until its approved candidate has been digitally signed and stored. An outage preserves the approvals, and a successful retry issues that version once without repeating a release notification or replacement transition.
- With digital signing off, the approved candidate is stored and issued without a digital signature. Turning signing on later does not rewrite an already issued PDF.
- A customer receives only the issued PDF, and a person without request access cannot read its draft through a working folder.
- Download and delivery of an issued PDF work when ONLYOFFICE is unavailable.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#reports-and-change-requests)
- [Administrator](../functional/laboratory_module/features/admin.md#6-report-templates-us-ad36)
- [Lab head](../functional/laboratory_module/features/lab-head.md#1-test-reports-us-lh01-to-us-lh03)
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Laboratory files](laboratory-files.md)
- [Digital signing](digital-signing.md)
- [Shared technical implementations](../functional/shared.md)
