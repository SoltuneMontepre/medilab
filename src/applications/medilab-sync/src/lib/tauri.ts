import { getVersion } from "@tauri-apps/api/app";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import packageJson from "../../package.json";
import { profiledInvoke, profileStatusEventHandler } from "./ipcProfiler";
import type {
  AppSettings,
  FileVersion,
  FileVersionList,
  FilesChangedDto,
  FolderMembers,
  MemberUser,
  OfficeSession,
  ProgressDeltaDto,
  RemoteFileRow,
  StatusDto,
  SyncRule,
  UnboundFolders,
} from "../types";

/** Payload sự kiện kéo-thả file gốc của Tauri webview. */
type DragDropPayload =
  | { type: "enter"; paths: string[] }
  | { type: "over"; position?: unknown }
  | { type: "drop"; paths: string[] }
  | { type: "leave" }
  | { type: "cancel" };

/** Đăng nhập Odoo và trả về trạng thái đồng bộ mới nhất. */
export async function login(odoo_url: string, login: string, password: string) {
  return profiledInvoke<StatusDto>("login", { args: { odoo_url, login, password } });
}

/** Đăng xuất khỏi tài khoản hiện tại. */
export async function logout() {
  return profiledInvoke<StatusDto>("logout");
}

/** Mở dialog chọn thư mục để đăng ký đồng bộ. */
export async function chooseSyncFolder() {
  return profiledInvoke<string | null>("choose_sync_folder");
}

/** Chuẩn hóa đường dẫn của một lượt kéo-thả folder. */
export async function resolveDroppedSyncFolder(paths: string[]) {
  return profiledInvoke<string>("resolve_dropped_sync_folder", { paths });
}

/** Lắng nghe sự kiện kéo-thả gốc của webview, gọi đúng handler theo giai đoạn (enter/leave/drop). */
export async function onNativeFolderDrop(handlers: {
  onEnter: () => void;
  onLeave: () => void;
  onDrop: (paths: string[]) => void;
}): Promise<UnlistenFn> {
  return getCurrentWebview().onDragDropEvent((event) => {
    const payload = event.payload as DragDropPayload;
    switch (payload.type) {
      case "enter":
      case "over":
        handlers.onEnter();
        break;
      case "leave":
      case "cancel":
        handlers.onLeave();
        break;
      case "drop":
        handlers.onLeave();
        handlers.onDrop(payload.paths);
        break;
    }
  });
}

/** Đăng ký một thư mục cục bộ để đồng bộ. */
export async function registerSyncFolder(payload: {
  local_path: string;
  logical_root: string;
  recursive: boolean;
  rules: SyncRule[];
}) {
  return profiledInvoke<StatusDto>("register_sync_folder", { args: payload });
}

/** Hủy đăng ký một thư mục đồng bộ. */
export async function unregisterSyncFolder(folderId: number) {
  return profiledInvoke<StatusDto>("unregister_sync_folder", { folderId });
}

/** Bỏ tạm dừng và đối soát lại toàn bộ ngay. */
export async function startSync() {
  return profiledInvoke<StatusDto>("start_sync");
}

/** Tạm dừng vòng lặp đồng bộ. */
export async function pauseSync() {
  return profiledInvoke<StatusDto>("pause_sync");
}

/** Xác nhận lại phiên đăng nhập lúc khởi động app. */
export async function restoreSession() {
  return profiledInvoke<StatusDto>("restore_session");
}

/** Thông tin chia sẻ của một folder trên server: chủ sở hữu, tư cách của mình, thành viên. */
export async function listFolderMembers(remoteId: number) {
  return profiledInvoke<FolderMembers>("list_folder_members", { remoteId });
}

/** Thêm một thành viên (vai trò do server gán) và trả về danh sách mới. */
export async function addFolderMember(remoteId: number, userId: number) {
  return profiledInvoke<FolderMembers>("add_folder_member", { remoteId, userId });
}

/** Gỡ một thành viên và trả về danh sách mới. */
export async function removeFolderMember(remoteId: number, memberId: number) {
  return profiledInvoke<FolderMembers>("remove_folder_member", { remoteId, memberId });
}

/** Tìm user có thể thêm vào folder này (server yêu cầu ≥2 ký tự, trả tối đa 10). */
export async function searchMemberCandidates(remoteId: number, query: string) {
  return profiledInvoke<MemberUser[]>("search_member_candidates", { remoteId, query });
}

/** Folder trên server mà máy này chưa gắn: được chia sẻ cho mình, và của chính mình. */
export async function listSharedFolders() {
  return profiledInvoke<UnboundFolders>("list_shared_folders");
}

/** Gắn một folder được chia sẻ (theo ID trên server) vào một thư mục cục bộ; không tạo folder mới. */
export async function bindSharedFolder(payload: {
  remote_id: number;
  local_path: string;
  recursive: boolean;
}) {
  return profiledInvoke<StatusDto>("bind_shared_folder", { args: payload });
}

/** Đặt lại một job lỗi để thử lại. */
export async function retrySyncJob(jobId: number) {
  return profiledInvoke<StatusDto>("retry_sync_job", { jobId });
}

/** Đọc cấu hình ứng dụng đã lưu. */
export async function getSettings() {
  return profiledInvoke<AppSettings>("get_settings");
}

/** Lưu cấu hình ứng dụng mới. */
export async function saveSettings(settings: AppSettings) {
  return profiledInvoke<StatusDto>("save_settings", { settings });
}

/** Lắng nghe sự kiện đổi trạng thái đồng bộ từ backend. */
export async function onStatusChanged(handler: (status: StatusDto) => void): Promise<UnlistenFn> {
  const profiledHandler = profileStatusEventHandler(handler);
  return listen<StatusDto>("sync-status-changed", (event) => profiledHandler(event.payload));
}

/** Lắng nghe sự kiện phát hiện xung đột mới từ backend. */
export async function onConflictCreated(handler: (payload: unknown) => void): Promise<UnlistenFn> {
  return listen("conflict-created", (event) => handler(event.payload));
}

/** Lắng nghe sự kiện lỗi đồng bộ từ backend. */
export async function onSyncError(handler: (payload: unknown) => void): Promise<UnlistenFn> {
  return listen("sync-error", (event) => handler(event.payload));
}

/** Lắng nghe tiến độ tải lên (delta) cho từng job. */
export async function onUploadProgress(
  handler: (progress: ProgressDeltaDto) => void,
): Promise<UnlistenFn> {
  return listen<ProgressDeltaDto>("upload-progress", (event) => handler(event.payload));
}

/** Lắng nghe tiến độ tải xuống (delta) cho từng job. */
export async function onDownloadProgress(
  handler: (progress: ProgressDeltaDto) => void,
): Promise<UnlistenFn> {
  return listen<ProgressDeltaDto>("download-progress", (event) => handler(event.payload));
}

/** Lắng nghe sự kiện danh sách tệp thay đổi ngữ nghĩa từ backend. */
export async function onFilesChanged(
  handler: (payload: FilesChangedDto) => void,
): Promise<UnlistenFn> {
  return listen<FilesChangedDto>("sync-files-changed", (event) => handler(event.payload));
}

/** Liệt kê mọi tệp cục bộ đã có ánh xạ tới server. */
export async function listRemoteFiles() {
  return profiledInvoke<RemoteFileRow[]>("list_remote_files");
}

/** Đọc một trang lịch sử version của một tệp. */
export async function getFileVersions(fileId: number, limit = 20, offset = 0) {
  return profiledInvoke<FileVersionList>("get_file_versions", { fileId, limit, offset });
}

/** Đọc chi tiết một version cụ thể. */
export async function getFileVersionDetail(fileId: number, versionId: number) {
  return profiledInvoke<FileVersion>("get_file_version_detail", { fileId, versionId });
}

/** Yêu cầu server phục hồi một version cũ thành version hiện hành. */
export async function restoreFileVersion(fileId: number, versionId: number) {
  return profiledInvoke<FileVersion>("restore_file_version", { fileId, versionId });
}

/** Xung đột: giữ bản trên server. */
export async function acceptServerVersion(fileId: number) {
  return profiledInvoke<StatusDto>("accept_server_version", { fileId });
}

/** Xung đột: giữ bản cục bộ (bản conflict vẫn được lưu song song). */
export async function keepLocalConflict(fileId: number) {
  return profiledInvoke<StatusDto>("keep_local_conflict", { fileId });
}

/** Mở phiên chỉnh sửa ONLYOFFICE cho một tệp. */
export async function openOfficeEditor(fileId: number) {
  return profiledInvoke<OfficeSession>("open_office_editor", { fileId });
}

/** Thông tin bản cập nhật đang chờ. */
export type UpdateAvailable = {
  current_version: string;
  new_version: string;
  notes?: string;
  pub_date?: string;
};

/** Kiểm tra bản cập nhật mới; `null` nếu đã là bản mới nhất hoặc lượt kiểm thất bại. */
export async function checkUpdate(): Promise<UpdateAvailable | null> {
  return profiledInvoke<UpdateAvailable | null>("check_update");
}

/** Tải và cài đặt bản cập nhật đang chờ. */
export async function downloadAndInstallUpdate(): Promise<void> {
  return profiledInvoke<void>("download_and_install_update");
}

/** Bỏ qua nhắc cập nhật cho phiên chạy hiện tại. */
export function dismissUpdateSession(): void {
  void profiledInvoke<void>("dismiss_update_session");
}

/** Lắng nghe sự kiện có bản cập nhật mới từ backend. */
export async function onUpdateAvailable(
  handler: (info: UpdateAvailable) => void,
): Promise<UnlistenFn> {
  return listen<UpdateAvailable>("update-available", (event) => handler(event.payload));
}

/** Phiên bản mặc định lấy từ package.json phục vụ fallback khi chưa nạp được metadata từ runtime. */
export const DEFAULT_APP_VERSION = packageJson.version;

/** Đọc phiên bản ứng dụng hiện tại từ metadata Tauri (hoặc rơi về phiên bản từ package.json lúc chạy ngoài webview). */
export async function getAppVersion(): Promise<string> {
  try {
    const version = await getVersion();
    if (version) {
      return version;
    }
  } catch {
    // getVersion là best-effort khi chạy trong môi trường test hoặc trình duyệt không có runtime Tauri
  }
  return DEFAULT_APP_VERSION;
}

