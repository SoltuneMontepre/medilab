/** Địa chỉ MediLab mà link `medilab-sync://connect?server=…` (nút trong MediLab) mang theo; null với mọi
 * link khác, kể cả địa chỉ không phải http(s) hoặc có kèm tài khoản. */
export function connectServer(link: string): string | null {
  let url: URL;
  let server: URL;
  try {
    url = new URL(link);
    server = new URL(url.searchParams.get("server") ?? "");
  } catch {
    return null;
  }
  if (url.protocol !== "medilab-sync:" || url.host !== "connect") {
    return null;
  }
  if (!["http:", "https:"].includes(server.protocol) || server.username || server.password) {
    return null;
  }
  let path = server.pathname;
  while (path.endsWith("/")) {
    path = path.slice(0, -1);
  }
  return server.origin + path;
}
