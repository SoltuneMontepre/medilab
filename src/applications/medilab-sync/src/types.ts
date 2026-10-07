/** Một rule đặt tên/lọc tệp áp cho một folder, cấu hình trong Odoo. */
export type SyncRule = {
  kind: string;
  pattern: string;
  recursive: boolean;
  enabled: boolean;
};

/** Một folder đã đăng ký đồng bộ cục bộ, kèm ngữ cảnh mẫu LIMS và trạng thái truy cập. */
export type FolderRow = {
  id: number;
  local_path: string;
  remote_id: number | null;
  logical_root: string;
  enabled: boolean;
  recursive: boolean;
  sample_name?: string | null;
  sample_code?: string | null;
  category?: string | null;
  workflow_status?: string | null;
  instrument_label?: string | null;
  access_state?: string;
};

/** Một job đồng bộ (tải lên hoặc tải xuống) và tiến độ hiện tại của nó. */
export type JobRow = {
  id: number;
  folder_id: number;
  file_id: number;
  relative_path: string;
  operation: string;
  status: string;
  attempt_count: number;
  last_error: string | null;
  bytes_total: number;
  bytes_done: number;
  remote_file_id: number | null;
  remote_version_id: number | null;
  target_version_number?: number | null;
};

/** Delta tiến độ truyền dữ liệu của một job đồng bộ (upload hoặc download). */
export type ProgressDeltaDto = {
  jobId: number;
  done: number;
  total: number;
};

/** Sự kiện báo danh sách tệp cục bộ/server có thay đổi ngữ nghĩa, kèm revision tăng dần. */
export type FilesChangedDto = {
  revision: number;
};

/** Ánh xạ cục bộ giữa một tệp đã biết trên server và đường dẫn tương đối của nó trong một folder. */
export type RemoteFileRow = {
  id: number;
  folder_id: number;
  relative_path: string;
  remote_file_id: number | null;
  remote_version_id: number | null;
  last_synced_hash?: string | null;
  suppress_hash?: string | null;
  status: string;
};

/** Người hoặc thiết bị đứng sau một hành động (tạo version, ...). */
export type VersionActor = {
  id: number;
  name: string;
};

/** Một version cụ thể của một tệp: hash nội dung, người/thiết bị tạo, có phải bản chuẩn hay
 * không, và có phục hồi được không. */
export type FileVersion = {
  id: number;
  file_id: number;
  version_number: number;
  size: number;
  content_hash: string;
  checksum_algorithm: string;
  source: string;
  created_at: string | null;
  created_by: VersionActor | null;
  device: VersionActor | null;
  is_canonical: boolean;
  parent_version_id: number | null;
  parent_version_number?: number | null;
  restored_from_version_id: number | null;
  restored_from_version_number?: number | null;
  object_available: boolean | null;
  can_restore: boolean;
  current_version_id?: number | null;
};

/** Một trang lịch sử version của một tệp. */
export type FileVersionList = {
  file_id: number;
  total: number;
  limit: number;
  offset: number;
  items: FileVersion[];
};

/** Snapshot trạng thái đồng bộ hiện tại: phiên đăng nhập, số job theo loại, folder và job hiện có. */
export type StatusDto = {
  paused: boolean;
  degraded: boolean;
  logged_in: boolean;
  session_expired: boolean;
  /** Trạng thái xác thực chi tiết. `credential_store_locked` = kho mật khẩu của OS đang khóa, KHÔNG
   * phải hết phiên. Vắng mặt (backend cũ) thì suy ra từ `logged_in`/`session_expired`. */
  auth_state?: "authenticated" | "missing_credentials" | "session_expired" | "credential_store_locked";
  user_name: string | null;
  odoo_url: string;
  pending: number;
  uploading: number;
  downloading: number;
  failed: number;
  conflict: number;
  completed: number;
  folders: FolderRow[];
  jobs: JobRow[];
};

/** Cấu hình ứng dụng đã lưu (URL Odoo, autostart, debounce/reconcile, ngôn ngữ, trạng thái tạm
 * dừng). */
export type AppSettings = {
  odoo_url: string;
  autostart: boolean;
  debounce_ms: number;
  reconcile_secs: number;
  change_poll_secs?: number;
  paused: boolean;
  locale?: string;
  /** Setting ẩn (không có trên form): số upload song song, áp dụng khi app khởi động. */
  upload_concurrency?: number;
  /** Setting ẩn: số download song song, áp dụng khi app khởi động. */
  download_concurrency?: number;
  /** Setting ẩn: số part của một tệp được PUT cùng lúc. */
  part_concurrency?: number;
};

/** Danh tính người dùng hiện cho ONLYOFFICE Document Server. */
export type OfficeUser = {
  id: string;
  name: string;
};

/** Toàn bộ cấu hình JS cần truyền cho ONLYOFFICE API để mở editor. */
export type OfficeEditorConfig = {
  documentType: string;
  width?: string;
  height?: string;
  document: {
    fileType: string;
    key: string;
    title: string;
    url: string;
    permissions: {
      edit: boolean;
      download: boolean;
      print: boolean;
      comment?: boolean;
    };
  };
  editorConfig: {
    mode: string;
    lang: string;
    type?: string;
    callbackUrl: string;
    user: OfficeUser;
    customization?: {
      autosave?: boolean;
      forcesave?: boolean;
      /** Theme giao diện editor do server chọn (hiện là theme sáng, khớp app). */
      uiTheme?: string;
      [key: string]: unknown;
    };
  };
  token: string;
};

/** Phiên chỉnh sửa ONLYOFFICE cho một tệp: id phiên, version gốc, và cấu hình để nhúng editor. */
export type OfficeSession = {
  session_id: number;
  file_id: number;
  base_version_id: number;
  document_key: string;
  created: boolean;
  state: string;
  document_server_url: string;
  document_type: string;
  file_type: string;
  config: OfficeEditorConfig;
};


/** Danh tính tối thiểu của một user do server trả về: chỉ id, tên và login (để phân biệt trùng tên). */
export type MemberUser = {
  id: number;
  name: string;
  login?: string | null;
};

/** Một thành viên của folder. `role` là key lưu (`owner` / `upload` = thành viên đọc + ghi).
 * `effective_access=false`: là thành viên nhưng chưa thấy mẫu đã map trong LIMS. */
export type FolderMember = {
  id: number;
  user: MemberUser;
  role: string;
  effective_access: boolean;
};

/** Thông tin chia sẻ của một folder. Thành viên thường chỉ nhận dòng của chính mình trong
 * `members`; `can_manage_members` chỉ để ẩn/hiện nút, server mới là nơi quyết định quyền. */
export type FolderMembers = {
  folder_id: number;
  owner: MemberUser;
  my_role: string;
  can_manage_members: boolean;
  mapped: boolean;
  members: FolderMember[];
};

/** Một folder trên server người khác chia sẻ cho mình mà máy này chưa gắn với thư mục cục bộ nào. */
export type SharedFolder = {
  id: number;
  name: string;
  logical_root: string;
  owner_name?: string | null;
  my_role?: string | null;
  sample_name?: string | null;
  sample_code?: string | null;
  category?: string | null;
};

/** Các folder trên server mà máy này chưa gắn: `shared` = được người khác chia sẻ, `owned` = của
 * chính mình (ví dụ sau khi "Ngừng đồng bộ" trên máy này). */
export type UnboundFolders = {
  shared: SharedFolder[];
  owned: SharedFolder[];
};
