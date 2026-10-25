# Approval and signing chain

- **Approving is signing.** Both mean "I allow this to proceed and I take responsibility for it". There is one concept, not two.
- For the user, signing is one click of a button.
- When a document or report is generated, the signatures of the people its approval rules name are attached automatically.
- A signed document is locked: it cannot be changed or discarded, even by its owner.
- Until the document's process is completed, a signer at any level, the final level included, can withdraw their own signature while they can still sign it: they hold the permission and the role of their level. Withdrawing follows the timeline: it is refused only while a signature given after theirs stands.
- Once a result, report, quotation or order completes its process, no signature can be withdrawn; changes use a change request producing a linked version.
- The Head of Department approves results, including results they entered. Other result entrants cannot approve their own results. The Lab Head reviews the approved results and signs the final report, including reports with results self-approved by a Head of Department.
- The laboratory's configured technical approval chain approves comparison presets and authored or changed request criteria. Applying a preset unchanged inherits its approval without another request approval or signature. Record the source approval and the selection separately; edit permission cannot approve changed criteria. Approved plan versions are immutable; a replacement preserves its inherited or direct approval basis. See [Conformity assessments](../specs/conformity-assessments.md).
- A report signature binds its saved DOCX, template and business-data versions, approved comparison plan, assessment records, result versions and the prepared PDF the signer reviewed. Editing an unsigned draft or changing its assessment sources invalidates that PDF; a signed draft is locked until permitted withdrawals. Digital signing uses the prepared PDF and never regenerates it from later edits. See [Test reports](../specs/test-reports.md).
- A correction to a result in an issued report automatically links or creates its report change request. A report awaiting signature returns to draft before corrected results are applied. After the required change-request approvals and approval of all corrected results, create a replacement draft and a fresh signing task. Issue the corrected report after the Lab Head signs it; only issuing the signed replacement marks the previous report replaced and notifies the customer that the new PDF is ready.
- Each signature keeps its own record of who signed and at what level when it was applied. A later change to the signer's role or account does not change an existing signature.

## Related documents

- [Shared technical features](../functional/shared.md): SH-04 signatures and digital signing, SH-07 signed documents are locked
