# Shared questions

- **Withdrawing after losing the permission or the role.** A signer withdraws their own signature or rejection; the documents say nothing more. On every document type, withdrawing does not check again that the person holds the `sign` permission and the role of the level. May a signer who has lost the permission or the role still withdraw, or is withdrawing refused like signing? (US-HD16, SH-04)
- **Signed PDFs after the certificate expires.** The laboratory is warned before its Viettel Sign certificate expires and renews it, but a PDF signed earlier carries no timestamp or long-term validation data. Does such a PDF still verify once the certificate has expired or been revoked? (SH-04)

- **Bounced mandatory emails.** How does a customer still get a mandatory email that bounced? Proposed answer, not decided: the notice stays in the portal, sales is told to contact the customer, and nothing is sent again to an address flagged as bouncing.
- **Uninstalling E-commerce.** What happens to test requests linked to orders when E-commerce is uninstalled? Proposed answer, not decided: test requests keep the order number as text, and uninstalling warns first.
- **Changing a chain while documents are being signed.** Does a document being signed keep its chain's old levels or take the new ones? Proposed answer, not decided: a document keeps the levels it had at its first signature; a changed chain applies to documents signed afterwards.
- **Signers on leave.** Can a signing level be handed to a backup while its only signer is away? Proposed answer, not decided: the level's role is given to a backup for a limited time, audited, so nobody signs on another's behalf; overdue signing tasks remind.
- **Notices about one's own actions.** Is a person notified of their own action, such as claiming a task? Proposed answer, not decided: nobody is notified of their own action; one open notice per task, person and event type.
- **Tasks for a role nobody holds.** Where does a task go when nobody holds its role or claims it? Proposed answer, not decided: administrators are told, and the task is listed as unassigned; archiving the last holder of a role an active task type uses warns.
- **Two signatures by one person.** The Head of Department may approve a result they entered, and the Lab Head signs the report. May one person hold signatures at two levels of a longer chain on the same document version? (blocks SH-04)

## Related documents

- [Shared technical features](../docs/functional/shared.md)
