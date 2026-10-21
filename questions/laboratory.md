# Laboratory questions

- **Zero limits (US-AD07).** Odoo stores an empty number as 0, so a regulation limit of exactly 0, such as 0 CFU/250 mL, reads as "no limit" and is entered as the text "Not detected" instead. Does any regulation need a numeric limit of 0, for example so results can be compared with it automatically?
- **Changing a due date.** A sample test's due date can be changed by hand. Who may change it, and does it keep the changed date when the request's expected date changes? (blocks US-HD05)
- **Due date check.** A due date falls on a weekday and the scheduler checks that a slot is free or can be made free. Do public holidays count as non-working days, does the check block saving or only warn, may it move the bookings of other tests, and does it suggest the earliest date that can be met? (blocks US-HD05)
- **Team work.** Departments can be split into teams. Do testing tasks also queue by team, and does the team lead assign them instead of the head of department? (blocks US-AD13)
- **Who maintains customers.** A customer's details are an Odoo contact, and Odoo lets only its contact managers create and edit contacts, so for now only administrators create and edit customers. Should sales get Odoo's contact creation group, or should a customer write its contact with full rights once the customer permission is checked, as people do? (blocks US-S03)
- **Cancelling during testing.** A test request can be cancelled while testing, but the lifecycles let only expected, received and testing samples, and waiting, assigned and testing sample tests, be cancelled. What happens to a sample on hold or awaiting approval, and to a test outsourced or with a result entered, when its request is cancelled? For now they keep their status. (US-SD06, US-S17)
- **Every test cancelled.** When the head of department cancels every sample test of a sample, nothing is left to test or report. Is the sample cancelled too, and its test request once all its samples are? For now the sample keeps its status. (US-HD09)
- **Correcting a reported result.** A change request on a result whose report is already issued creates a new result version, but the issued report keeps the old value until someone raises a change request on the report too. Should approving the new result version reissue the report by itself, and should a change request on a result be refused while its report waits for the lab head's signature? For now the two are separate change requests. And when the lab head rejects a new report version and the results sent back are approved again, its request is already reported, so no new signing task is created: should it be? (US-T11, US-LH03)
- **Complaints and nonconforming work.** There is no way to record a customer complaint about a result or report, or work that did not follow the method, and follow it to a correction. Is this in scope, as ISO/IEC 17025 asks?
- **Quality control.** Blanks, control samples, reference materials and proficiency tests are not recorded. Does the laboratory track them, and does a failed control block the results of its run?
- **Measurement uncertainty.** A result has no uncertainty. Should results carry one, and does the report print it?
- **Staff competence.** Anyone in the department can be assigned any test. Should a person be authorised per testing method, so that assignment and the scheduler's recommendation only offer people allowed to run it?
- **Room conditions.** The temperature and humidity of working rooms are not recorded. Does a method need conditions checked before a test runs?
- **Turnaround reporting.** The lab head has no figures on how long tests take or how many finished late. Which figures are needed, and for whom?
- **Sanity check thresholds.** A numeric result is flagged when at least 10 approved results exist and it lies more than 3 standard deviations from their mean, or within 10% of the regulation limit. Are these the right defaults, and do some parameters need their own?
- **Signing a file version.** Is a signed file version also digitally signed through Viettel Sign, as printed documents are, and may the person who saved a version sign it? For now versions are not signed through Viettel Sign, and the person who saved a version may sign it; both are provisional, not decided. (blocks US-HD16)
- **Creating sample folders.** The old module let only its sync manager create a sample's folders, from the sample. Does the head of department create them, or are they created when the sample is received? The [overview](../docs/functional/laboratory_module/overview.md#laboratory-files) already says the head of department creates them from the sample; the answer confirms or corrects it. For now the head of a department that tests the sample creates them from the sample; this is provisional, not decided. (blocks US-HD15)
- **Retention of laboratory files.** When an archived folder's retention date passes, are its files deleted from the bucket, and who is told first? Versions never change and are never deleted, and content is stored once for every version that has it, also in other folders: is content another folder still keeps left in place, are signed versions and their content kept longer, and does a version whose content is removed stay in the history? Until this is answered, nothing removes stored content. (blocks US-AD30)
- **Medilab Sync installations in use.** The laboratory files API moves to `/medilab/api/v1`, which main does not serve under the old path `/api/sync/v1`, and the keys of installed computers were issued by the old server. Which installations of Medilab Sync are in use, against which server and release? Must they keep syncing until a cut-over, or may they be updated or reinstalled and signed in again then? Are the old server's folders and versions moved to the new one, so that the computers' bindings still find their folders? See also the question on the sync app's updates in [infrastructure questions](infrastructure.md). (blocks US-T23)
- **Restoring a revoked computer.** Revoking a computer is final, also when a person revokes their own, and a revoked installation cannot sign in again. Can an administrator restore a revoked computer? For now it gets back in only as a new installation of Medilab Sync, which signs in with a new installation id. (US-AD29)
- **Laboratory file API.** Decided: the API is native Odoo HTTP controllers in `sol_laboratory`, not FastAPI through OCA's `fastapi` addon nor a FastAPI service next to Odoo. Authentication, authorization, business rules, versions, locks, signing and the audit trail stay in Odoo. See the [laboratory files architecture](../docs/decisions/laboratory-files-architecture.md).
- **Laboratory file API path.** Decided: the API moves to `/medilab/api/v1` with the fields of the diagram. Medilab Sync is moved to it in an issue of its own, with a tested strategy for the installations already in use.
- **Laboratory files bucket.** Decided: laboratory files have a private S3-compatible bucket of their own, not a prefix of the filestore bucket: MinIO if the existing infrastructure suits it, otherwise an equivalent S3-compatible provider the deployment supports. Content is stored once by its SHA-256, which the server verifies.
- **Online editing service.** Decided: the laboratory runs a self-hosted ONLYOFFICE Document Server Community Edition in the cluster, a pinned and tested release of 9.4 or later, with its JWT secret in Doppler. Online editing is kept as an optional dependency: when the editing service is down, syncing, history, downloads and restore keep working.
- **Laboratory files permission.** Decided: the create permission on laboratory folders, `laboratory_folder.create.all`, is the laboratory files permission. Its holders sign computers in and create folders, and its group carries the accesses to the folders they are members of.
- **Expiry of device keys.** Decided: a computer's key does not expire; it stays valid until the computer signs out or is revoked.
- **Folder retention period.** Decided: the system parameter `sol_laboratory.laboratory_folder_retention_days`. Assumption: no document gives a retention period for laboratory files, so it is 1825 days by default. An archived folder is not unarchived.
- **Archived folders.** Decided: an archived folder behaves like a turned-off folder: it is still listed and read, and every write is refused.
- **Folder settings.** Decided: the owner and administrators rename a folder and change its sync rules. Assumption: Medilab Sync does not say which sync mode a new folder gets, so it is upload-only.
- **Folder names.** Decided: renaming changes the name people see; the name a folder was created with, unique for its owner, never changes. Creating a second folder of that name for the same owner is refused.
- **Who can be added to a folder.** Decided: active internal users holding the laboratory files permission; anyone else is refused with one message that does not say why.
- **Medilab Mobile and laboratory folders.** Decided: out of scope for now; signed-in computers are Linux or Windows, as the diagram says.
- **Laboratory folders in the back office.** Decided: only administrators change folders, members, sync rules and computers in the back office; owners manage members through the API. Changing a folder's owner, turning it off and archiving it are done only in the back office.
- **Deleting a folder.** Decided: folders are never deleted; they are archived.
- **When a version was stored.** Decided: a version's and a change's time is Odoo's creation time of the row; the diagram's `created_at` columns are dropped.
- **Sizes beyond 2 GiB.** Decided: a version's size is a 64-bit integer, through a field type the module adds, since Odoo's integers stop at 2 GiB and files reach 5 GiB.
- **Letter case and Unicode of paths.** Decided: paths are kept in Unicode NFC; paths that differ only in letter case are one file, which keeps the letter case it was first saved with. Folder names and sync rule patterns are kept in NFC too.
- **Saving the content a file already has.** Decided: when the new content's SHA-256 is the current version's, nothing is added and the current version stays, whatever version the save was based on. A restore always adds a version.
- **Files of folders without a category.** Decided for now: they are not raw data. Their Office files are edited online, as [files edited online](#171-online-editing) says, and their other files are locked, as [which files are locked](#file-locks-us-t27-us-ad31) says.
- **Office documents.** Decided: Word, Excel and PowerPoint documents are the files with the extensions `docx`, `xlsx` and `pptx`, in any letter case.
- **Turned-off folders and online editing.** Decided: a turned-off folder refuses every new version, saves of the online editor included.
- **Demo files.** Decided: the shared foundation of laboratory files brings a few demo files with versions and a conflict; the upload flow adds restores, shared content and the stored bytes.

## File locks (US-T27, US-AD31)

- **Which files are locked.** Decided with US-T26: files that are neither Office documents nor raw data, in folders of working documents, of results and of no category. Report files are not locked.
- **Who holds a lock.** Decided: the person. The computer it was taken from is recorded for information, so the person's other computers save the file too.
- **Lock duration.** Decided: the system parameter `sol_laboratory.laboratory_file_lock_minutes`, 30 minutes by default, in the Laboratory Files block of the settings.
- **A holder who leaves the folder.** Decided: removing a member, or the person losing the laboratory files permission, leaves their lock until it expires or an administrator releases it.
- **Who sees a lock.** Decided: the back office shows who holds a file's lock and until when; once the laboratory files API exists, its file listings show them too.
- **Ended locks.** Decided: as for document locks, the cleanup job removes released and expired locks after the retention period of locks; their audit entries stay.
- **Renewing a lock.** Decided: renewals are not recorded in the audit trail; taking a lock, unlocking it, its expiry and an administrator's release are.

## #173

- **Which file versions are signed.** Decided: only the current version of a file in a result folder. Conflict versions are never current, so they are never signed.
- **Who signs a file version.** Decided: a member of the folder who sees its sample, with the role of the chain's level and the sign permission of versions.
- **The department of a file version.** A sample is tested by several departments, and any of them should count for a level whose signer must belong to the department that did the work. The approval chain takes one department per document, so such a level is refused for file versions for now. Should the chain take several departments, or does one of the sample's departments count? (US-HD16)
- **When a file version's process is completed.** Once a document's process is completed, its signatures can no longer be withdrawn. When is that for a file version, for example once the test report that relies on it is issued? For now its signatures can always be withdrawn. (US-HD16)
- **Signing and later saves.** Decided: signing never stops a new save, online editing or a lock; a signed version is already never changed, and the newer version starts unsigned.
- **Sample folders in the back office.** Decided: a sample's folders, and everything in them, are shown only to people who see the sample, folder administrators included.
- **Working and report folders.** Creating a sample's folders adds its raw-data and result folders. Who creates its working-documents and reports folders, and when? Out of scope for now.
- **Uploads to a closed sample's folders.** The old module refused uploads to the folders of a completed or cancelled sample. Should the folders of a closed sample refuse uploads, and online editing? For now they do not; this is provisional, not decided.
- **Names of sample folders.** Assumption: a sample's folders are named after its lab code and their category, such as `PTN.2026.0001 Raw Data`, with the roots `PTN.2026.0001-raw` and `PTN.2026.0001-result`. Is that the name the laboratory wants?
- **The chain of file versions.** Decided: as for every document type, the chain for signing file versions is set up by administrators and comes only with the demo data; until it exists, signing a version is refused.
- **Category of a folder of no sample.** Decided: a folder has a category if and only if it has a sample. Upgrading clears the category of every folder of no sample, and logs each one with the number of its files.

## #171 Online editing

- **Files edited online.** Decided: Office files of result and working folders and of folders without a category are edited online; files of raw-data and report folders are not.
- **Who saves an online version.** Decided: the version goes to the last editor the editing service reports for the save, and the audit entry names every editor. When that person can no longer write the file, the session ends in error and its audit entry records the key of the stored content, so the content can be recovered.
- **A save after expiry.** Decided: a save is never discarded. A save arriving for an expired session is stored like any other, and the conflict rule handles a file that changed meanwhile; expiry only stops people from joining the session.
- **Idle period of editing sessions.** Decided: the system parameter `sol_laboratory.laboratory_editing_idle_hours`, 12 hours by default, in the Laboratory Files block of Settings.
- **Stuck saves.** Decided: a session still saving after the idle period expires too. A save that fails for a while answers the editing service with an error, so it calls back again.
- **Joining a session whose file changed.** Decided: a person opening a file joins its open session even when the file has a newer version; the session's save becomes a conflict.
- **Intermediate saves.** Decided: the editor's force save is off; only the save once everyone has left is a version.
- **Editing from the back office.** Decided: the back office has no Edit online button and no action to close a session.
- **The callback token.** Decided: only its SHA-256 is stored, and it is compared in constant time.
- **Online editing of a closed sample's files.** Asked with [uploads to a closed sample's folders](#173): whether a closed sample's folders refuse online editing too. For now they do not; this is provisional, not decided.
- **The editor's save and the bucket.** File bytes never pass through the API's requests. Storing an editor's save means Odoo streams the saved document from the editing service into the bucket during its callback, as nothing else can fetch it before the callback is answered without risking the save. Is the callback an accepted exception to that rule, or must the save be fetched by a job after the callback is answered, accepting that a save is lost when the job fails after the editing service has dropped the document? Proposed answer, for the team to confirm, not decided: the callback is an accepted exception; it streams the save from Document Server into the bucket without holding it in memory, because losing a save is worse than bytes passing through Odoo in that one request. (blocks US-T26)
- **Where the editor opens.** Opening a file online gives a signed editor configuration, which a page in the browser hands to ONLYOFFICE's editor. Who asks for it and where that page lives is not given: Medilab Sync with its computer key, opening the person's browser on a page that has no Odoo session, or a page of Odoo's own that the person reaches signed in, such as from the file in the back office, which today has no Edit online button. How does a person open a file online, and from which application? (US-T26)

## Laboratory files API

- **Routes without a key.** Decided: signing in is `auth='public'`, and health and readiness are `auth='none'`, all with `csrf=False` and `save_session=False`; every other route takes a computer's key.
- **Slowing a login.** Decided: the delay is counted from the last failure; an attempt refused for its delay is not counted; a login's failures are forgotten 15 minutes after its last one; a login nobody has is counted the same; a right password clears the count, also when signing in is then refused with `permission_denied` or `device_revoked`.
- **A person who lost the laboratory files permission.** Decided: they still sign out and revoke their own computers; listing them is refused.
- **Revoking someone else's computer.** Decided: administrators do it in the back office only, not through the API.
- **Waiting after `try_again`.** Decided: `Retry-After` is 5 seconds.
- **Failed sign-ins in the audit trail.** Decided: they are not recorded there; Odoo's log and the count of failed sign-ins are enough.
- **Errors without a code.** Decided: a method a route does not take answers 405 with `method_not_allowed` and an `Allow` header; an error nobody expected answers 500 with `internal_error`, a generic message and the id the server logged it under.

## Related documents

- [Laboratory overview](../docs/functional/laboratory_module/overview.md)
