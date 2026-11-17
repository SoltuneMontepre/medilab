import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { addReleases, type Catalog, serializeCatalog } from "./catalog";
import { buildManifest, signManifest } from "./manifest";

// Adds one Android release, its code update and its APK, to the catalog the release pipeline publishes. Every input is
// an environment variable the pipeline sets; the update key is read from a file, so it never reaches the command line.
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set.`);
  }
  return value;
}

function httpsUrl(name: string): string {
  const value = required(name);
  if (!value.startsWith("https://")) {
    throw new Error(`${name} must start with https://.`);
  }
  return value.replace(/\/+$/, "");
}

const version = required("MEDILAB_MOBILE_VERSION");
const runtimeVersion = required("MEDILAB_MOBILE_RUNTIME_VERSION");
const exportDir = required("EXPORT_DIR");
const catalogFile = required("CATALOG_FILE");
const apk = readFileSync(required("APK_FILE"));
const pubDate = new Date().toISOString();

const metadata = JSON.parse(readFileSync(join(exportDir, "metadata.json"), "utf8"));
const manifest = buildManifest({
  files: metadata.fileMetadata.android,
  expoClient: JSON.parse(readFileSync(required("EXPO_CONFIG_FILE"), "utf8")),
  runtimeVersion,
  baseUrl: httpsUrl("UPDATE_URL"),
  createdAt: pubDate,
  readFile: (path) => readFileSync(join(exportDir, path)),
});
const signature = signManifest(manifest, readFileSync(required("UPDATE_KEY_FILE"), "utf8"));

const catalog: Catalog = existsSync(catalogFile) ? JSON.parse(readFileSync(catalogFile, "utf8")) : { releases: [] };
const common = { platform: "android", runtime_version: runtimeVersion, version, pub_date: pubDate } as const;
const updated = addReleases(catalog, [
  { ...common, kind: "code", manifest, signature },
  { ...common, kind: "install", url: httpsUrl("APK_URL"), sha256: createHash("sha256").update(apk).digest("hex") },
]);
writeFileSync(catalogFile, serializeCatalog(updated));
