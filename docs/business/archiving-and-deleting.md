# Archiving and deleting

How a record stops being used. The administrator documents of each module state which document types can be archived and which can be deleted.

## Rules

- **In use.** A record is in use while an active record or an unfinished document refers to it, such as a unit on an active parameter and method pair, or a machine on a scheduled booking. A document is finished once it reaches a final state, such as done, cancelled or signed.
- **Archive.** A record can be archived only when it is not in use. Finished documents keep referring to it, so past quotations, results and reports keep showing it. Archived records do not appear in selection lists.
- **Delete.** A record can be deleted only when nothing refers to it at all, finished documents included. Deleting a record also deletes the parts that belong only to it, such as a tax's rates or a package's lines.
- **Refusal.** Archiving or deleting a record that is still referred to is refused with a message that lists the records referring to it. The user finishes, archives or removes those first.
- **Settings without history.** Records that no document keeps a reference to, such as roles, are not archived. They are deleted once nothing refers to them.

## Acceptance criteria

- Archiving a record that an unfinished document or an active record refers to is refused with a message listing them.
- Once those documents are finished and those records archived, the record can be archived, and finished documents still show it.
- Deleting a record that any record refers to, finished or not, is refused with a message listing them.
- A record that nothing refers to can be deleted.

## Related documents

- [Laboratory administrator](../functional/laboratory_module/features/admin.md)
- [E-commerce administrator](../functional/ecommerce_module/features/admin.md)
- [Approval and signing chain](approval-and-signing-chain.md)
