# Medilab Sync

Medilab Sync is the desktop application that keeps folders on the laboratory's computers in step with the [laboratory files](../overview.md#laboratory-files) of the Laboratory module. Testers and their instruments save files where they always do; Medilab Sync uploads each new version, brings other people's versions down, and keeps both sides of a conflict. It runs in the background from the system tray and talks to the Laboratory module's REST API, with the files' bytes going straight to and from the S3 bucket.

## Platforms and installation

| Rule          | Description |
| ------------- | ----------- |
| Platforms     | Linux as DEB and RPM packages, and Windows. It is built with Tauri 2, Rust and React. |
| Background    | It runs in the system tray, can start with the operating system, and keeps syncing while its window is closed. |
| Languages     | Vietnamese by default, or English, chosen at sign-in, in the header or in the settings, and kept for the next start. |
| Installing    | A testing task offers Download Medilab Sync to a person with the laboratory files permission. It gives the latest release's Windows installer to a Windows computer and its DEB package to a Linux x86_64 one; any other computer gets the release page, which also has the RPM package. The installers are the same for every MediLab. |
| Opening       | Open in Medilab Sync, next to it, opens the application with this MediLab's address. Both stay on the testing task, for setting up another computer, such as an instrument's. |

## Signing in

| Rule              | Description |
| ----------------- | ----------- |
| Server            | Open in Medilab Sync fills in the address and names its host under it, so the person checks it is their MediLab before entering their password; a link that opens a signed-in application only shows its window. Otherwise the address is the one the application was built with, if any, and can be changed. Production must use HTTPS. Every address signed in to successfully is remembered and offered again. |
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
| Home folder       | The home folder is `MediLab` in the person's Documents folder, or in their user folder on a computer without one, until the person chooses another. The sample folders the person is a member of are bound by themselves inside it, under the sample's lab code and the folder's category, such as `<lab code>/Raw Data` and `<lab code>/Results`, created when missing. A folder already bound stays where it is, a folder of a completed or cancelled sample is not bound, and a folder the person stopped syncing is not bound again until they bind it themselves. |
| Raw and results   | Raw data and results are bound to separate local folders. |
| Sync rules        | By default every file in the folder and its subfolders is synced. Under Advanced options, folded away until needed, the person can limit it by name prefix, name pattern with `*`, or extension, and can leave out subfolders. |
| First start       | A person with no bound folder lands on the Folders tab after signing in, which opens with the home folder. |
| Modes             | An upload-only folder sends local changes and never writes to the computer, for instrument computers. A two-way folder also downloads the new current versions others save. A bound folder says which mode it is in. |
| Stop syncing      | Stop syncing removes the binding from this computer only. The laboratory folder, its members and the local files stay; the folder is listed again, ready to bind to any local folder. |
| Sharing           | Manage access shows the owner and the members. The owner finds people by name or login to add them and removes members; other members only see the list. |

## Syncing

| Rule              | Description |
| ----------------- | ----------- |
| Watching          | The application watches the bound folders and waits until a file stops changing before it uploads it, so one save of a document is one version. A scan of the folders at start and at intervals catches changes the watcher missed. |
| Uploading         | A file is uploaded in parts straight to the bucket, with its SHA-256 hash, from the version it was based on. An interrupted upload resumes; one that keeps failing is retried with a growing delay. |
| Downloading       | A new version is downloaded to a temporary file, checked against its hash, and only then put in place, so a half-written file never replaces a good one. |
| Changes           | Every 15 seconds the application asks for the changes to its folders since the last one it saw. |
| Summary           | The Status tab opens with one sentence saying whether everything is synced, syncing, paused, in need of attention or without a folder, and offers to add a folder when there is none. Under it are the counts of files synced, in progress, with an error and in conflict; errors and conflicts are coloured, on the Status tab's name too. |
| Queue             | Each file shows its status: pending, running, completed, conflict, error and retrying, or paused. The person pauses and resumes the queue and retries a failed file; pausing keeps the queue. |
| Synced files      | The synced files are listed under the folder they belong to, and the person finds one by typing part of its name. |
| Lost access       | When the person loses a folder's membership or its sample, the folder stays listed with a line saying access was lost; its pending files are paused, not deleted or failed, and nothing on the computer is removed. They continue when access comes back, without binding again. |
| Turned off        | When an administrator turns a folder off, new files wait with a message and upload once it is turned on again. |
| Deleting and renaming | Deleting or renaming a file on one computer is not passed to other computers or to MediLab. |

## Conflicts, history and editing

| Rule              | Description |
| ----------------- | ----------- |
| Conflicts         | A file whose upload became a conflict shows it in Status. Keep local file keeps the computer's file and hides the conflict. Use server version backs up the local file and downloads the current version. Both versions stay on the server. |
| History           | Version history lists every version with its number, who saved it, the computer, the time and how it was made, and restores one as a new current version. |
| Opening files     | The person opens a file in its own program, and a bound folder in the file manager, from the application. A file that is not on the computer says so. |
| Confirming        | Stopping a folder's sync, using the server version of a conflict and removing a member each ask first, in a dialog that says what will change and names the action on its button. |
| Editing online    | Edit online opens an Office result or working file in the browser editor, on MediLab's editor page where the person is signed in, showing step 1 of 2 while it connects to the editing service and step 2 of 2 while it opens the document. The editor supports Odoo installations served at the origin root; Sync refuses an editor handoff when the configured server URL contains a path prefix. The Sync API still supports configured base paths. When the editing service is down the application says so at once; when the editor does not answer within a minute it shows an error with Retry. Syncing never depends on the editing service. |

## Acceptance criteria

- Signing in stores a device key in the operating system's credential store and never the password.
- A revoked device is signed out and cannot sync.
- Binding a folder sends no local path to MediLab.
- Binding a folder shared by someone else creates no second laboratory folder.
- A testing task offers Download Medilab Sync and Open in Medilab Sync to a person with the laboratory files permission.
- Download Medilab Sync gives a Windows computer the Windows installer and a Linux x86_64 computer the DEB package of the latest release.
- Open in Medilab Sync fills in this MediLab's address on the sign-in screen and names its host.
- The folders of a sample the person was just given to test are bound inside the home folder without the person choosing a location, also on a new installation.
- A sample folder the person stopped syncing is not bound again by itself.
- Saving a document several times within the waiting time adds one version.
- A file changed while the application was closed is uploaded at the next start.
- A downloaded file whose hash does not match is not put in place.
- Uploading a file changed on two computers from the same version keeps both versions, and Use server version keeps a backup of the local file.
- Losing access to a folder pauses its pending files and deletes nothing on the computer; getting access back resumes them.
- Stop syncing leaves the laboratory folder, its members and the local files unchanged.
- An upload-only folder never writes to the computer.
- A bound folder shows whether it is upload-only or two-way.
- A synced file opens in its own program from the Status tab.
- Edit online on a raw-data file is not offered.

## Related documents

- [Laboratory overview](../overview.md#laboratory-files)
- [Tester](../features/tester.md)
- [Administrator](../features/admin.md)
- [Business flows](../../business-flows.md)
