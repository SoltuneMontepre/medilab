# Mobile questions

- **Apple developer account.** Installing Medilab Mobile on iPhones outside development, through TestFlight or the App Store, and pushing to them through Firebase both need an Apple Developer Program membership, at 99 USD a year. Does the laboratory or the team have one, or does the first release target Android only?
- **Installing the app.** Staff can install the app from Google Play and the App Store, or from a file the laboratory hands out, such as an Android APK or a device management tool. Which one, since it decides what the release pipeline builds and signs?
- **Printing labels from the phone.** Opening a bottle and preparing a solution print a label (US-T12, US-T13). The phone prints only through its print dialog, AirPrint on iOS or a print service on Android, which not every label printer supports. Do the laboratory's label printers take prints from phones, or is the label printed from a computer afterwards?
- **Working offline.** The app works only online for now: an action without a connection is refused and retried by hand. Laboratories and customer sites can have poor coverage. Should a later version queue actions on the phone and send them when the connection is back, and what happens when the record changed on the web meanwhile?

## Related documents

- [Medilab Mobile](../docs/functional/laboratory_module/applications/medilab-mobile.md)
- [Shared technical features](../docs/functional/shared.md)
