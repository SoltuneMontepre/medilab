import type { ConfigContext, ExpoConfig } from "expo/config";

// The MediLab address of a build made without MEDILAB_URL: the local app.
export const DEFAULT_SERVER_URL = "http://localhost:8069";

// The variable naming the path of the build's google-services.json, its Firebase project. A build without one gets no
// pushes.
const GOOGLE_SERVICES_FILE = "GOOGLE_SERVICES_JSON";

// The version of a build made without MEDILAB_MOBILE_VERSION, which only the release pipeline sets.
export const DEFAULT_VERSION = "0.1.0";

// Android's version code of a semantic version, so that a later version always installs over an earlier one.
export function versionCode(version: string): number {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(version);
  if (!match) {
    throw new Error(`MEDILAB_MOBILE_VERSION ${version} is not a version such as 1.2.3.`);
  }
  const [major, minor, patch] = match.slice(1).map(Number);
  return major * 1_000_000 + minor * 1_000 + patch;
}

// The variable naming the path of the PEM certificate of the update key, which expo-updates checks every code update's
// signature against. Only a release build has it; a build without it takes no updates.
const UPDATE_CERTIFICATE = "MEDILAB_MOBILE_UPDATE_CERTIFICATE";

// The theme's primary colour, behind the splash screen, and the mark's accent, behind the adaptive icon.
const BRAND = { primary: "#0a4d8c", accent: "#0083ef" };

// The path MediLab serves code updates at, in the Expo Updates protocol.
const UPDATES_PATH = "/medilab/api/v1/mobile/updates";

export default function appConfig({ config }: ConfigContext): ExpoConfig {
  const version = process.env.MEDILAB_MOBILE_VERSION || DEFAULT_VERSION;
  // The release pipeline names the native build a code update runs on; a local build names none.
  const runtimeVersion = process.env.MEDILAB_MOBILE_RUNTIME_VERSION || undefined;
  const googleServicesFile = process.env[GOOGLE_SERVICES_FILE] || undefined;
  // Firebase's plugins need the project's file; a build without it has no Firebase app and registers no push id. Pushes
  // reach the phone by its Firebase Installation ID, which replaces the deprecated FCM token.
  const firebasePlugins: NonNullable<ExpoConfig["plugins"]> = googleServicesFile
    ? ["@react-native-firebase/app", ["@react-native-firebase/messaging", { installationIdEnabled: true }]]
    : [];
  const serverUrl = process.env.MEDILAB_URL || DEFAULT_SERVER_URL;
  // A build made for a MediLab served over HTTP, such as the local app, may reach one; other builds use HTTPS only.
  const allowsHttp = serverUrl.startsWith("http:");
  const updateCertificate = process.env[UPDATE_CERTIFICATE] || undefined;
  // The app checks for updates itself, at start and back from a minute away, so expo-updates never checks on its own.
  const updates: ExpoConfig["updates"] = updateCertificate
    ? {
        enabled: true,
        url: serverUrl + UPDATES_PATH,
        checkAutomatically: "NEVER",
        codeSigningCertificate: updateCertificate,
        codeSigningMetadata: { keyid: "main", alg: "rsa-v1_5-sha256" },
      }
    : { enabled: false };
  return {
    ...config,
    name: "MediLab",
    slug: "medilab-mobile",
    version,
    ...(runtimeVersion ? { runtimeVersion } : {}),
    scheme: "medilab",
    platforms: ["android", "ios"],
    // The MediLab mark of the web's theme, sol_theme's medilab.svg.
    icon: "./assets/icon.png",
    ios: {
      bundleIdentifier: "com.medilab.mobile",
      supportsTablet: true,
      ...(allowsHttp ? { infoPlist: { NSAppTransportSecurity: { NSAllowsArbitraryLoads: true } } } : {}),
    },
    android: {
      package: "com.medilab.mobile",
      versionCode: versionCode(version),
      googleServicesFile,
      adaptiveIcon: { foregroundImage: "./assets/adaptive-icon.png", backgroundColor: BRAND.accent },
      // A new install opens Android's installer on the APK the app downloaded.
      permissions: ["android.permission.REQUEST_INSTALL_PACKAGES"],
    },
    plugins: [
      "expo-router",
      "expo-secure-store",
      // The app opens on the web's navbar colour with the MediLab mark.
      ["expo-splash-screen", { image: "./assets/logo.png", imageWidth: 112, backgroundColor: BRAND.primary }],
      // The camera reads sample labels and photographs samples; the app records no sound.
      [
        "expo-camera",
        {
          cameraPermission: "MediLab reads the QR code on sample labels and photographs samples with the camera.",
          microphonePermission: false,
          recordAudioAndroid: false,
        },
      ],
      // Conversations send photos from the camera or the gallery; the app records no sound.
      [
        "expo-image-picker",
        {
          photosPermission: "MediLab sends photos from your gallery in conversations.",
          cameraPermission: "MediLab takes photos to send in conversations.",
          microphonePermission: false,
        },
      ],
      // React Native Firebase reaches the Firebase Apple SDK through Swift Package Manager, which needs dynamic
      // frameworks.
      [
        "expo-build-properties",
        { ios: { useFrameworks: "dynamic" }, android: allowsHttp ? { usesCleartextTraffic: true } : {} },
      ],
      ...firebasePlugins,
    ],
    updates,
    extra: {
      serverUrl,
      allowsHttp,
    },
  };
}
