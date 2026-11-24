import Constants from "expo-constants";
import { digest, CryptoDigestAlgorithm } from "expo-crypto";
import { File, Paths } from "expo-file-system";
import { startActivityAsync } from "expo-intent-launcher";
import * as Updates from "expo-updates";
import { Platform } from "react-native";

import { callApi } from "../../api";
import { serverUrl } from "../../config";
import type { Locale } from "../../i18n";

/** What MediLab says the phone does before it is used. */
export type Release =
  | { action: "code"; version: string }
  | { action: "install"; version: string; url: string; sha256: string }
  | { action: "unavailable" };

const APK_TYPE = "application/vnd.android.package-archive";
// Android's FLAG_GRANT_READ_URI_PERMISSION, so the installer reads the APK the app downloaded.
const GRANT_READ_URI = 1;

/** Whether the build takes updates: only a release build made with the update certificate has expo-updates on. A
 * development build's launcher reports expo-updates on whatever the build, so it never takes any. */
export function takesUpdates(): boolean {
  return !__DEV__ && Updates.isEnabled && Updates.runtimeVersion !== null;
}

/** Asks the MediLab the app was built for, which also serves its code updates, whether the phone must update; null
 * when it runs a version MediLab serves. */
export function checkRelease(language: Locale): Promise<Release | null> {
  const platform = Platform.OS === "ios" ? "ios" : "android";
  const runtime = encodeURIComponent(Updates.runtimeVersion ?? "");
  // The version of the code that runs: a code update brings its own app config.
  const version = encodeURIComponent(Constants.expoConfig?.version ?? "");
  return callApi<Release>(serverUrl, language, `/mobile/release/${platform}/${runtime}/${version}`);
}

/** Downloads the code update and restarts into it. expo-updates refuses a manifest whose signature the app's
 * certificate does not verify, and the app keeps the code it runs. False when there was nothing newer to take. */
export async function installCode(): Promise<boolean> {
  const fetched = await Updates.fetchUpdateAsync();
  if (!fetched.isNew && !fetched.isRollBackToEmbedded) {
    return false;
  }
  await Updates.reloadAsync();
  return true;
}

async function sha256(file: File): Promise<string> {
  const hash = new Uint8Array(await digest(CryptoDigestAlgorithm.SHA256, await file.bytes()));
  return Array.from(hash, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Downloads the APK, unless the phone already has it, checks it is the one MediLab named and opens Android's
 * installer on it. Android installs it over the app only when it is signed with the app's own key. */
export async function installApk(release: Extract<Release, { action: "install" }>): Promise<void> {
  const apk = new File(Paths.cache, `medilab-${release.version}.apk`);
  if (!apk.exists || (await sha256(apk)) !== release.sha256) {
    if (apk.exists) {
      apk.delete();
    }
    await File.downloadFileAsync(release.url, apk);
    if ((await sha256(apk)) !== release.sha256) {
      apk.delete();
      throw new Error("The downloaded APK is not the one MediLab named.");
    }
  }
  await startActivityAsync("android.intent.action.VIEW", { data: apk.contentUri, type: APK_TYPE, flags: GRANT_READ_URI });
}
