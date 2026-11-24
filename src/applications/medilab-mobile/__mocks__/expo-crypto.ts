let next = 0;

export function randomUUID(): string {
  next += 1;
  return `00000000-0000-4000-8000-${String(next).padStart(12, "0")}`;
}

export enum CryptoDigestAlgorithm {
  SHA256 = "SHA-256",
}

export async function digest(_algorithm: CryptoDigestAlgorithm, data: Uint8Array<ArrayBuffer>): Promise<ArrayBuffer> {
  return globalThis.crypto.subtle.digest("SHA-256", data);
}
