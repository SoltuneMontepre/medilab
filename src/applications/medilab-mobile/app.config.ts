import type { ConfigContext, ExpoConfig } from "expo/config";

// The MediLab address of a build made without MEDILAB_URL: the local app.
export const DEFAULT_SERVER_URL = "http://localhost:8069";

// The variable naming the path of the build's google-services.json, its Firebase project. A build without one gets no
// pushes.
const GOOGLE_SERVICES_FILE = "GOOGLE_SERVICES_JSON";

export default function appConfig({ config }: ConfigContext): ExpoConfig {
  const googleServicesFile = process.env[GOOGLE_SERVICES_FILE] || undefined;
  // Firebase's plugins need the project's file; a build without it has no Firebase app and registers no push id. Pushes
  // reach the phone by its Firebase Installation ID, which replaces the deprecated FCM token.
  const firebasePlugins: NonNullable<ExpoConfig["plugins"]> = googleServicesFile
    ? ["@react-native-firebase/app", ["@react-native-firebase/messaging", { installationIdEnabled: true }]]
    : [];
  return {
    ...config,
    name: "MediLab",
    slug: "medilab-mobile",
    version: "0.1.0",
    scheme: "medilab",
    platforms: ["android", "ios"],
    ios: {
      bundleIdentifier: "com.medilab.mobile",
      supportsTablet: true,
    },
    android: {
      package: "com.medilab.mobile",
      googleServicesFile,
    },
    plugins: [
      "expo-router",
      "expo-secure-store",
      // The camera reads sample labels; the app records no sound.
      [
        "expo-camera",
        {
          cameraPermission: "MediLab reads the QR code on sample labels with the camera.",
          microphonePermission: false,
          recordAudioAndroid: false,
        },
      ],
      // React Native Firebase reaches the Firebase Apple SDK through Swift Package Manager, which needs dynamic
      // frameworks.
      ["expo-build-properties", { ios: { useFrameworks: "dynamic" } }],
      ...firebasePlugins,
    ],
    extra: {
      serverUrl: process.env.MEDILAB_URL || DEFAULT_SERVER_URL,
    },
  };
}
