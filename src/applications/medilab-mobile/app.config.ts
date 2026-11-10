import type { ConfigContext, ExpoConfig } from "expo/config";

// The MediLab address of a build made without MEDILAB_URL: the local app.
export const DEFAULT_SERVER_URL = "http://localhost:8069";

// The variable naming the path of the build's google-services.json, its Firebase project. A build without one gets no
// pushes.
const GOOGLE_SERVICES_FILE = "GOOGLE_SERVICES_JSON";

export default function appConfig({ config }: ConfigContext): ExpoConfig {
  const googleServicesFile = process.env[GOOGLE_SERVICES_FILE] || undefined;
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
      // React Native Firebase reaches the Firebase Apple SDK through Swift Package Manager, which needs dynamic
      // frameworks.
      ["expo-build-properties", { ios: { useFrameworks: "dynamic" } }],
      // Firebase's plugins need the project's file; a build without it has no Firebase app and registers no token.
      ...(googleServicesFile ? ["@react-native-firebase/app", "@react-native-firebase/messaging"] : []),
    ],
    extra: {
      serverUrl: process.env.MEDILAB_URL || DEFAULT_SERVER_URL,
    },
  };
}
