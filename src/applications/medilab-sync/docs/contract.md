# MediLab Sync contract

## Authentication

The control API is `/medilab/api/v1`, under the installation's configured HTTP(S) base path. The [OpenAPI document](../../../../src/core/modules/sol_laboratory/api/openapi.yaml) defines its requests, responses and refusal codes. Metadata requests send `User-Agent: MediLab-Sync/<application version>`. Authenticated requests send only `Authorization: Bearer <device key>`; no separate device-ID header is sent. Redirects are not followed by metadata or storage clients.

`POST /sign-in` sends `login`, `password`, `client_uid`, `name` and `platform` (`linux` or `windows`). The password can be an Odoo API key for a person with two-factor authentication. The response supplies `key` and `device`. `GET /devices` validates the restored session; `POST /devices/{id}/revoke` revokes a device. `POST /sign-out` signs out; `invalid_key` on a repeated sign-out is already signed out.

The device key stays in the OS credential store, service `com.medilab.filesync`, account `api_key`. The password is never persisted. Rust keeps the active key in memory without serializing it to SQLite, logs or React. A non-secret pending sign-in fingerprint pairs a recovered OS key with its server after a crash; changing the server address requires a fresh sign-in. A locked credential store does not expire the active session and never triggers plaintext fallback. The development fallback requires `MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING`; its file is written atomically with Unix mode 0600 before receiving key bytes.

Only the API's typed `invalid_key` or `device_revoked` refusal expires the session. Folder permission failures, transport failures, locked stores and storage HTTP errors do not. Behavior follows error codes, independently of translated messages. `too_many_attempts`, `try_again` and `storage_unavailable` receive up to three metadata attempts with backoff and `Retry-After`. Upload-job retries remain separately bounded.

## API mappings

| API field or operation | Desktop behavior |
| --- | --- |
| `root`, `path`, `sha256`, `number`, rule `kind` | Map into existing SQLite and IPC names at the Rust boundary |
| Folder `role`: `owner` or `member`; `can_share` | Sharing controls follow the server's permission result |
| `GET /folders/{id}/rules` | Read rules separately from folder metadata |
| `POST /folders` | Send only a folder name; local paths remain on the computer |
| Members and candidates | Use wrapped `members`, `member`, `candidates`; add with `user_id` |
| File lists and changes | Follow `next_after`; never use offset pagination on the wire |
| File detail | Locate the file within its folder's documented file list |
| Version history and detail | Read the documented version list; paginate locally and identify the current version by ID |
| Download | Authorize the folder/file/version, use its version metadata to verify bytes |
| Restore | Add a version with an idempotency key; never rewrite history |

The wire contract does not supply all former UI fields. Missing owner display names, workflow labels and object-availability probes remain absent; the desktop does not invent them. Upload-only folders do not schedule downloads or replace local files. A server folder that refuses writes does not silently become writable on the server.

## Two-way decision matrix

| Local content | Server content | Action |
| --- | --- | --- |
| Same as server | Any base | Advance the base without transfer |
| Same as base | Changed | Download and verify |
| Changed | Same as base | Upload from the known base version |
| Changed differently | Changed | Preserve both and show conflict |
| Missing | Present | Download in two-way mode |

Deleting and renaming files are not propagated. Accepting a server version first preserves a conflict copy of a divergent local file. Server conflicts remain immutable versions; they do not replace the current version.

## Concurrent transfers

The dispatcher has separate bounded upload and download slots and at most one running transfer for a local file. Upload, download and part concurrency default to 3 and are clamped to 1–4. Upload buffers share a 128 MiB budget. Hashing reads parts in order; only PUTs run concurrently. Completed-part state is persisted by the owning transfer.

Pause cancels transfers at safe checkpoints without discarding the queue or completed parts. Resume schedules refresh in the background. Startup returns running jobs to pending. Every result write checks the captured job, file and folder binding, so unbinding or reused SQLite IDs cannot redirect a transfer's result into another binding.

Job backoff grows from 1 to 60 seconds plus jitter. Actual connectivity failures keep waiting; other retryable server/storage failures stop after 20 job attempts. `Retry-After` is a lower bound. Pending server verification waits without consuming this failure budget. Authentication or lost access pauses queued work. An expired upload gets a new preparation key; ordinary conflicts and temporary refusals do not discard its upload identity.

## Direct bucket upload

1. Resolve the expected SHA-256 from the local fingerprint or a fresh full-file hash.
2. Persist a UUID preparation key and the request fingerprint with the queued job before `POST /folders/{id}/uploads`. Send `path`, `size`, `sha256` and nullable `base_version_id`. A lost answer or restart reuses that key; changed content or base gets a new key.
3. Read the upload's `part_size` and `part_count`. Zero-length or unchanged content needs no part PUT. Request part addresses with `POST /folders/{id}/uploads/{upload_id}/parts` and upload bytes directly. Refresh expired addresses using `expires_at`; no device key goes to the bucket.
4. Hash exactly the bytes read, including resumed parts. Refuse finalization if that hash differs from the expected snapshot.
5. Finalize without a request body, then read the upload until `completed`, `conflict`, `unchanged`, `failed`, `refused` or `expired`. A resumed transfer checks server status before sending any part again. Odoo verifies the complete object's size and SHA-256 asynchronously; a multipart ETag is not its content hash.
6. Record completion only after a terminal successful result. Preserve a conflict and its server-current base separately. If the local file changed after the proven snapshot was read, queue the next upload.

## Direct bucket download

The client requests a version's presigned address through its folder-scoped download route. Bytes go to a temporary file beside the destination. Size and SHA-256 must match before fsync and atomic replacement. Range resumes partial downloads. The storage client has a read-idle timeout rather than a whole-file deadline. Presigned query strings are removed from diagnostics.

## Installed clients and updates

The application identifier, database location, credential-store service/account and installation UID stay stable. Successful sign-in to the new API migrates existing local state transactionally. Without verified old-to-new folder identities, old remote IDs are quarantined: folders are shown as not bound, queued jobs and local paths/files remain, and no upload is claimed until explicit rebinding. Old multipart sessions and remote cursors are not reused. Changing account or server also requires rebinding and preserves queued files.

The new updater address is `<base>/medilab/api/v1/updates/<target>/<arch>/<version>`, with a versioned User-Agent. Its availability is a server integration dependency: it is not currently an operation in the device OpenAPI document.

Production migration requires verified evidence before choosing either route:

- With the existing signing key, the server must serve an appropriately signed manifest at the old installed updater address. Other legacy routes return `410 client_update_required`.
- Without that key, legacy routes, including updates, must return `410 client_update_required` with the approved installer download information. Reinstallation requires a separately authorized release process. The client preserves a typed refusal's supplied message; it never rotates a signing key or interprets an update refusal as permission to delete data.

The original installed binaries, server compatibility routes, installer/download contract, key availability and production end-to-end upgrade/reinstall evidence remain release dependencies. Client regression tests do not prove an old installed binary accepts a new release.

## Editing online

Edit online opens `<base>/medilab/laboratory-files/<positive file_id>/edit` with the existing Tauri opener plugin in the default browser. The HTTP(S) origin and base path are validated; credentials, query strings and fragments are excluded. Launch failures are visible and retryable from the desktop.

Only supported `.docx`, `.xlsx` and `.pptx` working/result or uncategorized files offer the action. Odoo authenticates the browser session and owns authorization, progress, timeout and editor retry. The desktop receives no editor configuration or JWT. A successful browser launch proves neither editor load nor a saved version. Sync, history, restore and download operate independently of Document Server.

## Event cadence and delta IPC

Progress events contain only `{jobId, done, total}` and update the relevant job. Lifecycle changes emit a status snapshot. File-list changes emit a revision invalidation; the frontend coalesces refreshes with at most one request in flight. Multipart progress does not repeatedly reload the full file list.

## Related documents

- [Database](database.md)
- [Maintenance and verification](maintenance.md)
- [Laboratory files specification](../../../../docs/specs/laboratory-files.md)
