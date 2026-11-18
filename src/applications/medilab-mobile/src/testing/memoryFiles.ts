// The phone's files as the tests keep them, in memory: each file's text by its address.
export const memoryFiles = new Map<string, string>();

// What each address downloads in the tests.
export const memoryDownloads = new Map<string, string>();
