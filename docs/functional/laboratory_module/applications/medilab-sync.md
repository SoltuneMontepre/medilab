# Medilab Sync

Medilab Sync is the desktop application that keeps folders on the laboratory's computers in step with the [laboratory files](../overview.md#laboratory-files) of the Laboratory module. Testers and their instruments save files where they always do; Medilab Sync uploads each new version, brings other people's versions down, and keeps both sides of a conflict. It runs in the background from the system tray and talks to the Laboratory module's REST API, with the files' bytes going straight to and from the S3 bucket.

## Platforms and installation

| Rule          | Description |
| ------------- | ----------- |
| Platforms     | Linux as DEB and RPM packages, and Windows. It is built with Tauri 2, Rust and React. |
| Background    | It runs in the system tray, can start with the operating system, and keeps syncing while its window is closed. |
| Languages     | Vietnamese by default, or English, chosen at sign-in, in the header or in the settings, and kept for the next start. |

## Signing in

| Rule              | Description |
| ----------------- | ----------- |
| Server            | The MediLab address is filled in for the build and can be changed; production must use HTTPS. Every address signed in to successfully is remembered and offered again. |
| Login             | The person signs in with their MediLab login and password. The computer gets its own device key, kept in the operating system's credential store; the password is never stored. |
| Locked store      | When the operating system has locked its credential store, the session has not ended: the application asks the person to unlock it and retry, and syncing that is already running carries on. |
| Refused           | Signing in is refused to a person without the laboratory files permission and to a revoked device. |
| Signing out       | Signing out removes the device key from the computer. |

## Folders

| Rule              | Description |
| ----------------- | ----------- |
| Binding           | The person binds a local folder to a laboratory folder by choosing it, pasting its path or dragging it into the window. The local path stays on the computer and is never sent to MediLab. |
| Own folders       | A new local folder creates a laboratory folder named after it, which the person can rename. |
| Shared folders    | Folders others share with the person are listed under Shared with you and bound by choosing a local folder; no second laboratory folder is created. |
| Not bound here    | Folders the person owns but has not bound on this computer are listed separately, ready to bind. |
| Raw and results   | Raw data and results are bound to separate local folders. |
| Sync rules        | By default every file in the folder and its subfolders is synced. The person can limit it by name prefix, name pattern with `*`, or extension, and can leave out subfolders. |
| Modes             | An upload-only folder sends local changes and never writes to the computer, for instrument computers. A two-way folder also downloads the new current versions others save. |
| Stop syncing      | Stop syncing removes the binding from this computer only. The laboratory folder, its members and the local files stay; the folder is listed again, ready to bind to any local folder. |
| Sharing           | Manage access shows the owner and the members. The owner finds people by name or login to add them and removes members; other members only see the list. |

## Syncing

| Rule              | Description |
| ----------------- | ----------- |
| Watching          | The application watches the bound folders and waits until a file stops changing before it uploads it, so one save of a document is one version. A scan of the folders at start and at intervals catches changes the watcher missed. |
| Uploading         | A file is uploaded in parts straight to the bucket, with its SHA-256 hash, from the version it was based on. An interrupted upload resumes; one that keeps failing is retried with a growing delay. |
| Downloading       | A new version is downloaded to a temporary file, checked against its hash, and only then put in place, so a half-written file never replaces a good one. |
| Changes           | Every 15 seconds the application asks for the changes to its folders since the last one it saw. |
| Queue             | Each file shows its status: pending, running, completed, conflict, error and retrying, or paused. The person pauses and resumes the queue and retries a failed file; pausing keeps the queue. |
| Lost access       | When the person loses a folder's membership or its sample, the folder stays listed with a line saying access was lost; its pending files are paused, not deleted or failed, and nothing on the computer is removed. They continue when access comes back, without binding again. |
| Turned off        | When an administrator turns a folder off, new files wait with a message and upload once it is turned on again. |
| Deleting and renaming | Deleting or renaming a file on one computer is not passed to other computers or to MediLab. |

## Conflicts, history and editing

| Rule              | Description |
| ----------------- | ----------- |
| Conflicts         | A file whose upload became a conflict shows it in Status. Keep local file keeps the computer's file and hides the conflict. Use server version backs up the local file and downloads the current version. Both versions stay on the server. |
| History           | Version history lists every version with its number, who saved it, the computer, the time and how it was made, and restores one as a new current version. |
| Opening files     | The person opens a file in its own program from the application. |
| Editing online    | Edit online opens an Office result or working file in the browser editor, on MediLab's editor page where the person is signed in, showing step 1 of 2 while it connects to the editing service and step 2 of 2 while it opens the document. When the editing service is down the application says so at once; when the editor does not answer within a minute it shows an error with Retry. Syncing never depends on the editing service. |

## Acceptance criteria

- Signing in stores a device key in the operating system's credential store and never the password.
- A revoked device is signed out and cannot sync.
- Binding a folder sends no local path to MediLab.
- Binding a folder shared by someone else creates no second laboratory folder.
- Saving a document several times within the waiting time adds one version.
- A file changed while the application was closed is uploaded at the next start.
- A downloaded file whose hash does not match is not put in place.
- Uploading a file changed on two computers from the same version keeps both versions, and Use server version keeps a backup of the local file.
- Losing access to a folder pauses its pending files and deletes nothing on the computer; getting access back resumes them.
- Stop syncing leaves the laboratory folder, its members and the local files unchanged.
- An upload-only folder never writes to the computer.
- Edit online on a raw-data file is not offered.

## Related documents

- [Laboratory overview](../overview.md#laboratory-files)
- [Tester](../features/tester.md)
- [Administrator](../features/admin.md)
- [Business flows](../../business-flows.md)
