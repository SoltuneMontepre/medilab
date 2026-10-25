# Mobile questions

- **Apple developer account.** Decided: the first release is Android only; iOS comes later.
- **Installing the app.** Decided: staff install the Android app from an APK in the `medilab-release` R2 bucket, without Google Play.
- **Printing labels from the phone.** Opening a bottle and preparing a solution print a label (US-T12, US-T13). The phone prints only through its print dialog, AirPrint on iOS or a print service on Android, which not every label printer supports. Do the laboratory's label printers take prints from phones, or is the label printed from a computer afterwards?
- **Working offline.** The app works only online for now: an action without a connection is refused and retried by hand. Laboratories and customer sites can have poor coverage. Should a later version queue actions on the phone and send them when the connection is back, and what happens when the record changed on the web meanwhile?
- **Automatic updates.** Decided: updates are mandatory, so a phone with an update waiting cannot be used until it has it. Odoo answers whether a phone has an update, and the files are in the `medilab-release` bucket, shared with Medilab Sync's packages.
- **Signing keys.** Decided: the update signing key and the Android upload key are kept in Doppler and read only by the release pipeline; Hoàng Anh keeps their backup.
- **Release bucket.** Is the bucket named `medilab-release`, and what is its public address, from which phones download updates and the APK?
- **First install.** How do staff get the APK the first time: a link or a QR code, and where is it shown, such as on the MediLab sign-in page or sent by an administrator?
- **Android versions.** Expo SDK 58 runs on Android 7 (API 24) and later. Does the laboratory have older phones, or should the app require a newer Android version?

## Related documents

- [Medilab Mobile](../docs/functional/laboratory_module/applications/medilab-mobile.md)
- [Shared technical features](../docs/functional/shared.md)
