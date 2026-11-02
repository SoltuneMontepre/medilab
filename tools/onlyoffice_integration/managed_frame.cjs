// Native editor assets of the pinned server can include its canonical version prefix.
function isDocumentEditorFrame(value, expectedOrigin) {
  try {
    const url = new URL(value);
    if (url.origin !== expectedOrigin || url.username || url.password) return false;
    const suffix = "/web-apps/apps/documenteditor/main/index.html";
    if (!url.pathname.endsWith(suffix)) return false;
    const prefix = url.pathname.slice(0, -suffix.length);
    return prefix === "" || /^\/\d+\.\d+\.\d+-[a-f0-9]{32}$/.test(prefix);
  } catch { return false; }
}
module.exports = { isDocumentEditorFrame };
