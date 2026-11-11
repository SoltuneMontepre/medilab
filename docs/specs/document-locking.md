# Document locking

Stories: SH-06

## Goal

Two users never change the same document at the same time. The second user sees who is editing and since when, cannot save, and can ask to be told when the document is free. A lock never outlives its holder's activity, and a long operation cannot run twice.

## Design

### Locks

- A lock (`medilab.document.lock`) names a document by its technical name and id, its holder, its kind, `edit` or `operation`, and the holder's last activity. When it was taken is Odoo's creation time of the row.
- Its status is `active`, `released` or `expired`. A released or expired lock keeps when and why it ended: `saved`, `cancelled`, `left`, `completed` for an operation that ended, `expired`, or `released_by_administrator` with the administrator.
- A partial unique index on the document where the status is `active` keeps at most one active lock per document; a second user taking a lock at the same moment is refused.
- The inactivity period is the system parameter `sol_laboratory.lock_timeout_minutes`, 15 minutes by default, in the Laboratory block of [Settings](settings.md). A lock whose last activity is older is no longer in force: it expires when someone next needs the document, and the scheduled job `document_locks.expire` expires the rest every 5 minutes, one item per lock.

### Lockable documents

Every Laboratory document model that has an edit permission inherits `medilab.lock.mixin`; a test fails when one is left out. The mixin:

- refuses `write` and `unlink` of a document another user holds an active lock on, naming the holder and since when. Writes with full rights, such as jobs and system steps, are not refused;
- releases the current user's own editing lock with reason `saved` after they write the document;
- adds a banner below the form's header, shown only while another user holds the lock: who is editing and since when, and a button to be told when the document is free, hidden once the user asked;
- offers the form `lock_take`, which takes the lock or refreshes the user's own, `lock_release` with `cancelled` or `left`, and `action_lock_watch`.

Taking a lock needs the right to change the document; others still read it.

### In the form

A patch of Odoo's form controller acts on forms whose model has the mixin:

- The first change of an existing record takes the lock. While the user keeps editing, each change refreshes the last activity, at most once a minute; a user who stops typing for the inactivity period loses the lock.
- When the lock is held by someone else, the form shows who holds it, discards the change and reloads.
- Saving releases the lock on the server. Discarding releases it as `cancelled`, and leaving the record or the form releases it as `left`. A closed browser releases nothing; the lock expires after the inactivity period.
- Taking and releasing a lock is sent on Odoo's bus to the group of internal users with the document's model and id. An open form of that document that has no unsaved change and no dialog open over it reloads, so its banner appears or disappears without the user reloading. A dialog that adds or edits a line of the form keeps its changes outside the form until it is saved, so a reload under it would drop them.

### Watchers

A user who asks to be told is added to the lock's watchers. When the lock is released or expires, the watchers get the notification event `document_lock.released` once, keyed on the lock, through their notification preferences.

### Long operations

`_operation(documents)` on the lock model holds an `operation` lock on each document while a block runs and releases it as `completed`. It first locks the documents' rows without waiting, as claiming a task does, so a second start of the operation while the first runs is refused at once, even before the first one's lock row is visible to other transactions. An operation is refused while another user holds an editing lock, and the user's own editing lock gives way to it. Signing a document with an approval chain and recording a test report's delivery run as operations.

### Stuck locks

The Document Locks screen under Jobs lists active locks by default, with their released and expired history. An administrator with the permission to release document locks releases a stuck one; the release writes an `unlock` entry on the document in the [audit trail](audit-trail.md). Locks themselves are not audited.

## Related documents

- [Shared technical features](../functional/shared.md): SH-06
- [Settings](settings.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
