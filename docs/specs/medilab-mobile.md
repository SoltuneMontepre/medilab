# Medilab Mobile

Stories: SH-10, SH-11, SH-12, US-T30, US-T31, US-HD06, US-HD17, US-S23, US-SD04, US-SD05

## Goal

[Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md) is a client of MediLab like the web: it shows and does only what the person may see and do there. A phone signs in once with the person's login and gets its own device key, the same key a computer running Medilab Sync gets, and calls MediLab's own routes under `/medilab/api/v1`. Every route calls the model method the web calls, with the person's rights, so permissions, record rules and lifecycle checks stay on the server. The phone receives pushes through Firebase Cloud Messaging on a token linked to its device, so signing out or revoking the phone stops them. Updates are mandatory and signed: Odoo answers from a release catalog the release pipeline publishes, as it does for [Sync updates](sync-updates.md), and never holds a signing key.

## Design

### The API

The phone's routes are routes of the [laboratory files API](laboratory-files.md#laboratory-files-api): declared with `laboratory_api_route()`, described in `sol_laboratory/api/openapi.yaml`, answered and refused in its format and tested through `LaboratoryApiCase`. The OpenAPI document gets a tag per feature below.

- **The module that owns a route declares it.** `sol_laboratory` declares the device, push, task, sample, result, handover, notification and conversation routes; `sol_commerce` the support request routes; `sol_inventory` the container routes. A route of a module that is not installed does not exist and answers `not_found`. The app learns what is installed from `GET /modules`.
- **No laboratory files permission.** The phone's routes are declared with `permission=False`: the models check what the person may do, as on the web. The laboratory files routes keep their check, so a phone reaches folders only as a computer of a person with that permission would.
- **The person's rights.** An endpoint reads and acts as the user of the key, never with full rights; only the model method itself elevates where the web's call does too, such as `receive_by_label()` recording a receipt. A record the person may not read answers `not_found`, so the answer does not tell that it exists.
- **Language.** The app sends its language, `vi` or `en`, in `Accept-Language`. The route serves the request in that language when the language is installed in MediLab, so messages and translated names match the app; otherwise it answers in the person's language.
- **Model refusals.** A `UserError` or `ValidationError` raised by the model method a route calls answers `action_refused` with Odoo's message, which the app shows as it is; on the laboratory files routes it stays `invalid_request`. Refusals the app acts on have their own codes. Every code below is added to `ERROR_STATUSES` and to the OpenAPI document's error codes.
- **Creating once.** A route that creates something takes `Idempotency-Key` with the meaning the [laboratory files API](laboratory-files.md#laboratory-files-api) gives it: a task, a result, a photo, a message, a chatter note, a conversation and a support answer. A request the app sends again after a lost answer creates nothing more and answers what the first one created.
- **Files in a request.** A photo, a signature or a file is sent in the JSON body as base64 with its name and type: at most 10 MiB per file once decoded and 25 MiB per request. A larger one is refused with `too_large` before anything is stored. A file the person reads is downloaded from `GET /attachments/{attachment_id}`, which reads the attachment with their rights, so a tester never downloads a sample photo.
- **Calls without a connection** never reach MediLab; the app keeps an unsent photo or signature and sends it again with the same `Idempotency-Key`.

| Code | Status | Answers |
| ---- | ------ | ------- |
| `action_refused` | 409 | The model refused the action; the message says why |
| `already_claimed` | 409 | Claiming a task someone else claimed first |
| `already_taken` | 409 | Taking a support request someone else took first |
| `result_warning` | 409 | Signing a result whose warnings the person did not acknowledge |
| `too_large` | 413 | A file over its limit |
| `mandatory_event` | 422 | Turning off a push of a mandatory event |
| `update_unavailable` | 503 | The release catalog is absent, unreadable or invalid |

### Phones

A signed-in phone is a `medilab.laboratory.device`, the record a [computer](laboratory-files.md#computers) is, with the platform `android` or `ios`. Sign-in, keys, sign-out, revoking, the audit trail and the [limits on signing in](laboratory-files.md#limits-on-signing-in) are the computers' own; only these differ.

- **Signing in.** `POST /sign-in` takes the phone's installation id, which the app generates once and keeps in its secure storage, its name, such as the phone's model, and its platform. Odoo checks the login as for a computer, and a person with two-factor authentication signs in with an Odoo API key of scope `rpc` in place of the password, created in their Odoo preferences.
- **Who.** A phone signs in only for an internal user, which in MediLab is always a person of the laboratory. A portal user, which every customer and subcontractor is, is refused with `permission_denied`. The laboratory files permission is not needed.
- **The key.** The key is the device key of scope `sol_laboratory.device`, named `Medilab Mobile: <name>` among the person's API keys. The app keeps it in `expo-secure-store` and never keeps the password.
- **A refused key.** A revoked phone, a phone signed out elsewhere and an archived user are refused with `invalid_key` at the next call; the app removes the key and its token and returns to sign-in. A revoked phone is signed in again only as a new installation.
- **Administrators** see phones with the person's computers in the back office and revoke them there.

### Push tokens

The Firebase token is a `medilab.mobile.device` linked to its phone's device: one per phone, holding the phone's current token.

| Route | Does |
| ----- | ---- |
| `PUT /push-token` | Registers the token Firebase gave the app for the phone of the key, or replaces its old one, and turns it on |
| `DELETE /push-token` | Turns the phone's token off |

- A token already registered for another phone, such as after the app is reinstalled, moves to this phone; a token is never pushed to two phones.
- Signing out, revoking the phone and removing its key from anywhere turn its token off in the same transaction, so no push reaches a phone that is no longer signed in. Firebase rejecting the token for good turns it off too ([Firebase](../functional/shared.md#4-firebase-cloud-messaging-mobile-push)).
- Pushes go only to tokens that are on and whose phone is signed in.
- A token is registered only through `PUT /push-token`, by a signed-in phone; no session route registers one.

### The person and the modules

| Route | Does |
| ----- | ---- |
| `GET /me` | The person's name, login, department and roles, and what they may do: create, assign and reassign tasks, take support requests |
| `GET /modules` | The installed MediLab modules, such as `sol_laboratory`, `sol_commerce` and `sol_inventory` |

What the person may do comes from the same permission checks the web's buttons use, so the app hides what the web hides. `GET /modules` reads the modules' installed state with full rights and answers only their technical names.

### Pushes

A push is created when a notification is delivered on the push channel ([SH-11](../functional/shared.md#sh-11-schedules-and-reminders)) or a conversation gets a message ([SH-12](../functional/shared.md#sh-12-conversations)). It is a `medilab.push.delivery`, sent by the push job, which retries it ([SH-09](../functional/shared.md#sh-09-scheduled-tasks)).

- **Payload.** A push has a title, a body and data. The data are `event`, the event's code or `message` for a conversation message; `model` and `id`, the document; and `code`, the document's code. The code is the record's own code, such as a sample's lab code; for a sample test or a result, its sample's lab code; for a task, its document's code; empty when the document has none.
- **Text.** The title is the event's name in the person's language and the body is the document's code. A push never carries the notification's message, the document's name or any other field, so it never names the customer or the customer's name for a sample, to a tester or anyone else. The app reads the rest after the tap, with the person's rights.
- **Conversation messages.** The title is the conversation's name and the body is the author's name; the message's text is not pushed. The data are `event: message`, `model: discuss.channel`, `id` and no code.
- **Tapping a push** opens `GET /documents/{model}/{record_id}`. A document the person can no longer see answers `not_found`, and the app says so instead of showing an empty screen.
- **On by default.** Once a person has a signed-in phone, every event they are notified of is also pushed unless they turned its push off. A mandatory event's push cannot be turned off, and a push of a mandatory event turned off before is sent all the same.
- **Firebase in the app.** The app registers its token, the phone's Firebase Installation ID, through `@react-native-firebase/messaging` (`register()` and `onRegistered()`, with Installation ID messaging turned on) at sign-in, at each start and whenever Firebase gives a new one. A build gets Firebase only from its `google-services.json` ([Running Medilab Mobile](../workflows/running-mobile-app.md)); without it the app registers no token.
- **Conversation pushes at once.** A new message in a conversation creates a push for each member's phones except its author's and the members who muted the conversation, and triggers the push job at once instead of waiting for its next run.

### Notifications and documents

| Route | Does |
| ----- | ---- |
| `GET /notifications?after=&limit=` | The person's notifications, unread first, then newest first, each with its event, title, date, document and whether it is read; `next_after` is the `after` of the next page |
| `POST /notifications/{message_id}/read` | Marks the notification read, as opening it in the web's inbox does |
| `GET /notification-preferences` | Every event with its name, whether it is mandatory and whether its push is on |
| `PUT /notification-preferences/{event_code}` | Turns the event's push on or off with `push` |
| `GET /documents/{model}/{record_id}` | The document's code, title and phone screen, and its address on the web |

- Notifications are the person's inbox notifications ([SH-11](../functional/shared.md#sh-11-schedules-and-reminders)): Odoo messages with an inbox notification for the person's contact. Reading one marks that notification read for the web as well. The title of a notification is its event's name, and the list never carries its text, as a push does not.
- The preferences list the events that notify people: an event the administrator turned off is left out, and its push cannot be set.
- A push preference is a `medilab.notification.preference` of channel `push`, set with `set_own()`, so the web shows the same choice. Turning off a mandatory event's push is refused with `mandatory_event`.
- A document's screen is `task`, `sample`, `sample_test`, `test_result`, `handover_record`, `support_request`, `container` or `conversation`. Any other readable document answers the screen `web` with its code, its title and its address on the web, which the app shows with "Open on the web". The title is the document's code when it has one, otherwise its display name.

### Tasks

| Route | Does |
| ----- | ---- |
| `GET /tasks/today` | The person's day, from `get_dashboard_data()` |
| `GET /tasks?list=open\|finished\|queue&after=&limit=` | The person's open tasks, soonest deadline first; their finished tasks, latest first; or the tasks waiting in the queues they can claim from |
| `GET /tasks/{task_id}` | The task, its document's code and screen, and the actions the person may take on it |
| `POST /tasks` | Creates a task by hand with a name, a note, an assignee and a deadline |
| `POST /tasks/{task_id}/claim`, `/start`, `/done` | `action_claim()`, `action_start()`, `action_done()` |
| `POST /tasks/{task_id}/assign` | Assigns or reassigns the task to a person or a department, with a reason when it moves away |
| `GET /tasks/assignees?q=` | The people and departments the person may give a task to |

- The lists search the person's tasks with `is_mine` and `in_my_queue`, as the web's to-do list and queues do, so both show the same tasks in the same order. A page's `next_after` is how many tasks the pages before it gave.
- The actions of a task are the buttons the web's form shows the person: claim while it waits in their queue, start and mark done while it is theirs, and assign with the permission to edit it. `GET /me` says whether the person may create and assign tasks, from the same permissions, so the app shows the screens only with them.
- A testing task gives its method's steps from `method_step_ids`: each step's minutes, instruction, note and location. A collection task gives its planned start and end and its sample's sampling location.
- Claiming a task someone else claimed first is refused with `already_claimed`; a task outside the person's queues with `action_refused`.
- Assigning and reassigning run the `medilab.task.reassign` wizard's `action_confirm()` on the task, so its checks apply. Moving a task away from its person or department without a reason is refused with `action_refused`: the task refuses it, so the web refuses it the same way. A person outside the task's department takes the task to their department unless the request names one; naming a department and no person puts the task in that department's queue. A person without the permission to edit the task is refused with `permission_denied`.
- Creating a task by hand creates a task of the general type with the person's rights, in the assignee's department; a task created on the phone never names a document ([SH-10](../functional/shared.md#sh-10-tasks-and-to-do-list)). The task keeps the phone it was created on and its `Idempotency-Key`. A person without the permission to create tasks is refused with `permission_denied`.

### Scanning sample labels

| Route | Does |
| ----- | ---- |
| `GET /samples/lookup?code=` | The sample of the lab code, as the person may see it, with its handover to the person's department and the unassigned testing tasks of their department on it |
| `POST /samples/receive` | Records the receipt of the scanned code by the person's department, through `receive_by_label()` |
| `POST /samples/{sample_id}/claim` | Claims the listed testing tasks of the sample through `action_claim()` |
| `GET /samples/{sample_id}` | The sample as the person may see it |

- The sample is read with the person's rights and answers only the fields they may read: a tester never gets the customer, the customer's name for the sample or its photos.
- A sample not handed over to the person's department, or a person in no department, is refused by `receive_by_label()` with `action_refused` and records nothing. Scanning a received sample again keeps the first receipt.
- The tasks offered and claimed are the sample's open testing tasks in the person's own department's queue; any other task is refused.

### Testing at the bench

| Route | Does |
| ----- | ---- |
| `GET /sample-tests/{sample_test_id}` | The test's lab code, parameter, way of testing and due date, the unit and decimals of the way on the sample's type, whether the sample has a regulation, and its reported result |
| `POST /sample-tests/{sample_test_id}/results` | Enters a result: a number with its decimals, or a text, and its conclusion |
| `GET /results/{result_id}`, `PATCH /results/{result_id}` | The result with its status, its warnings and what the person may do with it; changes a draft result |
| `POST /results/{result_id}/sign` | Sends the result for approval or approves it, through `action_sign()` |
| `POST /results/{result_id}/reject` | Rejects the result with a reason, through `action_reject()` |
| `GET /results?awaiting=me` | The results waiting for the person's signature |

- A result is created and changed with the person's rights, so the unit, the copied limit, the machine and the start time are worked out as on the web; the machine and the start are corrected on the web only.
- The warnings are those of the sanity check before sending ([US-T22](../functional/laboratory_module/features/tester.md#2-results-us-t05-to-us-t09-us-t17-us-t18-us-t22)): one model method that both the web and the route call. Signing a result with warnings needs `warnings_acknowledged`; without it, it is refused with `result_warning`.
- Signing takes `confirmed: true`, which the app sends only from its confirmation step, so signing is a deliberate action ([SH-04](../functional/shared.md#sh-04-signatures-and-digital-signing)). The approval mixin decides the level: a tester's signature sends the result, a head of department's approves it, and a head may approve a result they entered.
- Rejecting needs a reason; an empty or blank one is refused by `action_reject()` with `action_refused`.
- The results waiting for the person are the results awaiting approval that they may read, kept when `approval_can_sign` is true for them; it is computed, not stored, so the route filters them before paging. A result that is approved or waits for someone else's signature answers that nothing can be done with it.

### Collecting samples and photos

- Collection tasks are tasks of the sample collection type, listed and marked done through the [task routes](#tasks).
- `POST /samples/{sample_id}/photos` attaches a photo through `action_attach_photo()`, with the person's rights. `GET /samples/{sample_id}/photos` lists the photos the person may read, which a tester never may.

### Handover records

| Route | Does |
| ----- | ---- |
| `GET /handover-records?status=draft\|signed` | The handover records the person may read |
| `GET /handover-records/{record_id}` | The record's code, test request, who handed the samples over, the samples it lists with their amount and condition, and when and on which phone it was signed |
| `POST /handover-records/{record_id}/sign` | Records the customer's signature through `action_sign()` |

- Signing takes the signature as a PNG, at most 1 MiB, and `confirmed: true`. The route signs through the record's `_sign()` with the phone of the key, which is recorded as the device the record was signed on; neither the app nor any caller of `action_sign()` names the device.
- A signed record is only shown. Signing it again from the phone that signed it answers the signed record, so a signature sent again after a lost answer is not refused; from any other phone it is refused with `action_refused`.

### Conversations and chatter

Conversations are Odoo Discuss channels ([SH-12](../functional/shared.md#sh-12-conversations)) of type direct (`chat`) and group (`group`).

| Route | Does |
| ----- | ---- |
| `GET /conversations` | The person's direct and group conversations, with their unread count, whether they are muted and their last message |
| `POST /conversations` | Opens the direct conversation with one person through `_get_or_create_chat()`, or creates a group with a name and members through `_create_group()` |
| `GET /conversations/{channel_id}/messages?before=&after=&limit=` | Messages through `mail.message._message_fetch()` |
| `POST /conversations/{channel_id}/messages` | Posts a message with its text, mentions and files through `message_post()` |
| `POST /conversations/{channel_id}/seen` | Marks the conversation read up to a message through the member's `_mark_as_read()` |
| `PUT /conversations/{channel_id}/mute` | Mutes or unmutes it through the member's `mute_until_dt`, as Discuss on the web does |
| `GET /people?q=` | Active internal users, for new conversations and mentions |
| `GET /documents/{model}/{record_id}/messages`, `POST /documents/{model}/{record_id}/notes` | Reads a task's, a sample's or a test request's chatter, and posts a note on it |

- **Internal only.** MediLab's channel member model refuses a member without an internal user in any Discuss channel, on the web and the phone alike, so a customer or a subcontractor never joins a conversation.
- **Mentions** name internal users only. A message notifies the people it mentions on each channel they keep on ([SH-11](../functional/shared.md#sh-11-schedules-and-reminders)).
- **Notes.** A note is posted with the note subtype, which is internal: it reaches only the people it mentions and the internal followers, never a customer. The chatter is read with the person's rights, so it shows what the web's chatter shows them.
- **Refreshing without Odoo's bus.** The app does not open Odoo's websocket. A message push with data refreshes the list and the open conversation; while a conversation is open, the app also asks for messages after the last one it has about every 10 seconds, and the list is refreshed when the app comes back to the foreground.

### Support requests

With E-commerce installed, `sol_commerce` adds:

| Route | Does |
| ----- | ---- |
| `GET /support-requests?list=mine\|waiting` | The open and answered requests the person handles, or the open requests nobody has taken |
| `GET /support-requests/{request_id}` | The request with its messages |
| `POST /support-requests/{request_id}/take` | `action_take()`; a request someone else took first is refused with `already_taken` |
| `POST /support-requests/{request_id}/answer` | Posts the answer as a comment through `message_post()` |

The answer is posted as on the web, so `_message_post_after_hook()` sets the request answered, closes its task and Odoo notifies the customer, who reads it on the portal.

### Containers and labels

With Inventory installed, `sol_inventory` adds routes for scanning a container's QR code and acting on it, each calling the action Inventory gives the web: `GET /containers/lookup?code=` opens the container, `POST /containers/{container_id}/open` opens a sealed bottle, `POST /preparations` prepares a solution from the scanned bottles, and `POST /results/{result_id}/containers` adds a scanned container to the result being entered. A container of another store or not usable is refused as on the web.

`GET /containers/{container_id}/label` answers the label of an opened bottle or a prepared solution as a PDF, rendered by the report the web prints. The app opens it in the phone's system dialog to print or share.

### Updates

Every update is mandatory and signed ([Updates](../functional/laboratory_module/applications/medilab-mobile.md#updates)). An update is either a code update, which `expo-updates` downloads and restarts into, or a new install, an APK the app downloads before opening Android's installer. The version is a semantic version; the runtime version names the native build a code update runs on.

Like the Sync updates route, these two are plain `auth='none'` HTTP routes, outside `laboratory_api_route()`, described in their own public contract `sol_laboratory/api/mobile-updates.openapi.yaml`.

| Route | Does |
| ----- | ---- |
| `GET /mobile/release/{platform}/{runtime_version}/{version}` | Whether the phone must update: 204 when it is current; 200 with `code`, or `install` with the APK's version, address and SHA-256; or `unavailable` when it is older than the oldest version served and no release reaches it |
| `GET /mobile/updates` | The code update for the phone, in the Expo Updates protocol |

- **Public.** Both routes are `auth='none'`, so a phone that is signed out also updates. Like the [Sync updates route](sync-updates.md#routes), they never use cookies, keys or addresses from the request as authority, answer `Cache-Control: no-store`, refuse invalid platforms and versions with `invalid_request`, and answer `update_unavailable` while the catalog is missing or invalid.
- **Checking.** The app asks the release route when it starts and when it comes back to the foreground. On `code` it fetches the update through `expo-updates`; on `install` it downloads the APK, checks its SHA-256 and opens the installer; on `unavailable` it shows only the updating screen. The app cannot be used until the update is installed.
- **The Expo Updates route** follows the protocol's version 1: it requires `expo-protocol-version: 1`, reads `expo-platform` and `expo-runtime-version`, and answers the newest eligible code update of that runtime as a `multipart/mixed` answer with its manifest and the manifest's `expo-signature` exactly as the catalog holds them, or 204 when there is none.
- **Signing.** The release pipeline signs every manifest with the update key; the app embeds the matching certificate and `expo-updates` refuses a manifest whose signature does not verify, keeping the version it has. An APK is signed with the laboratory's upload key, and Android installs it over the app only when the key is the same. Odoo stores and serves signatures; it never reads or holds a key.
- **The catalog** is a read-only JSON file at `MEDILAB_MOBILE_RELEASES_FILE`, published last by the release pipeline after the artifacts, with the size limits and the all-or-nothing validation of the Sync catalog. Each release names its platform, kind (`code` or `install`), runtime version, version and publication date; a code release holds its manifest and signature, an install its HTTPS address and SHA-256.
- **Administrators** set, in the settings, the oldest version MediLab still serves and the releases it stops serving. A stopped release is never answered; the newest release not stopped is. A phone that already runs a stopped code update returns to an earlier one only when the release pipeline republishes that one as a new signed update, because `expo-updates` never launches an update older than the one it runs; returning to the code built into the installed APK instead is the protocol's `rollBackToEmbedded` directive, which the pipeline signs the same way.
- **iOS.** The first release is for Android. The routes take `ios`; the catalog has no iOS release until there is one, and an iOS build answers 204.

### Data

- `medilab.laboratory.device` takes the platforms `android` and `ios`.
- `medilab.mobile.device` has `laboratory_device_id`, required and unique: the phone the token belongs to. Its user is the phone's user.
- `medilab.task` has `created_by_device_id` and `idempotency_key`, unique together where the key is set: the phone a task was created on by hand and the key of its request.
- `medilab.handover.record.signed_device_id` names the phone's `medilab.laboratory.device`, which is never deleted, rather than its token, which the cleanup job removes once it is off.
- `medilab.push.delivery` pushes either a notification or a conversation message: `notification_id` or `message_id`, exactly one, each unique with the token.
- The diagram is [laboratory.prisma](../infrastructure/database/laboratory/laboratory.prisma).

### Verification

- Every route has an `HttpCase` through `LaboratoryApiCase`, which checks its answers against the OpenAPI document, including refusals for a portal user, a revoked phone and a person without the permission the route needs.
- The app's screens are tested with Jest and React Native Testing Library ([Testing](../conventions/testing.md)).
- A Maestro flow on an Android emulator signs `demo.tester` in, scans a sample's label, claims its task, enters the result and signs it. It runs locally and in a nightly job, not as a required check of pull requests.
- A Cypress test of each feature checks on the web what the phone did, such as a result waiting for `demo.head_of_department`.

## Related documents

- [Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md)
- [Shared technical features](../functional/shared.md)
- [Laboratory files](laboratory-files.md)
- [Sync updates](sync-updates.md)
- [Running Medilab Mobile](../workflows/running-mobile-app.md)
