type OpenCommand = (command: "open_office_editor", args: { fileId: number }) => Promise<void>;

export async function openEditorInBrowser(fileId: number, invoke: OpenCommand): Promise<void> {
  if (!Number.isSafeInteger(fileId) || fileId <= 0) {
    throw new Error("Invalid laboratory file ID");
  }
  await invoke("open_office_editor", { fileId });
}
