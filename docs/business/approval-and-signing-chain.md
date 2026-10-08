# Approval and signing chain

- **Approving is signing.** Both mean "I allow this to proceed and I take responsibility for it". There is one concept, not two.
- For the user, signing is one click of a button.
- When a document or report is generated, the signatures of the people its approval rules name are attached automatically.
- A signed document is locked: it cannot be changed or discarded, even by its owner.
- A signer can withdraw their own signature only after every higher level has withdrawn theirs.
- Once the final level has signed, changes go through a change request that produces a new linked version.
- Each signature keeps its own record of who signed and at what level when it was applied. A later change to the signer's role or account does not change an existing signature.

## People data source

- A source provides only people, with their role and department. Permission-based access control, signing levels and approval rules belong to this system and are configured here, whichever source is active.
- The signing chain reads people through one source interface. It never reads them from a source directly.
- The laboratory module is the default source. An admin can configure the system to take people from the HR module instead. Other sources can be added by implementing the same interface.
- One source is active at a time. Choosing the source is the only source configuration; if a source lacks data this system needs, the admin reconfigures it.
- People taken from the HR module are not recreated in the laboratory module. This system refers to people and departments by the source's identifier and reads their current names from the source.
- A person or department removed from the source is never deleted here. This system keeps a copy of the data it has recorded, for legal retention. Approval rules that name a removed department are repointed by an admin.
- Switching the source carries nothing over. The admin configures permissions, signing levels and approval rules again for the new source's people.

## Related documents

- [Shared technical features](../functional/shared.md): SH-04 signatures and digital signing, SH-07 signed documents are locked
