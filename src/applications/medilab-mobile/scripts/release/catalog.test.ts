/**
 * @jest-environment node
 */
import { addReleases, MAX_RELEASES, type Release, serializeCatalog } from "./catalog";

function install(version: string, url = "https://release.example/medilab.apk"): Release {
  return {
    platform: "android",
    kind: "install",
    runtime_version: "7b04",
    version,
    pub_date: "2026-11-17T00:00:00.000Z",
    url,
    sha256: "0".repeat(64),
  };
}

const CODE: Release = {
  platform: "android",
  kind: "code",
  runtime_version: "7b04",
  version: "1.0.0",
  pub_date: "2026-11-17T00:00:00.000Z",
  manifest: "{}",
  signature: "c2ln",
};

describe("release catalog", () => {
  it("keeps the published releases and adds the new ones after them", () => {
    const catalog = addReleases({ releases: [install("1.0.0")] }, [CODE, install("1.1.0")]);
    expect(catalog.releases.map((release) => `${release.kind} ${release.version}`)).toEqual([
      "install 1.0.0",
      "code 1.0.0",
      "install 1.1.0",
    ]);
  });

  it("refuses a release that is already published", () => {
    expect(() => addReleases({ releases: [install("1.0.0")] }, [install("1.0.0")])).toThrow(
      "The catalog already has the android install release 1.0.0.",
    );
  });

  it("writes a catalog within Odoo's limits", () => {
    expect(JSON.parse(serializeCatalog({ releases: [CODE] }))).toEqual({ releases: [CODE] });
  });

  it("refuses more releases than Odoo reads", () => {
    const releases = Array.from({ length: MAX_RELEASES + 1 }, (_, index) => install(`1.0.${index}`));
    expect(() => serializeCatalog({ releases })).toThrow(`more than ${MAX_RELEASES}`);
  });

  it("refuses a catalog larger than Odoo reads", () => {
    expect(() =>
      serializeCatalog({ releases: [install("1.0.0", `https://release.example/${"a".repeat(1024 * 1024)}`)] }),
    ).toThrow("larger than");
  });
});
