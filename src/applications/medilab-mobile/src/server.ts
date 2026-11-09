import type { MessageKey } from "./i18n";

/** The address as the app keeps it: without spaces around it or slashes at its end. */
export function normalizeServerUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

/** Why the address cannot be MediLab's, or null when it can: a production build reaches MediLab only over HTTPS. */
export function serverUrlError(url: string, production: boolean = !__DEV__): MessageKey | null {
  const schemes = production ? ["https:"] : ["http:", "https:"];
  let parsed: URL;
  try {
    parsed = new URL(normalizeServerUrl(url));
  } catch {
    return production ? "server.invalid" : "server.invalidDevelopment";
  }
  if (!schemes.includes(parsed.protocol) || !parsed.hostname) {
    return production ? "server.invalid" : "server.invalidDevelopment";
  }
  return null;
}
