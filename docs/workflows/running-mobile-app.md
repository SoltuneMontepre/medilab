# Running Medilab Mobile

How a developer runs [Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md) on a phone, an emulator or a simulator against a MediLab server.

## Steps

1. **Tools.** Install Node 22.13 or later, Bun, and Android Studio for Android or Xcode on a Mac for iOS.
2. **Dependencies.** Run `bun install` in `src/applications/medilab-mobile`; every command below runs there.
3. **Server.** Start MediLab with `task up`. The app talks to `http://localhost:8069`, or to the address in `MEDILAB_URL` when Metro starts or the app is built.
   - An Android emulator reaches the computer's `localhost` after `adb reverse tcp:8069 tcp:8069`.
   - A phone on the same network needs `MEDILAB_URL=http://<computer's address>:8069`.
4. **Development build.** `bun run android` or `bun run ios` builds the app with its development client, installs it on the emulator, simulator or connected phone, and starts Metro. Build it again only after a change to the native dependencies or `app.config.ts`. The `development` profile in `eas.json` builds the same app on EAS instead, such as for iOS without a Mac: `bun x eas-cli build --profile development --platform ios`.
5. **Develop.** `bun run start` starts Metro, and the installed development build loads the code from it.
6. **Check.** Run the checks of [ci-mobile-app](../infrastructure/pipelines.md#ci-mobile-app) with `bun run typecheck`, `bun run lint`, `bun run test` and `bun x expo export`. `task test:apps` runs the tests with those of the other applications.

## Related documents

- [Medilab Mobile](../functional/laboratory_module/applications/medilab-mobile.md)
- [Testing](../conventions/testing.md#applications)
- [Pipelines](../infrastructure/pipelines.md#ci-mobile-app)
