# Laboratory files

Stories: US-T23, US-T24, US-T25, US-T26, US-T27, US-T28, US-AD29, US-AD30, US-AD31, US-HD15, US-HD16

## Goal

People reach the [laboratory files](../functional/laboratory_module/overview.md#laboratory-files) only through the folders they are members of, and only with the laboratory files permission. One check decides what a person may do with a folder, so the laboratory files API and the features built on folders refuse the same things the same way. Each computer signs in once with the person's login and gets its own key, which stops at once when the computer is revoked. Every saved state of a file is a version that never changes, numbered in order even when two saves of the file come at once. A person editing a file can lock it, so nobody else saves it meanwhile. People edit an Office file together in the browser in one session per file, and received saves preserve their immutable versions; delivery failures require the recovery procedure below. The API is Odoo's own HTTP routes under `/medilab/api/v1`; file content is stored once by its SHA-256 in the private bucket and counts only once the server has verified it; online editing goes through a self-hosted ONLYOFFICE Document Server that nothing else depends on. The [architecture decision](../decisions/laboratory-files-architecture.md) gives the requirements, by ID.

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

The Documents menu of the Laboratory app lists Folders, Files, File Versions, File Locks, Editing Sessions, Folder Members, Sync Rules and Computers. Files, versions, locks and editing sessions are only read there; a folder's form lists its files, and a file's form its versions and editing sessions. A version's form downloads it, for a member of its folder, through the same presigned address as the API, opened in a new tab. People with the laboratory files permission see their folders, with their members and rules, and their own computers there. They create folders of their own, as Medilab Sync does, and change nothing else: owners manage their folders from Medilab Sync. A sample's folders are created from the sample ([Creating a sample's folders](#creating-a-samples-folders)); otherwise only administrators create a folder for someone else or set a folder's sample. Administrators see and change them all: they turn folders off and on, archive them, change their owner, add and remove members, change rules and revoke computers. Members are added on their folder; the Folder Members list removes them, from an archived folder too.

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
- A version's number, file, parent and restored versions, source, content, size, SHA-256, person and computer never change, and versions, files and changes are never deleted, administrators included. When a version was stored is Odoo's creation time of its row. Fields a later feature adds to versions, such as their signing state, are not part of that list.
- Sizes are 64-bit integers (`fields/big_integer.py`), as files reach 5 GiB and Odoo's integers stop at 2 GiB. A version's SHA-256 is 64 lowercase hexadecimal digits.
- A file is raw data when its folder holds a sample's raw data, `_is_raw_data()`; a folder without a category holds none. It is an Office document when its extension is `docx`, `xlsx` or `pptx`, in any letter case, `_is_office_document()`. What applies to files of folders without a category is decided by the features built on files.

#### Storing a version

`file._add_version(source, user, content, device, base_version, restored_from)` is the one way a version is stored. Uploads, restores and the online editor's saves all call it, after checking access with `file._check_file_access("write")`; `_get_or_create(folder, path)` finds or makes the file of a new path first.

A version holds content the server verified ([Stored content](#stored-content)) and records its SHA-256 and size, never values a computer sent: a save passes the content, and a restore takes the content of the version it restores. Content that is pending, failed or a duplicate is refused, and so is a version whose SHA-256 or size is not its content's.

1. `_check_can_add_version(user, device)` refuses a version that breaks a rule every save obeys, whoever stores it and with whatever rights: the folder is archived (`folder_archived`) or turned off (`folder_disabled`). **It is the extension point of the features built on files**, which add their own rules there, such as a lock someone else holds, so a caller that skips the access check still cannot pass them.
2. The file's row is updated, which locks it (see below).
3. Content with the current version's SHA-256 adds nothing, whatever version the save was made from, and the current version is returned. A restore is the exception: it always adds a version with the content of the version it restores.
4. The version takes the number after the file's last one, and the version that is current as its parent.
5. A save made from a base version that is no longer current is kept as a `conflict` version and the current version stays. Otherwise the version becomes current through `_make_current()`, which adds the change row and refuses to move the current version back to an older one. Writing the current version any other way is refused.

#### Two saves at once

Two saves of the same file at once, such as an upload and a save of the online editor, never take the same number or skip one:

- Every save updates the file's row before it numbers its version, a conflict too. The second save waits for the first; once the first commits, the second fails with a serialization error, because the row changed after its snapshot, and Odoo's request retrying runs its whole request again, which now sees the first save's version. A lock alone would not do: the second save would number its version from a snapshot without the first one, and the duplicate number would fail without a retry.
- The number is the file's highest one plus one, read under that lock, not a database sequence, so a save that is rolled back leaves no gap.
- **Saves of different files of one folder** each add a change, which computers read by id after the last one they saw. A change must never commit after one of a higher id, which a computer would already have passed, so each save takes its folder's feed lock, `pg_advisory_xact_lock(FEED_LOCK_SCOPE, folder)`, right before it inserts its change, and holds it until it commits: the next save of the folder inserts its change once this one has committed. The file's row is always locked first, and `_lock_feed()` refuses otherwise, so two saves never wait on each other's locks in opposite orders. A save only waits, without running again, so the lock costs no retry.
- Two first saves of one new path make one file: the second one's creation fails on the unique path key, which `_get_or_create()` turns into a `ConcurrencyError`, and Odoo runs the request again.
- Odoo 20 runs a request again (`odoo/http/retrying.py`) after a serialization failure, a deadlock, a lock it could not take or a `ConcurrencyError`, up to 5 tries in all, waiting a random time of up to 2, 4, 8 and 16 seconds between them; after the last try the request fails. Any other integrity error, a unique violation too, is rolled back and answered as a validation error without running again, which is why the unique violations above become a `ConcurrencyError`. Running again rolls back the transaction with its pre-commit and post-commit hooks and the ORM caches, reloads the session, rewinds uploaded files and authenticates again. It undoes no call to the bucket or the editing service.
- **Everything a caller does before `_add_version()` in the same request must be safe to run twice**, as a concurrent save runs the whole request again: the storage calls of uploads, and fetching the edited document from the online editor. A rollback undoes none of them, so they only write new objects under random keys, and content counts only once its row is verified and committed ([Stored content](#stored-content)).
- Odoo's request retrying does not run saves outside a web request, but a [job item](scheduled-jobs.md) that fails is run again later, so the work of a job item is safe to run twice too.

`laboratory_files_concurrency_case.py` runs such races in two real database transactions, the second through Odoo's request retrying, and gives the second one's record or the refusal it got; `test_laboratory_file_version_concurrency.py` races saves with it. It calls Odoo's own `retrying()` outside an HTTP request, so the API's routes are raced through real HTTP requests too, which authenticate again when they run again, and in the deployed configuration.

#### Access

`file._check_file_access("read" | "write")` checks reading and writing a file through its folder's `_check_folder_access()`: membership, the sample of a sample folder, and whether the folder is archived or turned off. Versions are checked through their file.

### Stored content

File content is stored in the laboratory files bucket, a private S3-compatible bucket that also holds Odoo's filestore when `BUCKET_FILESTORE=1` ([Filestore](#filestore)). Odoo's credentials reach that bucket only; computers never get credentials, only presigned addresses, and file bytes never pass through the API's requests and answers. Content is addressed by its SHA-256 in the database, never by its object key.

- **Objects.** Every upload, and every save of the online editor, is written to an object of its own under a random key the server makes, 32 hexadecimal digits that tell nothing about its content; a key from a client is never accepted. Every upload is a multipart upload the server creates, even of one part, and its presigned addresses are for that upload's parts only, so no address can write the object once its upload is completed.
- **Content.** `medilab.laboratory.content` has a row per object: its key, unique, and its verification state, `pending`, `verified`, `duplicate` or `failed`, with the size and SHA-256 the server computed once it is verified. The SHA-256 is unique among verified content. A version refers to verified content, and its SHA-256 and size are the content's. Only the server records a content's size, SHA-256 and state, `_settle(sha256, size)` from its own reading of the bytes and `_fail()`; a content's key and settled values never change, and content is never deleted. Only full rights reach content, so nobody reads its object key without a check of the version that holds it.
- **Uploading.** An upload (`medilab.laboratory.upload`) is a computer putting one file's content into the bucket. Preparing it records the path, the size and SHA-256 the computer claims and its base version, once the person may write the file there, so a lock someone else holds refuses it before any byte is sent. When the file's current version already has the claimed SHA-256, nothing is uploaded: the upload is `unchanged` and the current version stays, as for any save of the content the file already has. Otherwise preparing adds the `pending` content row of a new object and creates its multipart upload, and the computer asks for the presigned addresses of its parts, of 16 MiB but the last, which last the file address lifetime of the settings or until the upload expires if sooner. The bytes are uploaded even when the same content is already stored, so knowing a SHA-256 gives no one its content. Empty content, which a multipart upload cannot hold, is written by the server as it prepares the upload. Preparing takes an `Idempotency-Key`, and a repeated request answers with the same upload.
- **Finalizing.** Finalizing checks that the person may still write the file and that every part is uploaded with its size, then makes the upload `verifying` and queues its verification; a part missing is refused with `upload_incomplete`, and the upload stays `prepared`. An upload past its expiry, or not `prepared` or `refused`, takes no part addresses or finalizing (`upload_closed`), and one already past finalizing answers with its state. The computer reads the upload until it ends.
- **Verifying.** The job `laboratory_contents.verify` completes the multipart upload, then streams the object from the bucket and computes its size and SHA-256; a multipart ETag or a composite checksum is never taken for the SHA-256 of the file. A mismatch with the claim makes the content `failed` and the upload `failed`, with no version, and its code says which: `size_mismatch`, `sha256_mismatch`, or `missing_object` when no object was completed. Verification takes one item per batch and one per pass of its cron, so a file of 5 GiB is one batch within the cron worker's time limits, and it reads the object in chunks of 8 MiB, so its memory stays under the worker's limit. A verification stopped midway, such as by a killed worker, leaves the content `pending`; its item is claimed again after the job's claim timeout and starts over from the first byte. When they match and verified content with that SHA-256 exists, the new content is `duplicate` and the version refers to the existing content; otherwise the new content is `verified`, and canonical from then on: nothing writes its object again.
- **Storing.** The job `laboratory_uploads.store` then stores the version with `_add_version()`, as the person who uploaded and from their computer, once the person may still write the file, in their own environment, and the computer is not revoked. The upload is `completed`, `conflict`, or `unchanged` when the file got the content meanwhile. Whatever refuses the version meanwhile, a lock someone else took, the folder turned off or archived, the person removed from the folder or the computer revoked, makes the upload `refused` with the code of the refusal; its verified content is kept, and the computer finalizes it again once what refused it is gone, until it expires. What state such an upload should get is an open question; `refused` is provisional.
- **Deleting objects.** The object of `duplicate` or `failed` content is deleted once the transaction that set its state commits, so the same content is stored once. A deletion that fails is left to reconciliation.
- **Running twice.** Two finalizations of one upload, Odoo's retrying, a job item run again and a computer repeating a call store one version: the upload's row is updated before its status is read, as a file's row is for a new version, and an upload already past finalizing answers with its result. Completing a multipart upload already completed, such as by a verification run again, finds its object. Two uploads of the same content at once write two objects; the second to be verified fails on the unique SHA-256, and its job item, run again, makes it `duplicate`, so one object stays.
- **What counts.** Content counts only once its row is `verified` and committed. An object written by a transaction that then failed, such as an editor's save Odoo runs again, has no row; reconciliation finds it.
- **Restoring.** `file._restore(version, device, key)` adds a version of the content of the version it restores, after `_check_file_access("write")`; no byte is copied. A restore always adds a version. A computer may send an `Idempotency-Key` with it, kept on the version and unique for the computer, and a request repeated with it answers with the version it added.
- **Downloading.** A download address is presigned for the object of one version's content, for reading only, after `_check_file_access("read")`, by `file._download_address(version)`, which records the download in the [audit trail](audit-trail.md) on the file. It is the only way to a version's content: no route takes a SHA-256. It lasts the system parameter `sol_laboratory.laboratory_file_url_minutes`, 15 minutes by default, in the Laboratory Files block of [Settings](settings.md).
- **Unfinished uploads.** An upload lasts the system parameter `sol_laboratory.laboratory_upload_hours`, 24 hours by default, at least 1 hour and less than the 7 days after which the bucket aborts it, in the Laboratory Files block of [Settings](settings.md). A `prepared` or `refused` upload past its expiry is marked `expired` by the job `laboratory_uploads.expire`: a pending content's multipart upload is aborted, which removes its parts, and the content becomes `failed`; verified content is never touched. The bucket's lifecycle rules also abort incomplete multipart uploads after 7 days, in case the job did not.
- **Reconciliation.** The job `laboratory_contents.reconcile` compares the bucket with the rows every day. Once they are a day old, it deletes the objects with no content row and the objects of `duplicate` and `failed` content still in the bucket, and aborts the multipart uploads of no open upload: an upload that has not ended, a `refused` one a computer may finalize again among them. It records as errors of the system in the [audit trail](audit-trail.md) the verified content whose object is missing or has another size, and the `pending` content of no open upload a day after it was made. It never deletes the object of verified content.
  - It walks the bucket's listing and the rows side by side, in the order of their keys, and queues one item per finding, keyed by what it is about. A finding that stays is recorded once, not every day, until the cleanup job removes its item. Each item checks its finding again before it acts, as the content or the upload may have changed since the bucket was listed.
  - **Whose bucket.** The object `.medilab-database` holds the `database.uuid` of the database the bucket belongs to. The first run writes it; Garage takes no conditional write, so it is a read then a write, which only this job makes. A run that finds another database's uuid deletes and aborts nothing, and records that once. This keeps a database that is not the bucket's, such as one restored from production into staging that reaches staging's bucket, or two local databases sharing one server, from deleting the other's objects as objects with no content row.
  - **What the marker cannot catch.** A database restored from production keeps production's `database.uuid`. Restored into staging and given production's bucket keys, it passes the check, and would delete every object production uploaded after the backup as an object with no content row. So staging never holds production's bucket keys, and a database restored from production into staging gets a new `database.uuid` before it runs.
- **Never removed.** Nothing deletes the object of verified content. When the content of laboratory files is removed after their retention is an open question; until it is answered, verified content is kept.
- **Reaching the bucket.** Odoo reads the bucket's settings from the environment: its key, `BUCKET_LABORATORY_ACCESS_KEY` and `BUCKET_LABORATORY_SECRET_KEY`, the bucket's name `BUCKET_LABORATORY_NAME`, the address Odoo calls it at `BUCKET_LABORATORY_ADDRESS`, the public address presigned addresses are made for `BUCKET_LABORATORY_PUBLIC_ADDRESS`, and the region its keys sign for `BUCKET_LABORATORY_REGION`. `services/laboratory_bucket.py` makes every call, each safe to make twice: completing an upload already completed answers with its object's size, and aborting an upload or deleting an object already gone changes nothing. A call that cannot reach the bucket raises `BucketUnavailable`, so the same call can be made again later. Odoo writes the documents it stores itself, such as an editor's save, in parts of 16 MiB, each with its SHA-256, which the bucket checks, and empty content in one call, since a multipart upload has at least one part of at least one byte.
- **Local development and CI.** Docker Compose runs a Garage server, pinned by digest, as the laboratory files bucket. Its one-shot service `garage-setup` sets the bucket up as production's: the lifecycle rule that aborts incomplete multipart uploads after 7 days, Odoo's key reaching that bucket only and creating none, and a second bucket the key may not reach, which the tests check. Its keys are local values in the Compose file.
- **Encryption and backups.** The bucket is encrypted at rest and reached over HTTPS only. Object keys say nothing about content, so the database is the index of the bucket: it is backed up outside the provider's site with the bucket, and restoring both is tested: the restored bucket holds the object of every verified content, with its size and SHA-256.

### Filestore

When `BUCKET_FILESTORE=1` and the laboratory bucket settings are present, `ir.attachment` keeps Odoo's filestore in the bucket under `filestore/<database>/<store_fname>`, using the local filestore directory as a cache:

- Writing an attachment (`_file_write`) writes the file to the local filestore first, then uploads it to `filestore/<database>/<store_fname>` when the object is not in the bucket yet.
- Reading (`_file_read`) or streaming (`_to_http_stream`) an attachment checks the local filestore first; when the file is missing locally, it downloads the object into a temporary file in the target folder, marks it read-only (`0444`), and replaces the target path before Odoo reads it.
- At the end of a module install or update (`_register_hook` when `init` or `update` is set), every attachment file already in the local filestore—including files Odoo wrote before `sol_laboratory` loaded—is uploaded to the bucket if missing.
- Odoo's daily autovacuum (`_gc_filestore_bucket`) lists `filestore/<database>/` and deletes objects older than 24 hours that no `ir.attachment` row references, leaving newer objects that an in-flight transaction may still be creating.

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

- **API.** A computer locks, renews and unlocks a file through `/folders/{folder_id}/files/{file_id}/lock`, after `read` on the folder and once the file is found in it: a file of another folder, or of no id, is `not_found`. The lock records the computer of the key, never one the request names. Locking a file one holds again renews the lock, renewing a lock that expired is `not_locked`, and unlocking with no lock answers 204, so each has the effect of one run when repeated. An administrator's release of someone else's lock is done in the back office only. A file's answer shows the lock in force on it with its holder and when it expires, never the computer of another person's lock.
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

A person opens a file online at `GET /medilab/laboratory-files/<file_id>/edit`, signed in with Odoo's browser session. Medilab Sync's browser handoff is delivered separately; the page takes no device key. Odoo sends an unauthenticated person to its login page with a server-generated relative return path. Caller-supplied redirect targets and query values are discarded from that return path. Native logout, session rotation and identity confirmation remain Odoo's responsibility.

The page is native HTML, outside both the device API and the callback's OpenAPI document. It returns 200 for an authorized open/join, generic 404 for missing/nonmember/sample-hidden files, 403 for missing global laboratory-files permission, 409 for eligibility or folder-state refusals, and 503 for unavailable editing or invalid service configuration. The existing global permission helper runs before existence checks: a person without that permission gets the same generic 403 for every id, so statuses do not disclose existence. It calls existing file model checks before validating origins, then `_open_for()` and `_editor_config()`; there is no second authorization policy. A savepoint rolls back opening/joining and its audit effects if configuration generation fails. Normal page responses commit through Odoo; concurrency errors reach its normal request retry loop.

`ONLYOFFICE_PUBLIC_URL` is the explicit browser-facing origin, and `ONLYOFFICE_CALLBACK_ORIGIN` is the explicit canonical callback ingress origin. Both are required; no request Host, forwarded host, query parameter or automatically updated `web.base.url` supplies either. Origins contain only scheme, host and optional port, with an optional trailing slash. Userinfo, path prefixes, query/fragment, encoded/control characters, backslashes, invalid ports and ambiguous numeric hosts are refused. Browser-facing Document Server and bucket origins require HTTPS, except loopback HTTP for local development. Explicit internal Document Server, bucket and callback ingress origins may use private HTTP; #203 must verify their network isolation or trusted TLS. A missing/invalid origin fails closed before a health-check request or session creation.

QWeb escapes the configuration as a JSON data attribute and the title as text. External JavaScript parses it and passes it to ONLYOFFICE; names, translated messages and upstream error descriptions never become executable markup. The configuration contains the authorized browser's editor JWT and read-only presigned base URL; neither belongs in URLs, redirects or telemetry. Page responses and login/error redirects use private/no-store cache headers, no-referrer, nosniff and a restrictive CSP. Scripts and frames use self/the explicit Document Server origin, connections additionally allow the explicit bucket origin, and inline scripts/eval are not allowed. The standalone page uses no back-office action. Its scoped Odoo handler filters also redact SDK signing diagnostics and editor URL references, including background diagnostics; #203 still owns bootstrap readiness and additional ingress/Document Server/APM sinks. A real pinned-editor CSP compatibility run is required before release; no broad CSP exception is assumed.

Loading, connecting, document-ready, timeout, error and stale-configuration states are accessible in English and Vietnamese. An editor-ready event confirms launch only. A document-state event can confirm that changes reached the editing service, never that MediLab committed a version; the page tells the person to check version history. Retry/reopen is an explicit navigation through authorization again. Timeout or refresh/outdated-version events do not replace a live editor, create a new key or run an automatic recovery. In particular, `onRequestRefreshFile` is a stale-key/reconnect event rather than a generic JWT renewal protocol ([upstream events](https://api.onlyoffice.com/docs/docs-api/usage-api/config/events)). Browser events are checked against pinned `web-apps` tag `v9.4.0.1`; real service behavior remains an integration gate.

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
   - This is the one place a file's bytes pass through Odoo, from server to server and within the limits above: fetching the save later in a job could lose it once the editing service has dropped the document.
   - `services/saved_documents.py` streams the document in chunks of 1 MiB; `_store_saved_document()` writes them to a new pending content's object, settles it from the size and SHA-256 computed on the way, and returns the verified content, which is the content already stored when it is a duplicate.
2. The session's row is updated, which locks it as a file's row is locked for a new version, and its status is read again. A session already ended by a save, `committed`, `conflict`, `closed` or `error`, stores nothing: this is the editing service repeating a call it got no answer to.
3. The version goes to the last editor the editing service reports for the save, the last of its `users`; the audit entry names them and everyone its `history` says changed the document. A user is named by the id of the editor configuration, an Odoo user's id. `_check_file_access("write")` is checked for that person; when it refuses, `_check_can_add_version()` refuses the version, or the id is of no active user, the session ends in `error`, and its audit entry records why and the key of the stored content, so the content can be recovered.
4. `_add_version()` stores it as edited online, from the session's base version and from no computer. The session is `committed` with the new version, `conflict` with the conflict version, or `closed` when the content is the file's current content.

A save arriving for an expired session is stored the same way, and the conflict rule handles a file that changed meanwhile. A temporary failure, such as the bucket being unreachable or an interrupted fetch, keeps the session `saving`, or `expired` when it had expired, and returns HTTP 503 with `{"error": 1}` normally so Odoo commits the state needed by the next attempt. An unavailable document, including HTTP 404/410, remains a temporary failure in the model; operators must establish whether its bytes are permanently lost. Delivery retries are finite and do not guarantee another callback or an eventual error-status callback.

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

- The compatibility target is ONLYOFFICE Document Server Community Edition `9.4.0.1`, image index digest `sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212`. Release requires actual callbacks from that image and staging evidence under #203/#206; local callback fixtures do not establish compatibility. `latest` is never deployed.
- The editor configuration and the editing service's calls are signed with the JWT secret `ONLYOFFICE_JWT_SECRET`, which comes from Doppler through the environment, never from the database or the repository. A secret shorter than 32 bytes, the length HS256 needs, counts as no secret: online editing is then unavailable.
- Odoo reaches the editing service at `ONLYOFFICE_INTERNAL_URL` and browsers at `ONLYOFFICE_PUBLIC_URL`, both from the environment.
- **The editor configuration.** `_editor_config(user, callback_url)` gives the session's configuration with its token, signed for as long as the presigned address of the base version lasts: the file address lifetime of the settings, `sol_laboratory.laboratory_file_url_minutes`. It names the document key, the file's name and extension, the editor of its extension, the base version's address, the callback address, the user by their Odoo id and name, editing, and force save off.
- **The callback route.** `POST /medilab/laboratory-files/callback/<callback_token>` is an Odoo `type="http"` route outside `/medilab/api/v1`, with `auth="none"`, `csrf=False`, `save_session=False` and `readonly=False`. Its capability and verified JWT authenticate it; computer keys and browser sessions do not. It returns native integer `error` values, never JSON-RPC or the device API error envelope. Its separate OpenAPI 3.1 contract is `sol_laboratory/api/onlyoffice-callback.openapi.yaml`, linted by `task test:openapi`. OpenAPI cannot express the path capability plus conditional header/body JWT; the contract names these checks explicitly and runtime HTTP tests enforce them. The HTML editor page belongs to #230, not either JSON contract.
- **The token header.** #203 configures `JWT_ENABLED=true`, `JWT_HEADER=Medilab-Editor-Token`, `JWT_IN_BODY=false`, and `JWT_SECRET` equal to Odoo's `ONLYOFFICE_JWT_SECRET`, at least 32 bytes. Verify the effective outbox configuration after container startup: header `Medilab-Editor-Token`, prefix `Bearer `, algorithm HS256 and expiry `5m`. The pinned image defaults to `Authorization`, which must be changed. Its callbacks may include both a header token (`payload` contains callback fields) and a body `token` (callback fields are top-level claims), even with `JWT_IN_BODY=false`; every token present must validate and match. Header-only, signed-body-only and token-only bodies are supported by the existing verifier. Device API authentication stays separate.
- **Checking a callback.** `_from_callback()` checks every callback before anything is stored, and refuses with `EditingCallbackRefused`:
  - every token that comes, in the header or the body, is a JWT signed with that secret and the algorithm HS256 only, and carries an expiry that has not passed, with a minute of clock difference allowed;
  - the header token's `payload`, and the body token's claims after removing `token`, `iat`, `exp`, `nbf` and `operation`, agree with the body fields and with every other supplied token;
  - the `operation` of a token, when it names one, is `callback`;
  - the session is found by its callback token, and the document key is that session's, compared in constant time; a malformed key that cannot be encoded as UTF-8 is refused.

  A callback that fails a check stores nothing, changes nothing and is answered with an error.
- The network lets the browser reach the editing service's public address, the editing service reach Odoo's callback route and the bucket, and Odoo reach the editing service's internal address. The editing service reaches no other private address.
  - Document Server refuses private addresses unless `ALLOW_PRIVATE_IP_ADDRESS` is on, which it needs to reach Odoo's callback. That switch turns off its own refusal of internal addresses, and people editing a document can make it fetch an address, such as by inserting an image from a link.
  - So the network policy, not Document Server, keeps it from internal addresses: its egress reaches only Odoo's callback port and the bucket's endpoint, nothing else in the cluster and never the provider's metadata address.
- **Health.** The editing service has a health and readiness check of its own, `GET /healthcheck` on its internal address, which answers `true` when it edits documents. The API's readiness never includes it. Opening a file asks it first, waiting at most 3 seconds and following no redirect, and refuses with `editing_unavailable` when it does not answer `true` or the secret is missing. Nothing else depends on the service: syncing, downloading, history and restoring never read sessions or call it, and an open session does not stop uploads of its file; its save becomes a conflict.

#### Callback transactions and recovery

| Result | HTTP/body | Persisted outcome |
| ------ | --------- | ----------------- |
| Handled, duplicate or unchanged | 200 / `{"error": 0}` | Intended model effects commit; a recorded terminal `error` is an acknowledgement, not a claim that a version was saved. |
| Temporary source/bucket failure | 503 / `{"error": 1}` | Normal response commits `saving` or preserves `expired`, including failed staging bookkeeping. |
| Malformed fields, unsupported status or refused saved URL | 400 / `{"error": 1}` | The callback savepoint rolls back any partial effects. |
| Invalid/missing/expired/mismatched JWT on initial delivery, capability or document key | 403 / `{"error": 1}` | No mutation or document fetch. |
| JWT expires on an internal retry of a previously validated final save | 503 / `{"error": 1}` | Rejects the expired credentials without fetching or writing; requests a fresh signed Document Server delivery. |
| Unknown callback path / wrong method | 404 / 405 with `Allow: POST`, `{"error": 1}` | No model mutation. |
| Exhausted Odoo concurrency retries or commit-time concurrency failure | 503 / `{"error": 1}` | Failed work rolls back; the previous committed session state remains. |
| Unexpected error, including permanent storage credential failures | 500 / `{"error": 1}` | The request rolls back; a sanitized incident event requires operator investigation. |

The adapter delegates identity checking to `_from_callback()` and all status/save business rules to `_receive_callback()`. Expected refusals escape a savepoint before being converted to a normal response. Other exceptions reach Odoo's outer request retry/rollback handling. A normal HTTP response is committed regardless of its status; there are no manual controller commits or additional retry loops. Odoo retries execution/flush serialization conflicts up to five attempts and checks authentication again each time. In the pinned Odoo source, commit happens outside that retry loop: a commit-time conflict rolls back and returns 503, and is logged as `concurrency_failure`, without claiming five attempts occurred. The final error hook emits the native failure body after rollback. Odoo adds OPTIONS automatically; the callback explicitly refuses it with the same 405/Allow contract as other unsupported methods.

A verified callback gets a scoped, in-process audit marker and service execution user. The marker cannot be supplied through JSON context. Audit entries record `source=api`, no browser/device actor, and keep the editors in their existing notes; the version retains the actual editor as `user_id`. The service user does not bypass `_store_save()`'s existing check with that editor's permissions.

Each attempt writes a fresh bucket object. Database rollback cannot delete it; objects without committed verified content never count as versions. Existing guarded reconciliation removes aged abandoned/failed/duplicate objects once a day old and preserves verified content. Failed/duplicate content also schedules immediate deletion of its staging object after a successful commit; even an uncertain storage completion can leave a failed object eligible for that cleanup. This cleanup is **not** a seven-day recovery archive and is unchanged. An orphan can be the sole surviving complete copy after a rollback and Document Server loss, and reconciliation will still delete it once old enough. Logs do not preserve its bytes. #203 must prove an independent retained copy or provider recovery capability; timely operator copying is an operational mitigation, not a continuous seven-day retention guarantee.

Pinned Document Server `9.4.0.1` retries eligible final saves on transport errors and configured HTTP 429/500–599 responses, by default three retries after the initial attempt, approximately 1, 2 and 4 seconds apart. HTTP 200 with `error=1` and HTTP 403 do not schedule these retries. Its queued redelivery reconstructs the callback and calls `sendServerRequest()` / `fillJwtForRequest()` to sign fresh header and body JWTs. Encryption/shutdown paths and restart/cache loss need separate real-service evidence. Forgotten-file facilities may help an operator but do not establish retention or guarantee that bytes still exist.

Each Odoo attempt revalidates the original delivery JWT. An authentic save can pass its first check, spend more than five minutes fetching, then roll back; repeating that transaction can encounter an expired JWT. This attempt performs no fetch or model mutation. Only when this same HTTP request previously passed JWT, capability, document-key and payload checks for a final save does an expiry failure return 503 (`delivery_expired`) to request a fresh signed delivery. Initial expired JWTs, bad signatures and mismatched payloads remain 403. The request-local incident metadata is never an authorization cache, and a separate request repeating the expired token is still rejected. This avoids the otherwise permanent 403 stop in Document Server's bounded retry path without extending token lifetime or accepting expired credentials. Successful recovery still depends on remaining delivery attempts and available bytes.

The pinned outbox can trim a large header payload around its 7168-character limit after generating the body JWT; if the tokens disagree, Odoo refuses them. #203 must resolve that compatibility gate without relaxing either signature/payload check or silently dropping audit provenance.

##### Callback timing options and deployment gate

The initial outbox JWT remains five minutes with 60 seconds of clock allowance. Fetching is bounded per fetch at 15 minutes, with 60-second connect/read waits; bucket I/O and processing add time. The deployment plan's 21-minute caller budget is **per HTTP delivery**, not a total across Odoo attempts or Document Server redeliveries. Odoo's planned worker wall limit is 20 minutes. A retry starting just before JWT expiry/clock allowance can spend another 15 minutes fetching, so these independent limits do not prove completion within either outer budget. Document Server's four possible deliveries can consume approximately 84 minutes plus backoff/queue time at a 21-minute caller timeout.

| Option | Trade-off and required approval | Required evidence |
| ------ | ------------------------------- | ----------------- |
| Keep five-minute JWTs and use the narrow 503 fresh-delivery contract | Keeps strict authentication and bounded existing delivery retries. No replay job or token-lifetime change. It does not guarantee time or bytes remain. | Actual pinned callbacks after slow fetch plus serialization/commit failure, fresh JWTs on redelivery, finite exhaustion and one committed version. |
| Add a total Odoo delivery deadline and/or lower the per-fetch limit | Requires owner-approved timing/size policy and a separate implementation: the five-GiB throughput requirement must still hold. Return a retryable failure before worker/caller termination; do not swallow conflicts or add manual commits. | Slow streaming and bucket faults near each bound, actual worker/ingress limits, cleanup and persisted outcomes after termination. |
| Change worker/caller and/or outbox-token lifetimes together | Requires owner approval. A longer JWT expands its replay window, and a longer JWT alone can permit more repeated fetches without solving the caller deadline. No value changes are implied by this specification. | Joint worst-case timing/resource measurements, expiry/mismatch rejection, clock skew, delivery retry count, staging concurrency and retained bytes. |

#203 must record a measured, approved timing envelope and verify configured connection/inactivity and whole-cycle limits, ingress limits and worker limits. The local HTTP fixture tests do not prove this envelope on Document Server.

##### Recovery evidence and retention options

After a successful bucket write and before content settlement or later database locks, the callback emits privileged `staged_bytes` evidence: session id, random object key, computed SHA-256, size and request correlation. It explicitly describes staged bytes, not a committed version. These records survive transaction rollback and allow operators to associate orphaned objects with an incident. A committed terminal permission error retains verified content and its existing audit note; expiry preserves session/file/base/key records and audit history. Source failures with no received bytes can supply only incident/session evidence.

Committed outcomes are logged after commit with status, outcome, session id, elapsed time and correlation id; an error after rollback records its exception class, never its message. Terminal errors, temporary failures, `delivery_expired` and `concurrency_failure` require actionable incident monitoring independent of whether the session still says `open`, `saving` or `expired`. Authentication probes need rate-aware security monitoring rather than one incident per probe.

Callback access/error redaction covers the configured Odoo output handlers, including descendant urllib3/botocore records and expanded debug headers; the callback's fixed-format evidence logger retains only trusted recovery fields. Watchdog and stack-dump records can contain thread callback URLs outside any request context, so redaction also checks formatted messages, encoded references and exception chains regardless of logger name. A diagnostic payload containing a callback reference is redacted in full; its logger and severity remain available, and unrelated business/cleanup diagnostics are preserved. #203 must gate traffic until the module/filter is loaded and protect any additional exporter/sink, ingress and Document Server logging. The pinned Document Server itself logs callback URLs and payloads on errors; Odoo's filter cannot sanitize a different process. Recovery evidence and logs must be access-restricted, retained and available to the responsible operators.

| Retention option | Trade-off and required proof |
| ---------------- | ---------------------------- |
| Provider soft deletion/version history or an independent retained backup/archive | Verify the actual provider supports it, protects deleted staging bytes for at least seven days, and can restore the last copy after Odoo cleanup and Document Server restart/loss. No capability is assumed for Garage or production storage. |
| Manual secured copy during incident triage | Retain a checked copy in an authorized store before cleanup and record SHA-256, provenance and access controls. A missed response target can still lose the sole copy; this alone is not a guaranteed seven-day window. |
| Extend staging cleanup retention | Requires owner approval and #170/#203 review of immediate failed/duplicate deletion, orphan age, costs and concurrency. No cleanup interval is changed here. |

Recovery is manual operator work only: no replay or automatic recovery job. The initial targets are a verified minimum seven-day retention window for recoverable bytes; alerts to responsible Infra/DevOps operators and the MediLab maintainer within five minutes of an actionable failure; acknowledgement within 30 minutes; escalation after 30 minutes without acknowledgement or two hours without meaningful progress; triage begun within two hours; and a verified outcome or explicit unrecovered classification within 24 hours. #203 must prove storage/lifecycle/restart capabilities and alert routing against these targets; unsupported retention must be reported, never claimed.

The tested deployment runbook under #203 must correlate the session's document key and audit evidence with secured Document Server/forgotten files, retained verified content or still-present abandoned objects; preserve a checked copy, SHA-256, original file/base version, editor identities, permissions, timestamps and incident evidence; and import only through an authorized existing version flow that preserves immutable history/conflicts and records the operator. Do not forge callbacks, bypass permissions or relabel an operator's action as the original editor's. Demonstrate outage, restart, expired temporary URL and missing-byte cases. If no verified bytes can be obtained, classify the document as unrecovered and preserve the evidence; do not claim a successful save. #171 supplies the boundary/evidence, #203 owns retention/alerts/runbook and #206 staging sign-off; #230 owns browser/Sync feedback.

#### Expiry

The job `laboratory_editing_sessions.expire` runs every 30 minutes and expires the open and saving sessions with no activity in the idle period. Expiry only stops people from joining: the people still editing lose nothing, as their save is stored when it arrives.

Re-entry after the editor configuration/presigned URL lifetime obtains fresh credentials and rechecks access. An active session keeps its document key, callback token and original base version even after a competing upload. Credential expiry is separate from the idle rule: explicit re-entry after idle expiry creates a new session/key; the old session may still save and conflict through the existing callback rules. No browser heartbeat or automatic refresh endpoint is added. Real long-running Office edits, delayed initial fetch, expired config rejection and reconnect behavior require pinned Document Server evidence; local HTTP checks alone cannot prove edits survive in its cache.

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
| `GET /folders`, `POST /folders` | Lists the person's folders; creates one of the person's own |
| `GET /folders/{folder_id}`, `PATCH /folders/{folder_id}` | Gives a folder; renames it |
| `GET /folders/{folder_id}/members`, `POST /folders/{folder_id}/members`, `DELETE /folders/{folder_id}/members/{member_id}` | Lists, adds and removes members |
| `GET /folders/{folder_id}/member-candidates?q=` | Finds people who can be added |
| `GET /folders/{folder_id}/rules`, `POST /folders/{folder_id}/rules`, `PATCH` and `DELETE /folders/{folder_id}/rules/{rule_id}` | Lists, adds, changes and removes sync rules |
| `POST`, `DELETE /folders/{folder_id}/files/{file_id}/lock`, `POST /folders/{folder_id}/files/{file_id}/lock/renew` | Locks a file, unlocks it and renews the person's lock ([File locks](#file-locks)) |
| `GET /folders/{folder_id}/files?after=&limit=` | Lists the folder's files with their current versions and locks, by id |
| `GET /folders/{folder_id}/files/{file_id}/versions` | Gives a file's history, newest first |
| `POST /folders/{folder_id}/files/{file_id}/versions/{version_id}/download` | Gives a presigned address that downloads the version |
| `POST /folders/{folder_id}/files/{file_id}/versions/{version_id}/restore` | Restores the version, once per `Idempotency-Key` when one is sent |
| `GET /folders/{folder_id}/changes?after=&limit=` | Gives the changes to current versions after the last one the computer saw, by id |
| `POST /folders/{folder_id}/uploads` | Prepares an upload ([Stored content](#stored-content)) |
| `GET /folders/{folder_id}/uploads/{upload_id}` | Gives an upload the computer prepared |
| `POST /folders/{folder_id}/uploads/{upload_id}/parts` | Gives the presigned addresses of its parts |
| `POST /folders/{folder_id}/uploads/{upload_id}/finalize` | Finalizes it, answering 202 while it is verified |
| `GET /health`, `GET /ready` | The API's health and readiness |

- **Routes.** Every route is declared with `laboratory_api_route()` (`services/laboratory_api.py`): `type='http'`, `auth='bearer'`, `bearer_scope='sol_laboratory.device'`, `csrf=False`, `save_session=False`, `readonly=False` and the methods it takes, and the operation of the OpenAPI document it serves. Odoo checks a CSRF token on `type='http'` routes for methods other than GET, HEAD, OPTIONS and TRACE, so the API's routes set `csrf=False`; the computer's key, which a browser never sends by itself, takes its place. Without a key, Odoo's bearer authentication accepts a browser session for a same-origin page opened by the person; the API refuses it with `invalid_key`, as every route needs the computer of the key.
- **Routes without a key.** Signing in gives the key, so it is `auth='public'`; health and readiness are `auth='none'` and read only. They are the only exceptions, and they too set `csrf=False` and `save_session=False`.
- **The computer of a call.** Once Odoo has verified the key, `_from_key()` finds its computer, and only that one: a computer named in the request, such as Medilab Sync's `X-Sync-Device-Id`, is ignored. `_from_key()` relies on that verification of the key's hash, so only bearer routes call it. Saves and locks record the computer it found.
- **Checks.** Every route checks, before it writes with full rights: the key's scope, through Odoo; that the computer is not revoked, through `_from_key()`; and the laboratory files permission, the folder membership and the folder's sample, through `_check_folder_access()` or `_check_file_access()`. Full rights never reach a record the check did not cover. Signing out and revoking one's own computers skip the laboratory files permission, so a person who lost it still stops their computers.
- **Running twice.** A route that changes something has the effect of one run when Odoo's retrying runs it again or the computer repeats a call whose answer it lost.
  - **Creating with an `Idempotency-Key`.** A route that creates a record takes an optional `Idempotency-Key` header: a key the computer generates for the request, unique for the computer. The record keeps it, through `medilab.laboratory.idempotency.mixin`, with a unique index on its computer and the key. A request repeated with the same key answers with the record the first one created; a key sent with another request is refused with `idempotency_conflict`, and a key that is not 1 to 200 letters, digits, dots, colons, hyphens or underscores with `invalid_request`. Two requests with one key at once make one record: the second one's creation fails on the unique index, `_create_once()` turns it into a `ConcurrencyError`, and Odoo runs the request again, which finds the record. Creating a folder takes it, and so does preparing an upload; a later route that creates a record inherits the mixin and declares its index.
  - **Without a key**, creating a folder of a name its owner already has is refused with `folder_exists`.
  - **The other changes** are idempotent by their own rules: adding a member already in the folder, or a sync rule of a kind and pattern it has, answers with that one; removing a member or a rule already gone answers 204; a rename or a change of a rule sets the same values again; a lock its holder takes again is renewed. A repeated sign-out finds its key gone and is refused with `invalid_key`, which the computer takes as signed out; revoking a computer already revoked changes nothing.
- **Folders.** The folder routes check `read` to read a folder, its members and its rules, and `share` to rename it, add and remove members, find people to add and change its rules, then act with full rights. A folder is listed and read only by its members and, for a folder of a sample, by members who see the sample; anyone else gets `not_found`. A folder created through the API is the person's own, of no sample and no category, upload-only, and records the computer it was created from. Changing its owner, turning it off and archiving it are done in the back office only. A folder's answer has `can_share`, whether the person may do what `share` allows, so the computer does not work the rules out itself.
- **Finding people to add.** `member-candidates` takes at least 2 characters of a name or login and answers at most 10 people, with their id, name and login only: active internal users with the laboratory files permission who are not members yet. Adding anyone else, or an id of nobody, is refused with `not_eligible` and one message.
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
| `folder_archived`, `folder_disabled`, `folder_exists`, `locked`, `not_locked`, `upload_incomplete`, `upload_closed` | 409 |
| `not_eligible`, `not_lockable`, `not_editable`, `idempotency_conflict` | 422 |
| `too_many_attempts` | 429 |
| `internal_error` | 500 |
| `try_again`, `editing_unavailable`, `storage_unavailable` | 503 |

- `invalid_key` and `invalid_credentials` carry a `WWW-Authenticate: Bearer` header.
- `method_not_allowed` answers a method the route does not take, with an `Allow` header naming those it takes. A path the API does not have is `not_found`.
- Odoo's own refusals answer in the same format: a missing or invalid key, and a session of another person with a key, are `invalid_key`; a record the person may not read (`AccessError`) or that does not exist (`MissingError`) is `not_found`, so the answer does not tell that a record exists; any other user error is `invalid_request`. `permission_denied` is only raised by name, such as for a person without the laboratory files permission.
- `internal_error` answers an exception nobody expected, with a generic message and an `id`. The server logs the exception and its traceback under that id; the answer tells nothing else about it.
- `too_many_attempts`, `try_again` and `storage_unavailable` carry a `Retry-After` header in seconds. `try_again` answers a request still failing on concurrency after Odoo's last try, after 5 seconds; `storage_unavailable` answers an upload route while the bucket cannot be reached, after 5 seconds too.
- **Adding to the API.** A feature adds its routes with `laboratory_api_route()`, its operations to the OpenAPI document, and any code of its own to `ERROR_STATUSES` (`constants/laboratory_api.py`) and to the document's error codes. Its tests call its routes through `LaboratoryApiCase` (`tests/laboratory_api_case.py`), which checks every answer against the document, so they are its contract tests.
- **Health.** `GET /medilab/api/v1/health` answers once Odoo serves requests; `GET /medilab/api/v1/ready` also runs the checks of `ir.http._laboratory_files_ready_checks()`, the database's and the bucket's, and 503 when one fails. The bucket's check reads the bucket with Odoo's key, waiting at most 2 seconds to connect and 3 for the answer, and fails while the bucket is not configured. A feature that adds a part the API needs adds its check there. Readiness never includes the editing service, so it answers ready while the editing service is down; the editing service has its own health check. When Odoo cannot reach the database at all, it answers before any route of the API does.

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
- Signing and rejecting take the file's row without changing it, once the signer is checked, so a signature and a concurrent save of the same file wait for each other and the second one runs again: a signature that comes after a newer version is refused, and a save after a signature adds an unsigned version. Someone who may not sign is refused without waiting on a save. The file's last save stays as it was.
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
