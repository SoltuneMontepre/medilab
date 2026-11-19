# Running Medilab Mobile

How a developer runs [Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md) on a phone, an emulator or a simulator against a MediLab server.

## Steps

1. **Tools.** Install Node 22.13 or later, Bun, and Android Studio for Android or Xcode on a Mac for iOS.
2. **Dependencies.** Run `bun install` in `src/applications/medilab-mobile`; every command below runs there.
3. **Server.** Start MediLab with `task up`. The app talks to `http://localhost:8069`, or to the address in `MEDILAB_URL` when Metro starts or the app is built. The sign-in screen changes the address, which the app keeps; a development build, or a build made for an `http://` address, takes `http://`, any other build only `https://`.
   - An Android emulator reaches the computer's `localhost` after `adb reverse tcp:8069 tcp:8069`.
   - A phone on the same network needs `MEDILAB_URL=http://<computer's address>:8069`.
4. **Pushes.** A build receives pushes only with its Firebase project: set `GOOGLE_SERVICES_JSON` to the path of the project's `google-services.json` before building, which adds React Native Firebase's plugins. A build without it, such as the checks of `ci-mobile-app`, runs without Firebase and registers no push token; MediLab sends pushes only when the server has its own [Firebase credentials](../functional/shared.md#4-firebase-cloud-messaging-mobile-push).
5. **Updates.** Only a build made with `MEDILAB_MOBILE_UPDATE_CERTIFICATE`, the path of the update key's PEM certificate, takes updates, from `MEDILAB_URL` ([Updates](../specs/medilab-mobile.md#updates)). A development build takes none and opens without asking MediLab.
6. **Development build.** `bun run android` or `bun run ios` builds the app with its development client, installs it on the emulator, simulator or connected phone, and starts Metro. Build it again only after a change to the native dependencies or `app.config.ts`. The `development` profile in `eas.json` builds the same app on EAS instead, such as for iOS without a Mac: `bun x eas-cli build --profile development --platform ios`.
7. **Develop.** `bun run start` starts Metro, and the installed development build loads the code from it. Sign in as a demo user, such as `demo.tester`, with the demo password; a customer or a subcontractor is refused.
8. **Check.** Run the checks of [ci-mobile-app](../infrastructure/pipelines.md#ci-mobile-app) with `bun run typecheck`, `bun run lint`, `bun run test` and `bun x expo export`. `task test:apps` runs the tests with those of the other applications.
9. **Maestro.** The flows in `.maestro` drive a release build on an Android emulator against MediLab with its demo data, as the nightly `maestro` job does. Install [Maestro](https://maestro.dev), start MediLab with `task test:e2e:app`, build the app with `bun run expo prebuild --platform android`, then `./gradlew assembleRelease` in `android`, which signs it with the debug keystore, and install `android/app/build/outputs/apk/release/app-release.apk`, or install the `medilab-mobile-release-x86_64` artifact of a `maestro` run on an x86_64 emulator. Run `adb reverse tcp:8069 tcp:8069`, then `maestro test --env LAB_CODE=<code> .maestro`. `LAB_CODE` is the lab code of the demo sample `sol_demo.demo_sample_label_scan`, whose lead task the flow claims; a flow changes the demo data, so run it again on a fresh database.

## Related documents

- [Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md)
- [Testing](../conventions/testing.md#applications)
- [Pipelines](../infrastructure/pipelines.md#ci-mobile-app)
