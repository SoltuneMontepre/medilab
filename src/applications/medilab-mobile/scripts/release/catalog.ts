// A release in the catalog Odoo answers phones from: a code update or a new install.
export type Release = {
  platform: "android" | "ios";
  kind: "code" | "install";
  runtime_version: string;
  version: string;
  pub_date: string;
} & ({ manifest: string; signature: string } | { url: string; sha256: string });

export type Catalog = { releases: Release[] };

// The limits Odoo reads a catalog within, as for the Sync catalog.
export const MAX_BYTES = 1024 * 1024;
export const MAX_RELEASES = 1000;

// The catalog with the new releases added, refused when one is already published.
export function addReleases(catalog: Catalog, releases: Release[]): Catalog {
  for (const release of releases) {
    const published = catalog.releases.some(
      (other) =>
        other.platform === release.platform && other.kind === release.kind && other.version === release.version,
    );
    if (published) {
      throw new Error(`The catalog already has the ${release.platform} ${release.kind} release ${release.version}.`);
    }
  }
  return { releases: [...catalog.releases, ...releases] };
}

// The catalog's text, refused when Odoo would refuse it for its size.
export function serializeCatalog(catalog: Catalog): string {
  if (catalog.releases.length > MAX_RELEASES) {
    throw new Error(`The catalog has ${catalog.releases.length} releases, more than ${MAX_RELEASES}.`);
  }
  const text = `${JSON.stringify(catalog, null, 2)}\n`;
  if (Buffer.byteLength(text, "utf8") > MAX_BYTES) {
    throw new Error(`The catalog is larger than ${MAX_BYTES} bytes.`);
  }
  return text;
}
