import { memoryFiles } from "../src/testing/memoryFiles";

// The phone's files as the tests drive them: the next pick answers the file a test planned, or a cancel.
const planned: ({ name: string; mimeType: string; content: string } | null)[] = [];

/** The person picks this file next; null cancels. */
export function nextDocument(file: { name: string; mimeType: string; content: string } | null) {
  planned.push(file);
}

export const getDocumentAsync = jest.fn(async () => {
  const file = planned.shift();
  if (!file) {
    return { canceled: true, assets: null };
  }
  const uri = `file:///cache/DocumentPicker/${file.name}`;
  memoryFiles.set(uri, file.content);
  return { canceled: false, assets: [{ uri, name: file.name, mimeType: file.mimeType }] };
});
