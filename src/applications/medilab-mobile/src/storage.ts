import { randomUUID } from "expo-crypto";
import * as SecureStore from "expo-secure-store";

// What the app keeps on the phone, all in its secure storage. The password is never kept.
const KEYS = {
  serverUrl: "medilab.server_url",
  language: "medilab.language",
  installationId: "medilab.installation_id",
  deviceKey: "medilab.device_key",
} as const;

export type Stored = keyof typeof KEYS;

export function read(name: Stored): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS[name]);
}

export function write(name: Stored, value: string): Promise<void> {
  return SecureStore.setItemAsync(KEYS[name], value);
}

export function remove(name: Stored): Promise<void> {
  return SecureStore.deleteItemAsync(KEYS[name]);
}

/** The id this installation of the app signs in with, generated once and kept until the app is removed. */
export async function installationId(): Promise<string> {
  const kept = await read("installationId");
  if (kept) {
    return kept;
  }
  const generated = randomUUID();
  await write("installationId", generated);
  return generated;
}
