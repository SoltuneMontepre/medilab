import { memoryStore } from "../src/testing/memoryStore";

export async function getItemAsync(key: string): Promise<string | null> {
  return memoryStore.get(key) ?? null;
}

export async function setItemAsync(key: string, value: string): Promise<void> {
  memoryStore.set(key, value);
}

export async function deleteItemAsync(key: string): Promise<void> {
  memoryStore.delete(key);
}
