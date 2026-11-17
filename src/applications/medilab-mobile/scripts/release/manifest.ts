import { createHash, randomUUID, sign } from "node:crypto";

// The part of the metadata.json of `expo export` that names one platform's files.
export type ExportedFiles = {
  bundle: string;
  assets: { path: string; ext: string }[];
};

// A file of a code update, as the Expo Updates protocol names it.
type ManifestAsset = {
  hash: string;
  key: string;
  contentType: string;
  fileExtension: string;
  url: string;
};

export type ManifestInput = {
  files: ExportedFiles;
  // The public `expo config` of the build, which the app reads as its configuration after the update.
  expoClient: Record<string, unknown>;
  runtimeVersion: string;
  // The HTTPS address the update's files are published under.
  baseUrl: string;
  createdAt: string;
  readFile: (path: string) => Buffer;
};

const CONTENT_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  svg: "image/svg+xml",
  ttf: "font/ttf",
  otf: "font/otf",
  json: "application/json",
  xml: "application/xml",
};

function manifestAsset(path: string, ext: string, contentType: string, input: ManifestInput): ManifestAsset {
  // `expo export` on Windows writes backslashes; a URL needs slashes.
  const file = path.replaceAll("\\", "/");
  const content = input.readFile(file);
  return {
    hash: createHash("sha256").update(content).digest("base64url"),
    key: createHash("md5").update(content).digest("hex"),
    contentType,
    fileExtension: `.${ext}`,
    url: `${input.baseUrl}/${file}`,
  };
}

// The manifest of a code update in version 1 of the Expo Updates protocol, as the exact text it is signed and served as.
export function buildManifest(input: ManifestInput): string {
  const manifest = {
    id: randomUUID(),
    createdAt: input.createdAt,
    runtimeVersion: input.runtimeVersion,
    launchAsset: manifestAsset(input.files.bundle, "bundle", "application/javascript", input),
    assets: input.files.assets.map((asset) =>
      manifestAsset(asset.path, asset.ext, CONTENT_TYPES[asset.ext] ?? "application/octet-stream", input),
    ),
    metadata: {},
    extra: { expoClient: input.expoClient },
  };
  return JSON.stringify(manifest);
}

// The base64 RSA-SHA256 signature of the manifest's text, which `expo-updates` checks against the app's certificate.
export function signManifest(manifest: string, privateKey: string): string {
  return sign("sha256", Buffer.from(manifest, "utf8"), privateKey).toString("base64");
}
