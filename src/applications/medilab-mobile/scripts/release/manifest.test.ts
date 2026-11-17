/**
 * @jest-environment node
 */
import { createHash, generateKeyPairSync, verify } from "node:crypto";

import { buildManifest, signManifest } from "./manifest";

const FILES: Record<string, Buffer> = {
  "_expo/static/js/android/entry-1.hbc": Buffer.from("bundle"),
  "assets/a1": Buffer.from("png"),
  "assets/b2": Buffer.from("font"),
};

function manifest() {
  return buildManifest({
    files: {
      bundle: "_expo/static/js/android/entry-1.hbc",
      assets: [
        { path: "assets\\a1", ext: "png" },
        { path: "assets/b2", ext: "woff3" },
      ],
    },
    expoClient: { name: "MediLab" },
    runtimeVersion: "7b04",
    baseUrl: "https://release.example/mobile/android/1.2.3/update",
    createdAt: "2026-11-17T00:00:00.000Z",
    readFile: (path) => FILES[path],
  });
}

describe("update manifest", () => {
  it("names each file by its SHA-256 and full HTTPS address", () => {
    const parsed = JSON.parse(manifest());
    expect(parsed.runtimeVersion).toBe("7b04");
    expect(parsed.extra).toEqual({ expoClient: { name: "MediLab" } });
    expect(parsed.launchAsset).toEqual({
      hash: createHash("sha256").update("bundle").digest("base64url"),
      key: createHash("md5").update("bundle").digest("hex"),
      contentType: "application/javascript",
      fileExtension: ".bundle",
      url: "https://release.example/mobile/android/1.2.3/update/_expo/static/js/android/entry-1.hbc",
    });
    expect(parsed.assets.map((asset: { url: string; contentType: string }) => [asset.url, asset.contentType])).toEqual([
      ["https://release.example/mobile/android/1.2.3/update/assets/a1", "image/png"],
      ["https://release.example/mobile/android/1.2.3/update/assets/b2", "application/octet-stream"],
    ]);
  });

  it("gives every update its own id", () => {
    expect(JSON.parse(manifest()).id).not.toBe(JSON.parse(manifest()).id);
  });

  it("is signed so that the certificate's key verifies the exact text, and only it", () => {
    const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const text = manifest();
    const signature = Buffer.from(
      signManifest(text, privateKey.export({ type: "pkcs8", format: "pem" }).toString()),
      "base64",
    );
    expect(verify("sha256", Buffer.from(text), publicKey, signature)).toBe(true);
    expect(verify("sha256", Buffer.from(text.replace("7b04", "7b05")), publicKey, signature)).toBe(false);
  });
});
