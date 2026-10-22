import type { ConfigContext, ExpoConfig } from "expo/config";

// The MediLab address of a build made without MEDILAB_URL: the local app.
export const DEFAULT_SERVER_URL = "http://localhost:8069";

export default function appConfig({ config }: ConfigContext): ExpoConfig {
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
    },
    plugins: ["expo-router"],
    extra: {
      serverUrl: process.env.MEDILAB_URL || DEFAULT_SERVER_URL,
    },
  };
}
