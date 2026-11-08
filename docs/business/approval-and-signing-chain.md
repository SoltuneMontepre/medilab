# Approval and signing chain

- **Approving is signing.** Both mean "I allow this to proceed and I take responsibility for it". There is one concept, not two.
- For the user, signing is one click of a button.
- When a document or report is generated, the signatures of the people its approval rules name are attached automatically.
- A signed document is locked: it cannot be changed or discarded, even by its owner.
- Until the document's process is completed, a signer at any level, the final level included, can withdraw their own signature, even after losing the permission or the role of their level. Withdrawing follows the timeline: it is refused only while a signature given after theirs stands.
- Once a result, report or quotation completes its process, no signature can be withdrawn; changes use a change request producing a linked version.
- The Head of Department approves results, including results they entered. Other result entrants cannot approve their own results. The Lab Head reviews the approved results and signs the final report, including reports with results self-approved by a Head of Department.
- A person signs at most one level of a document version. A Head of Department approving a result they entered is the only exception.
- A document keeps the chain levels it had when its signing process started; a changed chain applies only to signing processes started afterwards. The signing process of a document version starts with its first signature or rejection.
- A level can be signed by any holder of its role, or by a holder of a higher level's role in the same chain, in their own name, so the responsibility moves to the person who signs; that person then signs no other level of the document version. When no holder of the top level is available, an administrator gives its role to a backup for a limited time, recorded in the audit trail. Nobody signs on another person's behalf.
- A report signature binds its saved DOCX, template and business-data versions, result versions and the prepared PDF the signer reviewed. Editing an unsigned draft or changing its source data invalidates that PDF; a signed draft is locked until permitted withdrawals. After the final approval, digital signing uses that prepared PDF and never regenerates it from later edits. Store the signed PDF before issuing the report; a signing failure preserves approvals and leaves it unissued while signing is retried. When digital signing is off, store the approved prepared PDF and issue it without a digital signature. See [Test reports](../specs/test-reports.md).
- A correction to a result in an issued report automatically links or creates its report change request. A report awaiting signature returns to draft before corrected results are applied. After the required change-request approvals and approval of all corrected results, create a replacement draft and a fresh signing task. Issue the corrected report after the Lab Head signs it and its PDF is stored, digitally signed when signing is on; only issuing the replacement marks the previous report replaced and notifies the customer that the new PDF is ready.
- Each signature keeps its own record of who signed and at what level when it was applied. A later change to the signer's role or account does not change an existing signature.
- A signature never changes once it is given, not even by an administrator. Only withdrawing it, or restarting the document's chain, records when it was withdrawn, once; a withdrawn signature is never put back in force.

## Related documents

- [Shared technical features](../functional/shared.md): SH-04 signatures and digital signing, SH-07 signed documents are locked
