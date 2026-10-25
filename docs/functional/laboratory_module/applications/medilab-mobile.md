# Medilab Mobile

Medilab Mobile is deferred from the [current scope](../../index.md#scope). These requirements describe the deferred application.

Medilab Mobile is the phone app of the laboratory's staff. It brings the work done away from a desk to the phone: the to-do list and its tasks, conversations, scanning sample labels and container QR codes, sample photos, the customer's signature on a handover record, and entering and signing results at the bench. It reaches MediLab through the Laboratory module's [REST API](../overview.md#laboratory-files) and receives pushes through [Firebase Cloud Messaging](../../shared.md#4-firebase-cloud-messaging-mobile-push). MediLab checks every call with the person's permissions, so the app shows and does only what the person may see and do on the web.

## Platforms and installation

| Rule        | Description |
| ----------- | ----------- |
| Platforms   | Android and iOS phones and tablets, built with React Native and Expo from one TypeScript code base. The first release is for Android. |
| Installing  | Staff install the Android app from an APK the laboratory publishes in its release bucket, not from Google Play. |
| Languages   | Vietnamese by default, or English, chosen at sign-in or in the settings, and kept for the next start. |
| Connection  | The app works online. An action that cannot reach MediLab is not done: the app says so and offers to retry. A photo or a signature not sent yet stays on the phone until it is sent or the person discards it. |
| Modules     | A screen whose module is not installed is not shown, such as container scanning without Inventory or support requests without E-commerce ([SH-01](../../shared.md#sh-01-modular-installation-and-integration)). |

## Updates

| Rule        | Description |
| ----------- | ----------- |
| Checking    | The app asks MediLab whether it has an update when it starts and whenever it comes back to the foreground. |
| Mandatory   | When MediLab has an update, the app shows an updating screen and cannot be used until the update is installed. The person cannot postpone it. |
| Code only   | An update that changes only the app's code downloads, and the app restarts into it. |
| New install | An update that needs a new install downloads the APK and opens Android's installer. |
| Signed      | The app installs only updates signed with the laboratory's key. An unsigned or altered update is refused, and the app keeps the version it has. |
| Releases    | An administrator stops or rolls back a release in MediLab and sets the oldest version MediLab still serves. A phone with an older version shows only the updating screen. |

## Signing in

| Rule        | Description |
| ----------- | ----------- |
| Server      | The MediLab address is filled in for the build and can be changed; production must use HTTPS. |
| Login       | The person signs in with their MediLab login and password. The phone gets its own device key, kept in the phone's secure storage; the password is never stored. |
| Who         | Only people with an internal user sign in. A customer, a subcontractor or a portal user is refused. |
| Device      | The phone is a device of the REST API, like a computer running [Medilab Sync](medilab-sync.md): an administrator sees it with the person's other devices and revokes it. A revoked device or an archived user is refused at the next call; the app removes the key and returns to sign-in. |
| Pushes      | Signing in registers the phone's Firebase token for the person; signing out turns the token off and removes the device key from the phone. |

## Tasks and notifications (SH-10, SH-11, US-HD17)

| Rule          | Description |
| ------------- | ----------- |
| Home          | The app opens on the person's day, as the Tasks app does on the web ([SH-10](../../shared.md#sh-10-tasks-and-to-do-list)): today's planned tasks, the next tasks to do with the action each needs, and the tasks waiting in the queues they can claim from. |
| To-do list    | The person's open tasks, soonest deadline first, and their finished tasks. Opening a task opens its document at the action to take. |
| Lifecycle     | The person claims a task from a queue, starts it and marks a task created by hand done, as on the web. A task already claimed by someone else cannot be claimed. |
| Managing      | A person with the task permissions, such as a head of department for their department, assigns a waiting task, reassigns one with a reason and creates a task by hand with an assignee and a deadline. |
| Notifications | The person's notifications ([SH-11](../../shared.md#sh-11-schedules-and-reminders)), unread first; opening one opens its document and marks it read. |
| Pushes        | A push names the event and the document's code. Tapping it opens the document; when the person can no longer see the document, the app says so instead of showing an empty screen. A push to a tester never names the customer or the customer's name for a sample. |
| Preferences   | The person turns pushes on or off per event in the app's settings, which are their notification preferences ([SH-11](../../shared.md#sh-11-schedules-and-reminders)). Mandatory events cannot be turned off. |

## Conversations (SH-12, US-S23)

Conversations follow [SH-12](../../shared.md#sh-12-conversations).

| Rule             | Description |
| ---------------- | ----------- |
| Conversations    | The person's direct and group conversations, the same as in Discuss on the web, with their unread messages. New messages appear without reloading while the app is open. |
| Messages         | Text, photos from the camera or the gallery, and files. A message can mention a person with @. |
| Chatter          | A task, sample or test request opened in the app shows its chatter, and the person posts a note on it. The app never sends a chatter message to a customer. |
| Mute             | The person mutes a conversation, so its messages are no longer pushed to them. |
| Support requests | With E-commerce installed, sales see the support requests they handle, take a waiting one and answer it, following [Support](../../ecommerce_module/features/sales.md#7-support-us-s20-us-s23). The customer reads the answer on the portal and is notified as on the web. |

## Scanning (US-HD06, US-T30, US-T31)

| Rule          | Description |
| ------------- | ----------- |
| Camera        | The app reads QR codes with the phone's camera. The code can be typed when a label cannot be read. |
| Sample label  | Scanning a sample's label opens the sample by its lab code, showing only what the person may see of it. From it, a person of a department the sample was handed over to records its receipt ([US-HD06](../features/head-of-department.md#2-samples-and-results-us-hd06-to-us-hd09)), and a tester claims the unassigned testing tasks of their department on it. A person outside the department is refused, as on the web. |
| Container     | With Inventory installed, scanning a container's QR code opens it. A tester opens a sealed bottle, adds the bottles they use to a preparation, or adds the containers a test used to the result they are entering, following [Containers and use](../../inventory_module/features/tester.md#1-containers-and-use-us-t12-to-us-t16). |
| Labels        | The label of an opened bottle or a prepared solution opens as a PDF that the person prints or shares from the phone. |

## Testing at the bench (US-T30, US-HD17)

| Rule          | Description |
| ------------- | ----------- |
| Test          | A testing task shows its sample's lab code, its parameter, its way of testing and its due date, and its method's steps, each with how long it takes, what to do, its note and where it is done. |
| Result        | The tester enters the result as a number in the unit of the way of testing or as a text, and its conclusion, following [Results](../features/tester.md#2-results-us-t05-to-us-t09-us-t17-us-t18-us-t22). A result that is unusual or close to the regulation limit shows the same warning as on the web before it is sent. |
| Sending       | The tester sends the result for approval and signs it with a deliberate action and a confirmation, as on the web ([SH-04](../../shared.md#sh-04-signatures-and-digital-signing)). |
| Approving     | A head of department sees the results of their department waiting for their signature, and signs or rejects one with a reason, following [Samples and results](../features/head-of-department.md#2-samples-and-results-us-hd06-to-us-hd09). |
| Read only     | A result that is approved, or waiting for someone else's signature, is shown and cannot be changed. |

## Collecting and receiving samples (US-SD04, US-SD05)

| Rule             | Description |
| ---------------- | ----------- |
| Collection tasks | Sample delivery staff see their collection tasks with their time and place, and mark one done once the samples are collected, following [Collecting samples](../features/sample-delivery-staff.md#1-collecting-samples-us-sd01-to-us-sd05). |
| Photos           | Photos taken with the camera when a sample is collected or received are attached to the sample. Testers never see them. |
| Handover record  | Sample delivery staff open a draft handover record of a test request and give the phone to the customer, who reads the samples listed, signs by hand on the screen and confirms. The signature, the time and the phone are recorded, and the signed PDF is emailed to the customer. A signed record is only shown. |

## Acceptance criteria

- Signing in stores a device key in the phone's secure storage and never the password.
- A customer, a subcontractor or a portal user cannot sign in.
- A revoked device is signed out at its next call.
- Signing out turns the phone's push token off.
- The to-do list shows the same open tasks as on the web, soonest deadline first.
- Two people claiming the same task from their phones: the second is told it is already claimed.
- Tapping a push opens its document; a document the person can no longer see shows a message instead.
- A push to a tester never names the customer or the customer's name for a sample.
- A push turned off for an event in the app's settings is no longer sent to the person.
- A message sent from the phone appears in Discuss on the web, and a message sent on the web appears on the phone.
- A note posted on a sample from the phone appears in its chatter on the web and sends nothing to the customer.
- A muted conversation's messages are not pushed to the person.
- An answer to a support request from the phone sets the request to answered and notifies the customer.
- Scanning the label of a sample not handed over to the person's department records no receipt and says why.
- Scanning a sample's label lets a tester claim only the unassigned testing tasks of their own department.
- A result entered and signed on the phone shows on the web waiting for the head of department, with the tester's signature.
- A head of department may approve their own result on the phone, as on the web; the Lab Head reviews it when signing the final report.
- A photo taken on the phone appears on the sample on the web and not to testers.
- A handover record signed on the phone records the phone and emails the PDF; it cannot be changed afterwards.
- An action without a connection is refused with a message and changes nothing; an unsent photo stays on the phone.
- Container scanning is not shown when Inventory is not installed, and support requests are not shown when E-commerce is not installed.
- A phone with an update waiting cannot be used until it has installed it.
- An update not signed with the laboratory's key is refused, and the app keeps the version it has.
- A phone with a version older than the oldest one MediLab serves shows only the updating screen.
- After an administrator rolls back a release, phones return to the previous version at their next check.

## Related documents

- [Laboratory overview](../overview.md)
- [Shared technical features](../../shared.md)
- [Tester](../features/tester.md)
- [Head of department](../features/head-of-department.md)
- [Sample delivery staff](../features/sample-delivery-staff.md)
- [Inventory tester](../../inventory_module/features/tester.md)
- [Sales](../../ecommerce_module/features/sales.md)
- [Medilab Sync](medilab-sync.md)
