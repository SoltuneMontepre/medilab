# Laboratory files

Stories: US-T23, US-T24, US-T25, US-T27, US-T28, US-AD29, US-AD30, US-AD31, US-HD15, US-HD16

## Goal

People reach the [laboratory files](../functional/laboratory_module/overview.md#laboratory-files) only through the folders they are members of, and only with the laboratory files permission. One check decides what a person may do with a folder, so the laboratory files API and the features built on folders refuse the same things the same way. Each computer signs in once with the person's login and gets its own key, which stops at once when the computer is revoked. Every saved state of a file is a version that never changes, numbered in order even when two saves of the file come at once. A person editing a file can lock it, so nobody else saves it meanwhile.

## Design

### Permissions

| Document type            | Actions                    | Scopes |
| ------------------------ | -------------------------- | ------ |
| Laboratory folder        | read, create, edit         | all    |
| Laboratory folder member | read, create, delete       | all    |
| Laboratory sync rule     | read, create, edit, delete | all    |
| Laboratory device        | read, edit                 | all    |
| Laboratory file          | read                       | all    |
| Laboratory file version  | read, sign                 | all    |
| Laboratory file change   | read                       | all    |
| Laboratory file lock     | read                       | all    |

- **The create permission on laboratory folders, `laboratory_folder.create.all`, is the laboratory files permission.** Its holders sign computers in and create folders they own. Its group also carries accesses of its own: its holders read the folders they are members of, the members and sync rules of those folders, and their own computers. They change them only through the laboratory files API, which checks them and then writes with full rights.
- Folder administration is `laboratory_folder.edit.all`. With the read permissions of every folder, member, sync rule and computer, and the other permissions above, administrators see and change them all in the back office.
- Files, versions and changes have only `read`: they are made by saving files, through the method below, and never changed or deleted. The laboratory files permission also reads the files and versions of its holder's folders. Versions also have `sign`, for [signing them](#signing-versions).
- Locks have only `read` too: they are taken, renewed and unlocked through the laboratory files API, and administrators release one as folder administrators. The laboratory files permission reads the locks of its holder's folders.
- Folders have no archive or delete action: archiving a folder is editing it, and folders are never deleted. Members change their role only with the folder's owner, so they have no edit action. Computers are created by signing in and revoked by editing; they are never deleted.

### What a person may do with a folder

`_check_folder_access(access)` on `medilab.laboratory.folder` refuses the user what they may not do with the folders, as a `LaboratoryFileError`: a user error carrying the code the API answers with. The API and later features call it, then act with full rights.

| Access       | Allowed when                                                                                                               | Refused with                           |
| ------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `read`       | The person holds the laboratory files permission, is a member of the folder and, for a folder of a sample, sees the sample | `permission_denied`, `not_found`       |
| `write`      | `read`, and the folder is neither archived nor turned off                                                                  | `folder_archived`, `folder_disabled`   |
| `share`      | `read` and the person owns the folder, or the person administers folders; and the folder is not archived                   | `permission_denied`, `folder_archived` |
| `administer` | The person administers folders                                                                                             | `permission_denied`                    |

- A person who is not a member gets `not_found`, as for a folder that does not exist, so the answer does not tell that the folder exists. So does an administrator who is not a member, except for `share`.
- `share` and `administer` are refused with `locked` while someone else holds the folder's [document lock](document-locking.md), because writing with full rights would pass over it.
- Odoo evaluates access domains with full rights, so an access cannot test whether the person sees a folder's sample. The check tests the sample in the person's own environment.

### Administering a folder

Administrators administer folders in the back office; each action checks `administer` and is recorded in the audit trail as an edit of the folder.

| Action             | What happens                                                                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Turning off        | The folder refuses `write`: nobody uploads to it, and its members still read it. It is still renamed, its rules changed and its members added and removed, since it can be turned on again. |
| Turning on         | The folder takes uploads again.                                                                                                                                                             |
| Archiving          | The folder records when it was archived, and its retention date is the retention period of archived folders from today. There is no unarchiving.                                            |
| Changing the owner | The new owner's row becomes the owner's and the previous owner stays a member. The new owner must be able to be a member, and must not own a folder of the same root already.               |

- An archived folder is read only, for its owner and members too: it refuses `write` and `share`, and the folder, its rules and its members cannot be changed. Administrators still remove its members in the back office, so access to it can always be withdrawn. It is no longer turned off or on, archived again or given another owner.
- The retention period of archived folders is the system parameter `sol_laboratory.laboratory_folder_retention_days`, in the Laboratory Files block of [Settings](settings.md), at least 1 day. It is 1825 days by default, an assumption until the laboratory gives one. What happens once a folder's retention date has passed is an open question.

### Back office

The Documents menu of the Laboratory app lists Folders, Files, File Versions, File Locks, Folder Members, Sync Rules and Computers. Files, versions and locks are only read there, and a folder's form lists its files. People with the laboratory files permission see their folders, with their members and rules, and their own computers there. They create folders of their own, as Medilab Sync does, and change nothing else: owners manage their folders from Medilab Sync. A sample's folders are created from the sample ([Creating a sample's folders](#creating-a-samples-folders)); otherwise only administrators create a folder for someone else or set a folder's sample. Administrators see and change them all: they turn folders off and on, archive them, change their owner, add and remove members, change rules and revoke computers. Members are added on their folder; the Folder Members list removes them, from an archived folder too.

A folder of a sample, its members, sync rules, files, versions, locks and changes are shown only to people who see the sample, administrators included; see [Sample folders](#sample-folders).

### Members

- Creating a folder adds its owner as a member with the role `owner`. A folder has one owner row, held by a partial unique index, and the owner row cannot be removed.
- Only active internal users holding the laboratory files permission are added as members. Anyone else is refused with `not_eligible` and one message that does not say why.

### Names, never paths

The API never receives or stores a path on anyone's computer:

- A folder's name and its root, the name it was created with, are one name each: no separator, drive, home folder or parent folder. Renaming changes the name; the root never changes, and it is unique for the owner.
- Folder names, roots, sync rule patterns and file paths are kept in Unicode NFC, so a Vietnamese name typed on two computers is the same text.
- A sync rule's name prefix is the start of a file name without `*`, its name pattern is a file name whose only wildcard is `*`, and its extension is letters and digits. An extension is kept without its dot and in lowercase, so `.PDF`, `.pdf` and `pdf` are one rule, and a file matches it when its own extension, in lowercase, is the same.

### Files and versions

A file (`medilab.laboratory.file`) is a path in a folder and a series of versions (`medilab.laboratory.file.version`), one of them current. Each time a file's current version changes, a change row (`medilab.laboratory.file.change`) is added; a computer reads its folder's changes after the last one it saw.

- A path is relative to its folder, such as `HPLC/run-01.csv`: names separated by `/`, never a root, drive, home folder or parent folder. It is kept in Unicode NFC. Paths that differ only in letter case are one file, which keeps the letter case it was first saved with: its `path_key`, the path in NFC and one letter case, is unique in the folder. A file is never renamed, moved or deleted, so renaming and deleting are not passed between computers.
- A version's number, file, parent and restored versions, source, size, SHA-256, storage key, person and computer never change, and versions, files and changes are never deleted, administrators included. When a version was stored is Odoo's creation time of its row. Fields a later feature adds to versions, such as their signing state, are not part of that list.
- Sizes are 64-bit integers (`fields/big_integer.py`), as files reach 5 GiB and Odoo's integers stop at 2 GiB. A version's SHA-256 is 64 lowercase hexadecimal digits.
- A file is raw data when its folder holds a sample's raw data, `_is_raw_data()`; a folder without a category holds none. It is an Office document when its extension is `docx`, `xlsx` or `pptx`, in any letter case, `_is_office_document()`. What applies to files of folders without a category is decided by the features built on files.

#### Storing a version

`file._add_version(sha256, size, storage_key, source, user, device, base_version, restored_from)` is the one way a version is stored. Uploads, restores and the online editor's saves all call it, after checking access with `file._check_file_access("write")`; `_get_or_create(folder, path)` finds or makes the file of a new path first.

1. `_check_can_add_version(user, device)` refuses a version that breaks a rule every save obeys, whoever stores it and with whatever rights: the folder is archived (`folder_archived`) or turned off (`folder_disabled`). **It is the extension point of the features built on files**, which add their own rules there, such as a lock someone else holds, so a caller that skips the access check still cannot pass them.
2. The file's row is updated, which locks it (see below).
3. Content with the current version's SHA-256 adds nothing, whatever version the save was made from, and the current version is returned. A restore is the exception: it always adds a version with the content of the version it restores.
4. The version takes the number after the file's last one, and the version that is current as its parent.
5. A save made from a base version that is no longer current is kept as a `conflict` version and the current version stays. Otherwise the version becomes current through `_make_current()`, which adds the change row and refuses to move the current version back to an older one. Writing the current version any other way is refused.

#### Two saves at once

Two saves of the same file at once, such as an upload and a save of the online editor, never take the same number or skip one:

- Every save updates the file's row before it numbers its version, a conflict too. The second save waits for the first; once the first commits, the second fails with a serialization error, because the row changed after its snapshot, and Odoo's request retrying runs its whole request again, which now sees the first save's version. A lock alone would not do: the second save would number its version from a snapshot without the first one, and the duplicate number would fail without a retry.
- The number is the file's highest one plus one, read under that lock, not a database sequence, so a save that is rolled back leaves no gap.
- Two first saves of one new path make one file: the second one's creation fails on the unique path key, which `_get_or_create()` turns into a `ConcurrencyError`, and Odoo runs the request again.
- **Everything a caller does before `_add_version()` in the same request must be safe to run twice**, as a concurrent save runs the whole request again: the storage calls of uploads, and fetching the edited document from the online editor. Saves outside a web request, such as jobs, are not run again.

`laboratory_files_concurrency_case.py` runs such races in two real database transactions, the second through Odoo's request retrying, and gives the second one's record or the refusal it got; `test_laboratory_file_version_concurrency.py` races saves with it.

#### Access

`file._check_file_access("read" | "write")` checks reading and writing a file through its folder's `_check_folder_access()`: membership, the sample of a sample folder, and whether the folder is archived or turned off. Versions are checked through their file.

### File locks

A person editing a file in their own program locks it (`medilab.laboratory.file.lock`), so nobody else saves it until they unlock it or the lock expires. The lock belongs to the person; the computer it was taken from is recorded for information. When it was taken is Odoo's creation time of its row.

- A file is locked when it is neither raw data nor an Office document, in a folder of working documents, of results or of no category, `_is_lockable()`. Report files are not locked, and Office documents are edited together online instead.
- A lock is `active`, `released` or `expired`. A partial unique index on the file where the status is `active` keeps one active lock per file. A lock lasts the system parameter `sol_laboratory.laboratory_file_lock_minutes` from when it was taken or last renewed, 30 minutes by default and at least 1, in the Laboratory Files block of [Settings](settings.md).
- **A lock is in force while it is active and has not expired.** Every rule treats an expired lock as absent, whether or not it has been marked expired yet, so a lock never blocks a file past its expiry.

| Step      | Method on the file | What happens                                                                                                                                                                                 | Refused with                                      |
| --------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Locking   | `_lock(device)`    | Checks `write`. An expired active lock of the file is marked expired; the person's own lock in force is renewed, otherwise a lock is taken.                                                  | The refusals of `write`, `locked`, `not_lockable` |
| Renewing  | `_renew_lock()`    | Checks `write`. The person's lock in force lasts the lock duration from now. A lock that expired is not renewed, since someone may have saved the file meanwhile: the person locks it again. | The refusals of `write`, `not_locked`             |
| Unlocking | `_unlock()`        | Checks `read`, so a holder unlocks a folder turned off meanwhile. The person's lock is released; a person holding none has nothing to release.                                               | The refusals of `read`                            |

- `_check_file_access("write")` refuses with `locked` a file someone else holds a lock in force on, naming them and until when, so the API refuses an upload before its bytes are sent. `_check_can_add_version()` refuses the same for the person saving, so no upload, restore or online save of someone else stores a version over the lock, whoever stores it and with whatever rights. The holder saves the file as usual; saving neither renews nor releases the lock.
- A lock that expired is marked `expired` when someone next locks the file or its holder unlocks it, and the scheduled job `laboratory_file_locks.expire` marks the rest every 5 minutes, one item per lock, so every lock gets its end in the back office and the audit trail. Its end is the time it expired, not when it was found.
- Released and expired locks are removed by the [cleanup job](scheduled-jobs.md#cleanup) after the retention period of locks, as document locks are; their audit entries stay.

- **Back office.** File Locks lists the active locks by default, with their released and expired history, and a file shows who holds its lock in force and until when, in its list and its form, with the file's locks. Folder administrators release a lock someone left: the release checks `administer` on the file's folder, and a lock already past its expiry is recorded as expired instead.
- **Audit.** Locks are audited as parts of their file, so the file's history shows them: taking a lock is the creation of the lock, and unlocking, expiring and an administrator's release are edits of its status, the release naming the administrator. Renewing a lock writes no entry, as when a lock expires is left out of the trail.

#### Two locks at once

Two people locking the same file at once end with one holder. Locking updates the file's row, without changing it, before it looks for a lock, as every save does before it numbers its version. The second one waits for the first; once the first commits, the second fails with a serialization error and Odoo's request retrying runs it again, when it is refused with `locked`. A lock and a save of someone else at once are ordered the same way: a save that started before the lock committed runs again and is refused, and a lock taken while a save is stored runs again and locks the saved version. Locking the row without updating it would not make a save that started earlier fail. The unique index refuses a second active lock that skipped the row.

### Computers

A signed-in computer is a `medilab.laboratory.device` of its person, one per installation of Medilab Sync: the installation id the application generates once is unique for the person. Its name is one name and its platform is Linux or Windows.

| Step        | What happens                                                                                                                                                                                                                                                                  | Refused with                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Signing in  | Odoo checks the login as it does for its external API: with the password, or, for a person with two-factor authentication, with one of their API keys in its place. The password is never kept. The computer is created, or found by its installation id, and gets a new key. | `invalid_request`, `invalid_credentials`, `permission_denied`, `device_revoked` |
| A call      | Odoo verifies the key; the computer is the one holding the key's row and not revoked. Its last call is written at most once a minute, so parallel calls do not fight over its row.                                                                                            | `invalid_key`                                                                   |
| Signing out | The key is removed; the computer can sign in again and gets a new key.                                                                                                                                                                                                        |                                                                                 |
| Revoking    | The key is removed and the computer is revoked for good. A person revokes their own computers, administrators any computer. The person's folder memberships and other computers stay.                                                                                         |                                                                                 |

- The key is an Odoo API key of the person, in `res_users_apikeys`, with the scope `sol_laboratory.device`. Odoo keeps only its hash, and the scope makes it open the laboratory files API and nothing else, not Odoo's external API. It does not expire: it stays valid until the computer signs out or is revoked. The device keeps only the id of the key's row, and signing in again removes the old key first.
- A person with two-factor authentication cannot sign in with their password: Odoo refuses passwords outside its own sign-in screen for them. They sign in with an Odoo API key in its place, one with the scope `rpc`, which is the scope of the keys a person creates in their Odoo preferences. A key of any other scope is refused there, a computer's key too, so one computer's key never signs another in.
- Odoo verifies the key's hash before the call reaches the laboratory files API, and that hash is deliberately slow. So the computer of a call is found by the key's row with the person, the scope and the key's index, as Odoo finds it, with the same expiry; the hash is checked again only when two of the person's keys share an index.
- Removing a computer's key from anywhere signs the computer out, also from the person's Odoo preferences or as an administrator. Odoo makes no foreign key to its API keys, so removing one empties the key of its computer first, which records the sign-out in the audit trail. Odoo's cleanup of expired keys deletes rows with SQL and would pass over it, but computers' keys never expire.
- Revoking is final, also for a person's own computer: the revoked installation cannot sign in again. The computer gets back in as a new installation of Medilab Sync, which generates a new installation id and signs in as a new computer. Whether administrators can restore a revoked computer is an open question.
- Signing in, signing out and revoking are recorded in the [audit trail](audit-trail.md) as the creation and edits of the computer: signing in creates it or changes its key, signing out empties its key, and revoking empties its key and sets when it was revoked. The key's row is named, never the key.

#### Risks

- Odoo's only brake on guessing passwords is its login cooldown, which counts failures per Odoo worker. Signing in is not rate limited otherwise, so many attempts against one login can reach Odoo; the route needs a rate limit in front of Odoo, as the webhooks have.

### Sample folders

A folder of a sample holds the files of one category of its work: raw data, working documents, results or reports.

- A sample has one folder of each category, held by a unique key on the sample and the category. A folder of a sample needs a category; a folder of no sample may have one too, and several such folders may share it.
- Once a folder holds files, its sample and its category never change, so its files keep meaning what they were saved as, such as a signed result of that sample. The folder's form shows them read only then.
- Everything of a sample's folder is seen only by people who see the sample, whoever they are, folder administrators included: the folder, its members, sync rules, files, versions, locks and changes, in lists, forms and links. Each of these models inherits `medilab.laboratory.sample.folder.mixin`, which adds to the model's access domain for every operation that the record's folder belongs to no sample or to a sample the user reads, with the sample's own access domain for the user. An access domain is evaluated with full rights, so it cannot test the sample itself; the sample's access domain, which Odoo builds for the user, can. A model a later feature adds under folders or files inherits the mixin too, naming the path to the sample in `_sample_field`.

#### Creating a sample's folders

**Create Folders** on the sample adds the raw-data and result folders it does not have yet. The head of a department that tests the sample creates them, holding the laboratory files permission and seeing the sample; anyone else is refused with `permission_denied`. Who creates a sample's folders, and when, is an open question: `_check_can_create_laboratory_folders()` on the sample alone decides it, so another answer changes only that method.

- The new folders are owned by the person who creates them, upload-only and without sync rules, so every file is synced. The owner adds the members.
- They are named after the lab code only, which testers see: `<lab code> Raw Data`, with the root `<lab code>-raw`, and `<lab code> Results`, with the root `<lab code>-result`. When the owner already has a folder of that root, nothing is created and the person is told.
- Creating them again adds nothing. Two creations at once make one folder of each category: the second one's creation fails on the unique key, `_create_laboratory_folders()` turns it into a `ConcurrencyError`, and Odoo runs the request again, which finds the folders.
- The sample's form opens its folders the person sees.

### Signing versions

A version of a result file is approved by signing it through the [approval and signing chain](../business/approval-and-signing-chain.md) of laboratory file versions, `medilab.laboratory.file.version`: each version is a document of the chain, signed level after level by the roles its levels name, and the signature belongs to that version and its content. The chain is set up by administrators; without it, signing a version is refused.

| Step        | Who and what                                                                                                                                                                                                                                                    |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Signing     | A member of the folder who sees its sample, holds the `sign` permission of versions and the role of the next level signs the current version of a file in a result folder. The signature records the signer, their role and level, the version and its SHA-256. |
| Rejecting   | The same person rejects the version instead, with a reason; a rejection without one is refused. The person who saved the version is told why, through the mandatory `laboratory_file_version.rejected` event, once for each round.                              |
| Withdrawing | A signer withdraws their own signature or rejection once every higher level has withdrawn theirs, as in every chain. Withdrawing the last one leaves the version unsigned, and the next signatures record the next round of `document_version`.                 |

- Only the current version of a file in a result folder is signed or rejected. A conflict version is never current, so it is never signed.
- A newer version of the file starts unsigned: the file shows the signing state of its current version, and the older version keeps its signatures.
- Signing never stops a save, the online editor or a lock: a signed version is already never changed. Its number, content, hash and origin are protected for good, as every version's are. The fields signing adds are not part of that list: the signing state changes as people sign, reject and withdraw, and only through them; the round, `document_version`, cannot change while a signature stands, as in every chain.
- Each signature of the chain records the hash of its document's content in `document_hash`, from `_approval_document_hash()`; for a version it is its SHA-256, and for document types without one it is empty.
- Signing and rejecting take the file's row without changing it, so a signature and a concurrent save of the same file wait for each other and the second one runs again: a signature that comes after a newer version is refused, and a save after a signature adds an unsigned version. The file's last save stays as it was.
- The level whose signer must belong to the department that did the work is refused for versions: a sample is tested by several departments, and the chain takes one department per document. Which one counts is an open question.
- When a version's process is completed, so that its signatures can no longer be withdrawn, is an open question; until it is answered, they can always be withdrawn.
- Signing, approving, rejecting and withdrawing are recorded in the [audit trail](audit-trail.md) on the version.
- In the back office, a version's form signs it, rejects it with a reason and withdraws a signature, each button shown only to the person who may use it now, and shows its signing state; its signatures are listed to people who read signatures. Lists of files and versions show the signing state of each, and filter versions that are signed, being signed or rejected.
- Whether a signed version is also digitally signed through Viettel Sign, and whether the person who saved a version may sign it, are open questions.

## Related documents

- [Laboratory overview](../functional/laboratory_module/overview.md#laboratory-files)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Permissions](permissions.md)
- [Document locking](document-locking.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
