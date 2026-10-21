# Laboratory files

Stories: US-T23, US-T24, US-T25, US-T26, US-T27, US-T28, US-AD29, US-AD30, US-AD31, US-HD15, US-HD16

## Goal

People reach the [laboratory files](../functional/laboratory_module/overview.md#laboratory-files) only through the folders they are members of, and only with the laboratory files permission. One check decides what a person may do with a folder, so the laboratory files API and the features built on folders refuse the same things the same way. Each computer signs in once with the person's login and gets its own key, which stops at once when the computer is revoked. Every saved state of a file is a version that never changes, numbered in order even when two saves of the file come at once. A person editing a file can lock it, so nobody else saves it meanwhile. People edit an Office file together in the browser in one session per file, and no save of the editor is lost. The API is Odoo's own HTTP routes under `/medilab/api/v1`; file content is stored once by its SHA-256 in a private bucket of its own and counts only once the server has verified it; online editing goes through a self-hosted ONLYOFFICE Document Server that nothing else depends on. The [architecture decision](../decisions/laboratory-files-architecture.md) gives the requirements, by ID.

## Design

### Permissions

| Document type              | Actions                    | Scopes |
| -------------------------- | -------------------------- | ------ |
| Laboratory folder          | read, create, edit         | all    |
| Laboratory folder member   | read, create, delete       | all    |
| Laboratory sync rule       | read, create, edit, delete | all    |
| Laboratory device          | read, edit                 | all    |
| Laboratory file            | read                       | all    |
| Laboratory file version    | read, sign                 | all    |
| Laboratory file change     | read                       | all    |
| Laboratory file lock       | read                       | all    |
| Laboratory editing session | read                       | all    |

- **The create permission on laboratory folders, `laboratory_folder.create.all`, is the laboratory files permission.** Its holders sign computers in and create folders they own. Its group also carries accesses of its own: its holders read the folders they are members of, the members and sync rules of those folders, and their own computers. They change them only through the laboratory files API, which checks them and then writes with full rights.
- Folder administration is `laboratory_folder.edit.all`. With the read permissions of every folder, member, sync rule and computer, and the other permissions above, administrators see and change them all in the back office.
- Files, versions and changes have only `read`: they are made by saving files, through the method below, and never changed or deleted. The laboratory files permission also reads the files and versions of its holder's folders. Versions also have `sign`, for [signing them](#signing-versions).
- Locks have only `read` too: they are taken, renewed and unlocked through the laboratory files API, and administrators release one as folder administrators. The laboratory files permission reads the locks of its holder's folders.
- Editing sessions have only `read`: opening a file online and the editing service's saves make and change them, and they are never deleted. The laboratory files permission also reads the sessions of its holder's folders.
- Folders have no archive or delete action: archiving a folder is editing it, and folders are never deleted. Members change their role only with the folder's owner, so they have no edit action. Computers are created by signing in and revoked by editing; they are never deleted.

### What a person may do with a folder

`_check_folder_access(access)` on `medilab.laboratory.folder` refuses the user what they may not do with the folders, as a `LaboratoryFileError`: a user error carrying the code the API answers with. The API and later features call it, then act with full rights.

| Access       | Allowed when                                                                                                                                            | Refused with                                        |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `read`       | The person holds the laboratory files permission, is a member of the folder and, for a folder of a sample, sees the sample                              | `permission_denied`, `not_found`                    |
| `write`      | `read`, and the folder is neither archived nor turned off                                                                                               | `folder_archived`, `folder_disabled`                |
| `share`      | `read` and the person owns the folder, or the person administers folders and, for a folder of a sample, sees the sample; and the folder is not archived | `permission_denied`, `not_found`, `folder_archived` |
| `administer` | The person administers folders and, for a folder of a sample, sees the sample                                                                           | `permission_denied`, `not_found`                    |

- A person who is not a member gets `not_found`, as for a folder that does not exist, so the answer does not tell that the folder exists. So does an administrator who is not a member, for `read` and `write`, and an administrator who does not see the folder's sample, for every access, before any other refusal.
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
- The retention period of archived folders is the system parameter `sol_laboratory.laboratory_folder_retention_days`, in the Laboratory Files block of [Settings](settings.md), at least 1 day. It is 1825 days by default, an assumption until the laboratory gives one. What happens once a folder's retention date has passed is an open question, and so is how that fits versions that are never deleted and content that versions of other folders share.

### Back office

The Documents menu of the Laboratory app lists Folders, Files, File Versions, File Locks, Editing Sessions, Folder Members, Sync Rules and Computers. Files, versions, locks and editing sessions are only read there; a folder's form lists its files, and a file's form its versions and editing sessions. People with the laboratory files permission see their folders, with their members and rules, and their own computers there. They create folders of their own, as Medilab Sync does, and change nothing else: owners manage their folders from Medilab Sync. A sample's folders are created from the sample ([Creating a sample's folders](#creating-a-samples-folders)); otherwise only administrators create a folder for someone else or set a folder's sample. Administrators see and change them all: they turn folders off and on, archive them, change their owner, add and remove members, change rules and revoke computers. Members are added on their folder; the Folder Members list removes them, from an archived folder too.

A folder of a sample, its members, sync rules, files, versions, locks, editing sessions and changes are shown only to people who see the sample, administrators included; see [Sample folders](#sample-folders).

### Members

- Creating a folder adds its owner as a member with the role `owner`. A folder has one owner row, held by a partial unique index, and the owner row cannot be removed.
- Only active internal users holding the laboratory files permission are added as members. Anyone else is refused with `not_eligible` and one message that does not say why.
- A folder has one sync rule of each kind and pattern, held by a unique key on the folder, the kind and the pattern.

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

The SHA-256, size and storage key a version records are those of content the server verified ([Stored content](#stored-content)), never values a computer sent: a save passes the content, and a restore takes them from the version it restores.

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
- Odoo 20 runs a request again (`odoo/http/retrying.py`) after a serialization failure, a deadlock, a lock it could not take or a `ConcurrencyError`, up to 5 tries in all, waiting a random time of up to 2, 4, 8 and 16 seconds between them; after the last try the request fails. Any other integrity error, a unique violation too, is rolled back and answered as a validation error without running again, which is why the unique violations above become a `ConcurrencyError`. Running again rolls back the transaction with its pre-commit and post-commit hooks and the ORM caches, reloads the session, rewinds uploaded files and authenticates again. It undoes no call to the bucket or the editing service.
- **Everything a caller does before `_add_version()` in the same request must be safe to run twice**, as a concurrent save runs the whole request again: the storage calls of uploads, and fetching the edited document from the online editor. A rollback undoes none of them, so they only write new objects under random keys, and content counts only once its row is verified and committed ([Stored content](#stored-content)).
- Odoo's request retrying does not run saves outside a web request, but a [job item](scheduled-jobs.md) that fails is run again later, so the work of a job item is safe to run twice too.

`laboratory_files_concurrency_case.py` runs such races in two real database transactions, the second through Odoo's request retrying, and gives the second one's record or the refusal it got; `test_laboratory_file_version_concurrency.py` races saves with it. It calls Odoo's own `retrying()` outside an HTTP request, so the API's routes are raced through real HTTP requests too, which authenticate again when they run again, and in the deployed configuration.

#### Access

`file._check_file_access("read" | "write")` checks reading and writing a file through its folder's `_check_folder_access()`: membership, the sample of a sample folder, and whether the folder is archived or turned off. Versions are checked through their file.

### Stored content

File content is stored in the laboratory files bucket, a private S3-compatible bucket used for nothing else. Odoo's credentials reach that bucket only; computers never get credentials, only presigned addresses, and file bytes never pass through the API's requests and answers. Content is addressed by its SHA-256 in the database, never by its object key.

- **Objects.** Every upload, and every save of the online editor, is written to an object of its own under a random key the server makes, 32 hexadecimal digits that tell nothing about its content; a key from a client is never accepted. Every upload is a multipart upload the server creates, even of one part, and its presigned addresses are for that upload's parts only, so no address can write the object once its upload is completed.
- **Content.** `medilab.laboratory.content` has a row per object: its key, unique, and its verification state, `pending`, `verified`, `duplicate` or `failed`, with the size and SHA-256 the server computed once it is verified. The SHA-256 is unique among verified content. A version refers to verified content; its SHA-256, size and storage key are the content's.
- **Uploading.** Preparing an upload records the path, the size and SHA-256 the computer claims and its base version, adds the `pending` content row of a new object, creates its multipart upload and gives presigned addresses for its parts. When the file's current version already has the claimed SHA-256, nothing is uploaded and the current version stays, as for any save of the content the file already has. Otherwise the bytes are uploaded, even when the same content is already stored, so knowing a SHA-256 gives no one its content.
- **Verifying.** Finalizing completes the multipart upload and queues its verification. A job item streams the object from the bucket and computes its size and SHA-256; a multipart ETag or a composite checksum is never taken for the SHA-256 of the file. A mismatch with the claim makes the content `failed` and the upload `failed`, with no version. Verification takes one item per batch, so a file of 5 GiB is one batch within the cron worker's time limits, and it reads the object in chunks, so its memory stays under the worker's limit. A verification stopped midway, such as by a killed worker, leaves the content `pending`; its item is claimed again after the job's claim timeout and starts over from the first byte. When they match and verified content with that SHA-256 exists, the new content is `duplicate` and the version refers to the existing content; otherwise the new content is `verified`, and canonical from then on: nothing writes its object again. `_add_version()` then stores the version, and the upload is `completed`, or `conflict`. The computer reads the upload until it ends.
- **Deleting objects.** The object of `duplicate` or `failed` content is deleted once the transaction that set its state commits, so the same content is stored once. A deletion that fails is left to reconciliation.
- **Running twice.** Two finalizations of one upload, Odoo's retrying and a computer repeating a call store one version: the upload's row is updated before its status is read, as a file's row is for a new version, and an upload already past finalizing answers with its result. Two uploads of the same content at once write two objects; the second to be verified fails on the unique SHA-256, and its job item, run again, makes it `duplicate`, so one object stays.
- **What counts.** Content counts only once its row is `verified` and committed. An object written by a transaction that then failed, such as an editor's save Odoo runs again, has no row; reconciliation finds it.
- **Restoring.** A restore adds a version of the content of the version it restores; no byte is copied.
- **Downloading.** A download address is presigned for the object of one version's content, for reading only, after `_check_file_access("read")`. It lasts the system parameter `sol_laboratory.laboratory_file_url_minutes`, 15 minutes by default, in the Laboratory Files block of [Settings](settings.md).
- **Unfinished uploads.** An upload not finalized by its expiry is marked `expired`, its multipart upload is aborted and its content becomes `failed`, by the job `laboratory_uploads.expire`. The bucket's lifecycle rules also abort incomplete multipart uploads after 7 days, in case the job did not.
- **Reconciliation.** The job `laboratory_contents.reconcile` compares the bucket with the rows every day: objects with no content row, `pending` content of no open upload, `duplicate` and `failed` content whose object is still there, and verified content whose object is missing or has another size. It deletes the objects no verified content refers to once they are a day old, and records the rest as errors in the [audit trail](audit-trail.md).
- **Never removed.** Nothing deletes the object of verified content. When the content of laboratory files is removed after their retention is an open question; until it is answered, verified content is kept.
- **Encryption and backups.** The bucket is encrypted at rest and reached over HTTPS only. Object keys say nothing about content, so the database is the index of the bucket: it is backed up outside the provider's site with the bucket, and restoring both is tested: the restored bucket holds the object of every verified content, with its size and SHA-256.

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

### Online editing

An editing session (`medilab.laboratory.editing.session`) is the editing of one Office file together in the browser, through ONLYOFFICE Document Server. Everyone in it edits the version it opened, its base version, and its save is one new version.

| Status      | The session                                                                                                     |
| ----------- | --------------------------------------------------------------------------------------------------------------- |
| `open`      | is edited; a person opening the file joins it                                                                   |
| `saving`    | was asked to save by the editing service, and the save is not stored yet                                        |
| `committed` | saved a version marked edited online, the file's new current version                                            |
| `conflict`  | saved a conflict version, because the file changed after the session opened                                     |
| `closed`    | ended without a new version: everyone left without changes, or the save had the content the file has            |
| `expired`   | had no activity for the idle period; nobody joins it any more                                                   |
| `error`     | could not save: the saved document could not be read, or the person who saved last can no longer write the file |

`open` and `saving` sessions are open: a file has at most one, held by a partial unique index. The other statuses end the session.

#### Which files

`file._check_can_edit_online()` refuses with `not_editable` a file that is not an Office document, a file of a raw-data folder and a file of a report folder. Office files of result and working folders and of folders without a category are edited online.

#### Opening and joining

`_open_for(file)` opens the file online for the user, after `file._check_file_access("write")` and `file._check_can_edit_online()`, so a member opens a file of a folder that is neither archived nor turned off. It then asks the editing service's health check, `_check_editing_available()`, so a person who may not edit the file online is refused for that reason whatever the service's state, and `_join_or_open(file)` joins or opens the session:

- When the file has an open session with activity in the idle period, the person joins it, even when the file has a newer version than the session's base; the session's save then becomes a conflict.
- Otherwise an open session past the idle period expires, and a new session opens on the file's current version, with a new document key and a new callback token. A file with no version yet is not opened.
- The editing service reads the session's base version from a presigned address of its content's object, so the document's bytes do not pass through Odoo.
- Two people opening a file at once make one session: the second one's creation fails on the partial unique index, which becomes a `ConcurrencyError`, and Odoo runs the request again, when it joins the session.
- The callback token is in the address the editing service calls back on. It is an HMAC of the document key with the database's secret, under a scope used for nothing else, so everyone in the session gets the same address, as the editing service calls back on the address of whoever changed the document last. Only its SHA-256 is stored; the session is found by it, and the hash is compared in constant time.

Opening, joining and every call of the editing service are the session's activity. The idle period is the system parameter `sol_laboratory.laboratory_editing_idle_hours`, in the Laboratory Files block of [Settings](settings.md), at least 1 hour and 12 hours by default.

#### Saving

The editing service saves once everyone has left the document; its force save is off, so a session has one save. The save is stored in this order:

1. The saved document is streamed from the address the editing service gives into a new object, never held whole in memory, computing its size and SHA-256 on the way, before any lock. Its content is verified on the way and recorded as an upload's is, `duplicate` when the content is already stored ([Stored content](#stored-content)). When Odoo runs the request again it streams the document again into another object, and reconciliation deletes the first. A session already ended by a save fetches nothing.
   - The editing service gives the address on the origin the browser reached it at. The address is accepted only when its scheme, host and port are those of one of two configured origins: `ONLYOFFICE_INTERNAL_URL`, or `ONLYOFFICE_PUBLIC_URL`, the public address, which Odoo rewrites to the internal origin with the same path and query. Odoo fetches only from the internal address, so a callback cannot make it fetch from anywhere else; an address on any other origin is a failed check.
   - Redirects are not followed and are a failed check. Every read waits at most 60 seconds and the whole fetch at most 15 minutes, within the time limit of Odoo's workers. A document over 5 GiB, by its length or once it has passed that size, ends the session in `error`.
   - `services/saved_documents.py` streams the document in chunks of 1 MiB; `_store_saved_document()` writes them to the bucket and returns the content's SHA-256, size and storage key.
2. The session's row is updated, which locks it as a file's row is locked for a new version, and its status is read again. A session already ended by a save, `committed`, `conflict`, `closed` or `error`, stores nothing: this is the editing service repeating a call it got no answer to.
3. The version goes to the last editor the editing service reports for the save, the last of its `users`; the audit entry names them and everyone its `history` says changed the document. A user is named by the id of the editor configuration, an Odoo user's id. `_check_file_access("write")` is checked for that person; when it refuses, `_check_can_add_version()` refuses the version, or the id is of no active user, the session ends in `error`, and its audit entry records why and the key of the stored content, so the content can be recovered.
4. `_add_version()` stores it as edited online, from the session's base version and from no computer. The session is `committed` with the new version, `conflict` with the conflict version, or `closed` when the content is the file's current content.

A save is never discarded: one arriving for an expired session is stored the same way, and the conflict rule handles a file that changed meanwhile. A save that fails for a while, such as the bucket being unreachable, keeps the session `saving`, or `expired` when it had expired, and answers the editing service with an error, so it calls back again; it gives up with an error status, which ends the session in `error`.

`test_laboratory_editing_concurrency.py` races two opens of a file, two calls of one save, a save and an upload, and a save and the expiry of its session, with `laboratory_files_concurrency_case.py`, through the session's methods and through the editing service's callbacks.

`_receive_callback()` maps each status of a checked callback onto the session:

| Editing service status | What happens                |
| ---------------------- | --------------------------- |
| 1, being edited        | Activity                    |
| 2, ready to save       | The save above              |
| 3, saving failed       | The session ends in `error` |
| 4, closed unchanged    | The session ends `closed`   |
| 6, 7, force save       | Activity; force save is off |
| Any other              | Refused, as a failed check  |

#### The editing service

- The editing service is ONLYOFFICE Document Server Community Edition, a pinned release of 9.4 or later that the tests ran against, in the cluster; `latest` is never deployed.
- The editor configuration and the editing service's calls are signed with the JWT secret `ONLYOFFICE_JWT_SECRET`, which comes from Doppler through the environment, never from the database or the repository. A secret shorter than 32 bytes, the length HS256 needs, counts as no secret: online editing is then unavailable.
- Odoo reaches the editing service at `ONLYOFFICE_INTERNAL_URL` and browsers at `ONLYOFFICE_PUBLIC_URL`, both from the environment.
- **The editor configuration.** `_editor_config(user, document_url, callback_url, lifetime_seconds)` gives the session's configuration with its token, signed for as long as the presigned address of the base version lasts. It names the document key, the file's name and extension, the editor of its extension, the base version's address, the callback address, the user by their Odoo id and name, editing, and force save off.
- **The callback route.** The editing service calls back on a route of its own, outside `/medilab/api/v1`, an exception to the [routes of the API](#laboratory-files-api): it has no computer key, so the route is `auth='none'`, without CSRF and without a session. The callback token in its address and the JWT check it, and it answers in the editing service's format, `{"error": 0}` for success and `{"error": 1}` for an error, never in the API's error format. It is answered with an error only when `_receive_callback()` asks for the call again or a check fails, and what it did before answering is committed.
- **The token header.** The editing service sends its token in the header `Medilab-Editor-Token`, with the prefix `Bearer `, a name of its own so that no authentication of Odoo reads it. Document Server 9.4 also puts a token in the body, whose claims are the body's fields.
- **Checking a callback.** `_from_callback()` checks every callback before anything is stored, and refuses with `EditingCallbackRefused`:
  - every token that comes, in the header or the body, is a JWT signed with that secret and the algorithm HS256 only, and carries an expiry that has not passed, with a minute of clock difference allowed;
  - the header token's `payload`, and the claims of the body token without `iat` and `exp`, are the fields of the body, and agree when both come;
  - the `operation` of a token, when it names one, is `callback`;
  - the session is found by its callback token, and the document key is that session's, compared in constant time.

  A callback that fails a check stores nothing, changes nothing and is answered with an error.
- The network lets the browser reach the editing service's public address, the editing service reach Odoo's callback route and the bucket, and Odoo reach the editing service's internal address. The editing service reaches no other private address.
  - Document Server refuses private addresses unless `ALLOW_PRIVATE_IP_ADDRESS` is on, which it needs to reach Odoo's callback. That switch turns off its own refusal of internal addresses, and people editing a document can make it fetch an address, such as by inserting an image from a link.
  - So the network policy, not Document Server, keeps it from internal addresses: its egress reaches only Odoo's callback port and the bucket's endpoint, nothing else in the cluster and never the provider's metadata address.
- **Health.** The editing service has a health and readiness check of its own, `GET /healthcheck` on its internal address, which answers `true` when it edits documents. The API's readiness never includes it. Opening a file asks it first, waiting at most 3 seconds and following no redirect, and refuses with `editing_unavailable` when it does not answer `true` or the secret is missing. Nothing else depends on the service: syncing, downloading, history and restoring never read sessions or call it, and an open session does not stop uploads of its file; its save becomes a conflict.

#### Expiry

The job `laboratory_editing_sessions.expire` runs every 30 minutes and expires the open and saving sessions with no activity in the idle period. Expiry only stops people from joining: the people still editing lose nothing, as their save is stored when it arrives.

#### Audit

Opening is the creation of the session and every change of its status an edit, recorded in the [audit trail](audit-trail.md) under its file. Joining is an edit entry naming the person, a save's entry names every editor, and an error records why. The token is masked, and activity times are not recorded.

### Laboratory files API

The API is Odoo HTTP controllers in `sol_laboratory` under `/medilab/api/v1`. The versioned OpenAPI 3.1 document `sol_laboratory/api/openapi.yaml` describes every route, its request and answer, the computers' key and every refusal; CI lints it and tests the routes against it.

| Route | Does |
| ----- | ---- |
| `POST /sign-in` | Signs a computer in with the person's login and gives it its key ([Computers](#computers)) |
| `POST /sign-out` | Signs the computer of the key out |
| `GET /devices` | Lists the person's computers |
| `POST /devices/{device_id}/revoke` | Revokes one of the person's computers |
| `GET /health`, `GET /ready` | The API's health and readiness |

- **Routes.** Every route is declared with `laboratory_api_route()` (`services/laboratory_api.py`): `type='http'`, `auth='bearer'`, `bearer_scope='sol_laboratory.device'`, `csrf=False`, `save_session=False`, `readonly=False` and the methods it takes, and the operation of the OpenAPI document it serves. Odoo checks a CSRF token on `type='http'` routes for methods other than GET, HEAD, OPTIONS and TRACE, so the API's routes set `csrf=False`; the computer's key, which a browser never sends by itself, takes its place. Without a key, Odoo's bearer authentication accepts a browser session for a same-origin page opened by the person; the API refuses it with `invalid_key`, as every route needs the computer of the key.
- **Routes without a key.** Signing in gives the key, so it is `auth='public'`; health and readiness are `auth='none'` and read only. They are the only exceptions, and they too set `csrf=False` and `save_session=False`.
- **The computer of a call.** Once Odoo has verified the key, `_from_key()` finds its computer, and only that one: a computer named in the request, such as Medilab Sync's `X-Sync-Device-Id`, is ignored. `_from_key()` relies on that verification of the key's hash, so only bearer routes call it. Saves and locks record the computer it found.
- **Checks.** Every route checks, before it writes with full rights: the key's scope, through Odoo; that the computer is not revoked, through `_from_key()`; and the laboratory files permission, the folder membership and the folder's sample, through `_check_folder_access()` or `_check_file_access()`. Full rights never reach a record the check did not cover. Signing out and revoking one's own computers skip the laboratory files permission, so a person who lost it still stops their computers.
- **Running twice.** A route that changes something has the effect of one run when Odoo's retrying runs it again or the computer repeats a call whose answer it lost. Preparing an upload takes an idempotency key the computer generates, unique for the computer, and a repeat answers with the same upload; the other changes are idempotent by their own rules, such as a lock its holder takes again. A repeated sign-out finds its key gone and is refused with `invalid_key`, which the computer takes as signed out; revoking a computer already revoked changes nothing.
- **Reading routes.** Routes are not read-only, even those that only read: finding the computer records its last call, and a write on a read-only cursor makes Odoo run the request again.
- **Requests.** A request is checked against its operation in the OpenAPI document before the endpoint acts: no query parameter the operation does not take, a body only where it takes one, as `application/json`, matching its schema with no field the schema does not have. An invalid request is refused with `invalid_request`.
- **Errors.** Every refusal answers `{"error": {"code": "<code>", "message": "<message>"}}` with the HTTP status of its code. A computer acts on the code, never on the message, which is in the person's language. An endpoint refuses by raising a `LaboratoryFileError` with its code; `ir.http` answers every exception on the API's paths in this format, Odoo's own refusals too, and a raised refusal commits nothing. An endpoint that must keep what it did, such as counting a failed sign-in, returns its refusal instead.

| Code | Status |
| ---- | ------ |
| `invalid_request` | 400 |
| `invalid_credentials`, `invalid_key` | 401 |
| `permission_denied`, `device_revoked` | 403 |
| `not_found` | 404 |
| `method_not_allowed` | 405 |
| `folder_archived`, `folder_disabled`, `locked`, `not_locked` | 409 |
| `not_eligible`, `not_lockable`, `not_editable` | 422 |
| `too_many_attempts` | 429 |
| `internal_error` | 500 |
| `try_again`, `editing_unavailable` | 503 |

- `invalid_key` and `invalid_credentials` carry a `WWW-Authenticate: Bearer` header.
- `method_not_allowed` answers a method the route does not take, with an `Allow` header naming those it takes. A path the API does not have is `not_found`.
- Odoo's own refusals answer in the same format: a missing or invalid key, and a session of another person with a key, are `invalid_key`; a record the person may not read (`AccessError`) or that does not exist (`MissingError`) is `not_found`, so the answer does not tell that a record exists; any other user error is `invalid_request`. `permission_denied` is only raised by name, such as for a person without the laboratory files permission.
- `internal_error` answers an exception nobody expected, with a generic message and an `id`. The server logs the exception and its traceback under that id; the answer tells nothing else about it.
- `too_many_attempts` and `try_again` carry a `Retry-After` header in seconds. `try_again` answers a request still failing on concurrency after Odoo's last try, after 5 seconds.
- **Adding to the API.** A feature adds its routes with `laboratory_api_route()`, its operations to the OpenAPI document, and any code of its own to `ERROR_STATUSES` (`constants/laboratory_api.py`) and to the document's error codes. Its tests call its routes through `LaboratoryApiCase` (`tests/laboratory_api_case.py`), which checks every answer against the document, so they are its contract tests.
- **Health.** `GET /medilab/api/v1/health` answers once Odoo serves requests; `GET /medilab/api/v1/ready` also runs the checks of `ir.http._laboratory_files_ready_checks()`, the database's, and 503 when one fails. A feature that adds a part the API needs, such as the bucket, adds its check there. Readiness never includes the editing service, so it answers ready while the editing service is down; the editing service has its own health check. When Odoo cannot reach the database at all, it answers before any route of the API does.

### Computers

A signed-in computer is a `medilab.laboratory.device` of its person, one per installation of Medilab Sync: the installation id the application generates once is unique for the person. Its name is one name and its platform is Linux or Windows.

| Step        | What happens                                                                                                                                                                                                                                                                  | Refused with                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Signing in  | Odoo checks the login as it does for its external API: with the password, or, for a person with two-factor authentication, with one of their API keys in its place. The password is never kept. The computer is created, or found by its installation id, and gets a new key. | `invalid_request`, `invalid_credentials`, `permission_denied`, `device_revoked`, `too_many_attempts` |
| A call      | Odoo verifies the key; the computer is the one holding the key's row and not revoked. Its last call is written at most once a minute, so parallel calls do not fight over its row.                                                                                            | `invalid_key`                                                                   |
| Signing out | The key is removed; the computer can sign in again and gets a new key.                                                                                                                                                                                                        |                                                                                 |
| Revoking    | The key is removed and the computer is revoked for good. A person revokes their own computers, administrators any computer in the back office only. The person's folder memberships and other computers stay.                                                                                         |                                                                                 |

- The key is an Odoo API key of the person, in `res_users_apikeys`, with the scope `sol_laboratory.device`. Odoo keeps only its hash, and the scope makes it open the laboratory files API and nothing else, not Odoo's external API. It does not expire: it stays valid until the computer signs out or is revoked. The device keeps only the id of the key's row, and signing in again removes the old key first.
- A person with two-factor authentication cannot sign in with their password: Odoo refuses passwords outside its own sign-in screen for them. They sign in with an Odoo API key in its place, one with the scope `rpc`, which is the scope of the keys a person creates in their Odoo preferences. A key of any other scope is refused there, a computer's key too, so one computer's key never signs another in.
- Odoo verifies the key's hash before the call reaches the laboratory files API, and that hash is deliberately slow. So the computer of a call is found by the key's row with the person, the scope and the key's index, as Odoo finds it, with the same expiry; the hash is checked again only when two of the person's keys share an index.
- Removing a computer's key from anywhere signs the computer out, also from the person's Odoo preferences or as an administrator. Odoo makes no foreign key to its API keys, so removing one empties the key of its computer first, which records the sign-out in the audit trail. Odoo's cleanup of expired keys deletes rows with SQL and would pass over it, but computers' keys never expire.
- Revoking is final, also for a person's own computer: the revoked installation cannot sign in again. The computer gets back in as a new installation of Medilab Sync, which generates a new installation id and signs in as a new computer. Whether administrators can restore a revoked computer is an open question.
- Two first sign-ins of one installation at once make one computer: the second one's creation fails on the unique installation id, `_create_signed_in()` turns it into a `ConcurrencyError`, and Odoo runs the request again, which finds the computer.
- Signing in, signing out and revoking are recorded in the [audit trail](audit-trail.md) as the creation and edits of the computer: signing in creates it or changes its key, signing out empties its key, and revoking empties its key and sets when it was revoked. The key's row is named, never the key.

#### Limits on signing in

- Odoo's only brake on guessing passwords is its login cooldown, which counts failures per client address in each Odoo worker. Signing in is therefore also limited per client address in front of Odoo, as the webhooks are, and slowed per login in Odoo.
- **Per client address.** A Traefik rate limit on the sign-in route counts by `Cf-Connecting-IP`. That header is trusted because only Cloudflare reaches the origin: Traefik binds no host port, and network policies let only the `cloudflared` pods reach Traefik and only Traefik reach Odoo, so no other pod can send a forged header.
- **Per login.** After 5 failed attempts for a login within 15 minutes, every further attempt waits a delay that doubles from 1 second up to 60 seconds; an attempt before its delay has passed is refused with `too_many_attempts` and a `Retry-After` header, before the password is checked. The account is never locked: the person signs in with the right password once the delay has passed.
  - The delay is counted from the last failure: the sixth attempt waits 1 second after the fifth failure, the seventh 2 seconds after the sixth, up to 60 seconds.
  - An attempt refused for its delay is not counted, so retrying early does not lengthen the delay.
  - A login's failures are forgotten 15 minutes after its last one; the next failure counts from one again.
  - A login nobody has is counted and slowed the same, so the answer does not tell whether it exists.
  - A right password clears the count, also when signing in is then refused with `permission_denied` or `device_revoked`.
  - The counts are in `medilab.laboratory.sign.in.attempt`, one row per login, so every worker shares them. Two failures of one login at once update one row: the second fails with a serialization error and Odoo runs its request again, so each is counted once. Only full rights reach it, failed sign-ins are not in the audit trail, as Odoo's log records them, and Odoo's daily autovacuum removes the counts already forgotten.
- **Odoo's cooldown.** While Odoo's own login cooldown holds the client's address, signing in is refused with `too_many_attempts` and the seconds left of it, before the password is checked, never as `invalid_credentials`.

### Sample folders

A folder of a sample holds the files of one category of its work: raw data, working documents, results or reports.

- A sample has one folder of each category, held by a unique key on the sample and the category. A folder has a category if and only if it has a sample, held by a check on the folder. Upgrading clears the category of every folder of no sample before the check is added, and logs each folder it changed with the number of its files, as its files stop counting as that category: a former raw-data folder's files are locked and edited online.
- Once a folder holds files, its sample and its category never change, so its files keep meaning what they were saved as, such as a signed result of that sample. The folder's form shows them read only then.
- Everything of a sample's folder is seen only by people who see the sample, whoever they are, folder administrators included: the folder, its members, sync rules, files, versions, locks, editing sessions and changes, in lists, forms and links. Each of these models inherits `medilab.laboratory.sample.folder.mixin`, which adds to the model's access domain for every operation that the record's folder belongs to no sample or to a sample the user reads, with the sample's own access domain for the user. An access domain is evaluated with full rights, so it cannot test the sample itself; the sample's access domain, which Odoo builds for the user, can. A model a later feature adds under folders or files inherits the mixin too, naming the path to the sample in `_sample_field`.

#### Creating a sample's folders

**Create Folders** on the sample adds the raw-data and result folders it does not have yet. The head of a department that tests the sample creates them, holding the laboratory files permission and seeing the sample; anyone else is refused with `permission_denied`. Who creates a sample's folders, and when, is an open question: `_check_can_create_laboratory_folders()` on the sample alone decides it, so another answer changes only that method. Until it is answered, the head of department creating them is provisional, not decided.

- The new folders are owned by the person who creates them, upload-only and without sync rules, so every file is synced. The owner adds the members.
- They are named after the lab code only, which testers see: `<lab code> Raw Data`, with the root `<lab code>-raw`, and `<lab code> Results`, with the root `<lab code>-result`. When the owner already has a folder of that root, nothing is created and the person is told.
- Creating them again adds nothing. Two creations at once make one folder of each category: the second one's creation fails on the unique key, `_create_laboratory_folders()` turns it into a `ConcurrencyError`, and Odoo runs the request again, which finds the folders.
- The sample's form opens its folders the person sees.
- Whether the folders of a completed or cancelled sample refuse uploads and online editing is an open question. Until it is answered they take both like any other folder, which is provisional; the answer adds its rule to `_check_can_add_version()` and `_check_can_edit_online()` only.

### Signing versions

A version of a result file is approved by signing it through the [approval and signing chain](../business/approval-and-signing-chain.md) of laboratory file versions, `medilab.laboratory.file.version`: each version is a document of the chain, signed level after level by the roles its levels name, and the signature belongs to that version and its content. The chain is set up by administrators; without it, signing a version is refused.

| Step        | Who and what                                                                                                                                                                                                                                                                                                                       |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Signing     | A member of the folder who sees its sample, holds the `sign` permission of versions and the role of the next level signs the current version of a file in a result folder. The signature records the signer, their role and level, the version and its SHA-256.                                                                    |
| Rejecting   | The same person rejects the version instead, with a reason; a rejection without one is refused. The person who saved the version is told why, through the mandatory `laboratory_file_version.rejected` event, once for each round.                                                                                                 |
| Withdrawing | A signer who still reads the version's file, as a member of its folder who sees its sample, withdraws their own signature or rejection once every higher level has withdrawn theirs, as in every chain. Withdrawing the last one leaves the version unsigned, and the next signatures record the next round of `document_version`. |

- Only the current version of a file in a result folder is signed or rejected. A conflict version is never current, so it is never signed.
- A newer version of the file starts unsigned: the file shows the signing state of its current version, and the older version keeps its signatures.
- Signing never stops a save, the online editor or a lock: a signed version is already never changed. Its number, content, hash and origin are protected for good, as every version's are. The fields signing adds are not part of that list: the signing state changes as people sign, reject and withdraw, and only through them; the round, `document_version`, cannot change while a signature stands, as in every chain.
- Each signature of the chain records the hash of its document's content in `document_hash`, from `_approval_document_hash()`; for a version it is its SHA-256, and for document types without one it is empty.
- Signing and rejecting take the file's row without changing it, so a signature and a concurrent save of the same file wait for each other and the second one runs again: a signature that comes after a newer version is refused, and a save after a signature adds an unsigned version. The file's last save stays as it was.
- The level whose signer must belong to the department that did the work is refused for versions: a sample is tested by several departments, and the chain takes one department per document. Which one counts is an open question.
- When a version's process is completed, so that its signatures can no longer be withdrawn, is an open question; until it is answered, they can always be withdrawn.
- Signing, approving, rejecting and withdrawing are recorded in the [audit trail](audit-trail.md) on the version.
- In the back office, a version's form signs it, rejects it with a reason and withdraws a signature, each button shown only to the person who may use it now, and shows its signing state; its signatures are listed to people who read signatures. Lists of files and versions show the signing state of each, and filter versions that are signed, being signed or rejected.
- Whether a signed version is also digitally signed through Viettel Sign, and whether the person who saved a version may sign it, are open questions. Until they are answered, versions are not signed through Viettel Sign and the person who saved a version may sign it; both are provisional, not decided.

## Related documents

- [Laboratory files architecture](../decisions/laboratory-files-architecture.md)
- [Laboratory overview](../functional/laboratory_module/overview.md#laboratory-files)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Permissions](permissions.md)
- [Document locking](document-locking.md)
- [Audit trail](audit-trail.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
