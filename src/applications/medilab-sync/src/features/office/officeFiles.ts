/** Office formats supported by the laboratory editor. */
export function isOfficeDocument(path: string): boolean {
  return /\.(docx|xlsx|pptx)$/i.test(path);
}

export function canEditOnline(path: string, category?: string | null): boolean {
  return isOfficeDocument(path) && (category == null || category === "working" || category === "result");
}
