# Digital signing

Stories: SH-04

## Goal

A fully signed document prints as a PDF that Viettel Sign digitally signed with the laboratory's certificate, stored once and returned on every download. A document still under approval prints as a marked draft. Anyone can check a signed PDF on a public page. An outage of Viettel Sign never loses the approval: the signing waits and is retried.

## Design

### Certificate

- The laboratory's certificate is a `medilab.signing.certificate` read from Viettel Sign: its credential id, subject, issuer, serial number, validity and certificate chain, leaf first. Certificates are not created or edited on the screen.
- The daily job `digital_signing.certificates` reads the account's certificates from Viettel Sign and updates the records; administrators can also refresh them from the certificates list. A certificate is `valid`, `expired` once its validity ends, or `revoked` when Viettel Sign reports its certificate or its key as not usable.
- Signing uses the valid certificate that stays valid longest. Without one, digital signing stops until a valid certificate is read.
- The same job alerts administrators through the mandatory `signing_certificate.alert` event, which ships with the administrator role as its recipient: once when a certificate comes within `sol_laboratory.signing_certificate_alert_days` days of the end of its validity, 30 by default, once when it expires and once when it is revoked. The expiry alerts are skipped while another valid certificate stays valid past that horizon.

### Viettel Sign

- The account comes from `VIETTEL_SIGN_CLIENT_ID`, `VIETTEL_SIGN_CLIENT_SECRET`, `VIETTEL_SIGN_PROFILE_ID` and `VIETTEL_SIGN_USER_ID`, read from the environment when a call is made, and `VIETTEL_SIGN_URL`, `https://remotesigning.viettel.vn` by default. They are not stored on a record and not written in the log.
- `ViettelSignClient._post` is the only method that opens a connection. The client logs in (`/vtss/service/ras/v1/login`), reads the certificates (`/vtss/service/certificates/info`) and signs a SHA-256 hash with RSA, waiting for the signature (`/vtss/service/signHash` with `async` 0). An HTTP error, a timeout, a body without the expected value or a missing variable raises `ViettelSignError`.
- The account signs without confirmation in the MySign app. An account that asks for one makes every call wait for a confirmation nobody gives, time out and be retried.

### Signing a PDF

- Signing takes the document version's unsigned PDF, adds an invisible PAdES signature field with Odoo's `odoo.tools.pdf.signature`, and sends the SHA-256 of the CMS signed attributes to Viettel Sign. The RSA signature it returns, with the certificate chain, makes the CMS that fills the field. A document type may render this source at signing; test reports supply the stored PDF prepared and reviewed before approval, as specified in [Test reports](test-reports.md#preparing-the-pdf).
- The signed PDF is checked before it is stored: a signature the certificate does not verify counts as a signing Viettel Sign did not confirm, and is retried like an outage.
- The signed file is stored as an attachment of the document, with a `medilab.digital.signature`: the document and its version, the certificate, when Viettel Sign signed and the SHA-256 of the file. A document version is signed once; the record is never edited or deleted. An `integration` audit entry on the document records the signing, and an `error` entry a signing that failed.
- A document type takes part by inheriting `medilab.digital.signing.mixin`, naming its report in `_digital_signing_report` and saying when its approval chain is complete. Fully signed means that the final approval level has signed; it does not require issuance or a digital signature. Test reports supply their prepared source PDF rather than rendering one again, and completion of their approval chain starts digital signing before issue.

### Printing

- Printing the report a document type named returns, for a fully signed document, its stored signed PDF, and signs it first when there is none yet. A document still under approval prints the report with its draft mark. An issued test report always returns its stored issued PDF; printing never rewrites it. Fully signed documents are printed one at a time, because merging PDFs breaks their signatures.
- Digital signing is off until an administrator turns it on in the Laboratory settings. While it is off, a fully signed document prints without a digital signature and without the draft mark. A test report issued while it is off keeps that stored PDF after the setting changes.
- A signed PDF prints the address of the verification page.

### Outage and retry

- When digital signing is on and a document becomes fully signed, its PDF is digitally signed at once. When Viettel Sign fails, the approval stands, the item `<model>:<id>:<version>` is queued on `digital_signing.sign` and the user is told on the screen. The job retries the item with a growing delay, up to 8 attempts; an item that fails for good alerts the administrator as every failed job item does.
- A document whose signing waits in the queue shows that it is pending, with a button to try again now. Printing it also tries again and, when Viettel Sign still fails, tells the user; the queued item stays. A document fully signed before digital signing was turned on is signed the first time it is printed, except an already issued test report whose stored PDF stays unchanged.

### Test reports

- Approval and signing bind the prepared PDF and its DOCX, template and business-data versions. Digital signing and every retry use that same source; a template update or later editor save cannot change it. A marked draft preview is a separate copy and never replaces the prepared source.
- With digital signing on, completing the approval chain signs the prepared PDF. Only after Viettel Sign succeeds and the verified signed PDF is stored is the report issued. Until then the approvals stand, the report remains unissued and pending digital signing, and it cannot be delivered or downloaded by the customer. Failure does not mark a previous report replaced or notify the customer of a release.
- With digital signing off, completing the approval chain stores the prepared PDF without a digital signature, then issues the report.
- Issuance makes the stored PDF available for delivery and customer download and sends the release notification. For a replacement, only issuance marks the previous report replaced. A retry rechecks that the candidate and its approvals still stand; a withdrawn approval or corrected source cannot issue an obsolete candidate.
- Issued PDFs are downloaded and delivered from storage, including while ONLYOFFICE is unavailable. Internal DOCX drafts are not customer downloads.

### Verification

- `/verify` is a public page where a visitor uploads a PDF. It shows three checks: the digital signature verifies with the certificate the file carries, that certificate is one of the laboratory's, and the content is unchanged: the signature covers the whole file and the file is, byte for byte, one the system stored, found by its SHA-256. The file is valid when all three pass.
- A valid file also shows the document, when it was signed, the certificate with its status and validity as Viettel Sign last reported them, and the signatures of the document's approval chain that stand on the signed version: signer, role, level and time.

### Document types of this feature

| Document type       | Actions | Scopes |
| ------------------- | ------- | ------ |
| Signing certificate | read    | all    |
| Digital signature   | read    | all    |

Turning digital signing on, the alert days and refreshing the certificates belong to Odoo's settings group, which the administrator role implies.

## Sandbox

CI does not call Viettel Sign. A check against it needs a Viettel Sign test account that signs automatically:

1. Set the variables, turn digital signing on and refresh the certificates. The laboratory's certificate is listed as valid with its expiry.
2. Complete a test report's approval chain. Its prepared PDF is digitally signed and stored before the report is issued, and opens in a PDF reader as signed with the laboratory's certificate.
3. Upload it on `/verify`: it is valid. Change one byte and upload it again: it is not.

Until that run is done, signing against Viettel Sign is unverified. Tests with the client mocked cover the same rules.

## Related documents

- [Shared technical features](../functional/shared.md): SH-04, Viettel Sign
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Settings](settings.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
- [Test reports](test-reports.md)
