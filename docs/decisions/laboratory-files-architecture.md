# Laboratory files architecture

Approved by the owner on 2026-10-21 for the [laboratory files](../specs/laboratory-files.md) and Medilab Sync. It decides how the laboratory files API runs, where file content is stored and which online editing service is used. The approval covers the architecture only: it waives no correctness, security or existing acceptance criterion. Existing constraints stay: immutable versions, version history, conflict handling, signatures, file locks, folder permissions and the audit trail.

Each requirement has an ID and a priority:

- **P0**: mandatory for correctness and security.
- **P1**: mandatory before production.

## Context

- MediLab modules depend only on Odoo Community apps. The old module served a FastAPI REST API inside Odoo through OCA's `fastapi` addon.
- Medilab Sync, a Tauri, Rust and React desktop application, and later Medilab Mobile reach laboratory files through a REST API. File bytes go between the computer and an S3 bucket, never through Odoo.
- Folders, members, sync rules, computers, files, versions, locks, editing sessions and the signing of versions are Odoo models of `sol_laboratory`, with their access checks and audit trail.

## Decision 1: the API is native Odoo HTTP controllers

The laboratory files API is a set of Odoo HTTP controllers in `sol_laboratory`, under `/medilab/api/v1`. Authentication, authorization, business rules, version management, locks, signing and the audit trail stay in Odoo.

**Rationale.** The API calls the same model checks the back office uses, such as `_check_folder_access()`, so there is one implementation of every rule. No service or dependency is added outside Odoo Community. Not chosen: FastAPI inside Odoo through OCA's `fastapi` addon, and a FastAPI service next to Odoo.

### Transaction safety and concurrency

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| API-01 | P0 | Odoo 20's request retrying is taken from its source and tested in the deployed configuration, not assumed from Odoo 19. |
| API-02 | P0 | Preparing and finalizing an upload, storing a version, restoring, locking, opening an editing session and storing an editor's save are idempotent: run twice, by Odoo's retrying or by a client repeating a call whose answer it lost, they have the effect of one run and give the same answer. |
| API-03 | P0 | Database constraints, row locks and one conflict answer prevent duplicate versions, lost updates and invalid status changes. |
| API-04 | P0 | A bucket operation that succeeded in a transaction that then failed or ran again leaves nothing that counts: content counts only once the row that records it commits. A rollback never undoes a bucket operation. |
| API-05 | P0 | Audit entries, notifications and other side effects are not duplicated by a retry: they are written in the transaction of their work, which a retry rolls back, or they are idempotent. |
| API-06 | P1 | Where Odoo and the bucket cannot change atomically, a reconciliation job finds and repairs or reports the difference. |

### API contract and security

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| API-07 | P1 | A versioned OpenAPI document describes `/medilab/api/v1`. CI validates it and runs contract and regression tests of the routes against it. |
| API-08 | P1 | Every route validates its request the same way and answers errors in one format, with the error's code and the HTTP status of that code. |
| API-09 | P0 | Routes use Odoo's bearer authentication with the computers' key scope, without CSRF tokens, which a bearer key replaces, and without a session. A call without a computer's key is refused, also from a signed-in browser. |
| API-10 | P0 | Every call checks the key's scope, that the computer is not revoked, the person's laboratory files permission, the folder membership and, for a folder of a sample, that the person sees the sample. |
| API-11 | P0 | Signing in is rate limited against guessing passwords. |
| API-12 | P0 | The server never stores a computer's password or a path on a computer. |
| API-13 | P0 | Full rights (`sudo()`) are used only after a check that covers every rule they pass over, and never to reach a record the person may not see. |

### Medilab Sync

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| API-14 | P1 | Medilab Sync moves to `/medilab/api/v1` in its own issue: request fields, answers, authentication headers and error handling. Its credential store behaves as it does now. |
| API-15 | P1 | Installations already in use follow a migration strategy that is tested. Moving the path is not assumed to be harmless because the old contract is incompatible. |

## Decision 2: laboratory files have a private bucket of their own

File content is stored in a private S3-compatible bucket used only for laboratory files: MinIO if the existing infrastructure suits it, otherwise an equivalent S3-compatible provider the deployment supports. Content is addressed by its SHA-256 in the database: every object has a random key, and a content table holds one verified object per SHA-256. Computers upload and download through presigned addresses, in parts for uploads, and abandoned uploads are cleaned up automatically.

**Rationale.** A bucket of its own gets its own credentials, lifecycle rules for unfinished uploads, and backups, apart from Odoo's attachments. Content addressing stores shared content once. Presigned addresses keep file bytes out of Odoo's requests. Addressing content in the database rather than by object key needs no server-side copy, which providers limit to 5 GiB, and no conditional write, and an object key tells nothing about its content.

### Content integrity

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| STO-01 | P0 | The server verifies the size and SHA-256 of the content actually stored before it counts. The SHA-256 a computer sends is a claim. |
| STO-02 | P0 | A multipart ETag, or a provider's composite checksum, is never taken for the SHA-256 of the whole file. |
| STO-03 | P0 | Verification reads the stored object outside the API's requests, such as in a job that streams it, with a strategy the chosen provider supports. |
| STO-04 | P0 | File bytes never pass through the API's requests and answers. |

### Deduplication and atomicity

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| STO-05 | P0 | Every upload is written to an object of its own, under a random key the server makes, and stays a staging object until it is verified and finalized. |
| STO-06 | P0 | Once verified, an object is canonical and never rewritten. Concurrent uploads of the same content write different objects, so none can overwrite or corrupt another. |
| STO-07 | P0 | Finalizing is idempotent and safe under concurrent requests, Odoo's retrying and lost answers. |
| STO-08 | P0 | A content table holds, per object, its key, size, SHA-256 and verification state, and is unique by SHA-256 among verified content. Versions refer to verified content. When a verified SHA-256 already has content, the new version refers to it and the new object is deleted: the same content is stored once. |
| STO-09 | P0 | A restored version refers to the verified content of the version it restores, without copying its bytes. |
| STO-10 | P1 | Orphaned staging objects, partly completed operations and failed finalizations are found and cleaned up. |

### Security and retention

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| STO-11 | P0 | The bucket is private, and every credential has the least access it needs. |
| STO-12 | P0 | Presigned addresses are short-lived and are made only after the person's access is checked. Knowing or guessing a content's SHA-256 never gives access to it, and reveals no object key. |
| STO-13 | P1 | Encryption, the expiry of multipart uploads, object cleanup, backups and disaster recovery are defined. |
| STO-14 | P1 | Cleanup never removes an object a version, folder or other required record still refers to. |
| STO-15 | P1 | Backups of the bucket are restored in tests, not only made. |
| STO-16 | P1 | The retention of laboratory files, still open, is reconciled with versions that never change and are never deleted. |

## Decision 3: online editing uses ONLYOFFICE Community Edition

Office documents are edited online through a self-hosted ONLYOFFICE Document Server Community Edition, 9.4 or later, subject to verifying the upstream version and licence. A tested release is pinned; `latest` is never deployed. Document Server runs in the cluster, and its JWT secret is managed in Doppler.

**Rationale.** The online editing design of the [laboratory files](../specs/laboratory-files.md#online-editing) already uses Document Server's editor, callbacks and JWT. A self-hosted Community Edition keeps documents inside the laboratory's infrastructure.

### Integration and security

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| EDT-01 | P1 | The network flow between the browser, Document Server, Odoo and the bucket is defined and verified, with secure communication both ways where needed. |
| EDT-02 | P0 | Callbacks are checked: their JWT, the document key, the editing session and the authorization of the person saving. |
| EDT-03 | P0 | An address a callback gives is never fetched blindly: strict URL and host checks and network restrictions prevent SSRF. |
| EDT-04 | P0 | Save callbacks are idempotent: a repeated callback never adds a second version. |
| EDT-05 | P0 | Concurrent editing, the expiry of a session, permission changes, callback retries and failures while saving are handled. |
| EDT-06 | P0 | Force save stays off, and a version is added when the editing session ends. |
| EDT-07 | P0 | A conflict version is kept when another computer saves the file during online editing. |
| EDT-08 | P0 | Only files of the eligible categories are edited online; raw-data files never are. |

### Availability and licensing

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| EDT-09 | P1 | Document Server is optional: when it is unavailable, syncing, history, downloads and restore keep working. |
| EDT-10 | P1 | Document Server has a health and readiness check of its own. |
| EDT-11 | P1 | Integration, failure and concurrency tests run against the pinned Document Server. |
| EDT-12 | P1 | Before production, the upstream licence and additional terms of the chosen version are reviewed: copyright and legal notices, AGPL obligations and trademark restrictions. Not modifying the source is not assumed to reduce the obligations to attribution. |

## Operations

| ID     | Priority | Requirement |
| ------ | -------- | ----------- |
| OPS-01 | P1 | Readiness checks, monitoring and operational documentation cover the API, the bucket and Document Server. |
| OPS-02 | P1 | The deployment configuration is validated: pinned versions, secrets, network flow and bucket settings. |

## What these decisions do not decide

These stay open in the [laboratory questions](../../questions/laboratory.md) until the responsible people confirm them. Where the code already behaves one way, that behaviour is provisional:

- the retention and deletion of laboratory files, including content shared between versions and signed versions;
- whether a signed version is also signed through Viettel Sign, and whether the person who saved a version may sign it;
- who creates a sample's folders, and when;
- whether the folders of a completed or cancelled sample refuse uploads and online editing.

## Related documents

- [Laboratory files](../specs/laboratory-files.md)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Architecture](../infrastructure/architecture.md)
- [Secrets](../infrastructure/secrets.md)
- [Laboratory questions](../../questions/laboratory.md)
