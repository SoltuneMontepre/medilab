import type { FolderRow, JobRow, RemoteFileRow, StatusDto } from "../types";

/**
 * Dựng fixture StatusDto mẫu với các mảng folder và job phục vụ kiểm thử phân lập render và bảo toàn identity.
 * Hỗ trợ truyền `overrides` để tùy biến các trường khi cần thiết lập kịch bản kiểm thử riêng.
 */
export function createStatusFixture(overrides?: Partial<StatusDto>): StatusDto {
  const folders: FolderRow[] = [
    {
      id: 1,
      local_path: "/data/folder1",
      remote_id: 10,
      logical_root: "ROOT1",
      enabled: true,
      recursive: true,
      access_state: "allowed",
    },
    {
      id: 2,
      local_path: "/data/folder2",
      remote_id: 20,
      logical_root: "ROOT2",
      enabled: true,
      recursive: true,
      access_state: "denied",
    },
  ];

  const jobs: JobRow[] = [
    {
      id: 101,
      folder_id: 1,
      file_id: 201,
      relative_path: "file1.txt",
      operation: "upload",
      status: "uploading",
      attempt_count: 0,
      last_error: null,
      bytes_total: 1000,
      bytes_done: 200,
      remote_file_id: null,
      remote_version_id: null,
    },
    {
      id: 102,
      folder_id: 2,
      file_id: 202,
      relative_path: "file2.txt",
      operation: "upload",
      status: "pending",
      attempt_count: 0,
      last_error: null,
      bytes_total: 2000,
      bytes_done: 0,
      remote_file_id: null,
      remote_version_id: null,
    },
  ];

  return {
    paused: false,
    degraded: false,
    logged_in: true,
    session_expired: false,
    user_name: "tester",
    odoo_url: "http://localhost:8069",
    pending: 1,
    uploading: 1,
    downloading: 0,
    failed: 0,
    conflict: 0,
    completed: 0,
    folders,
    jobs,
    ...overrides,
  };
}

/** Dựng danh sách tệp remote mẫu cho kiểm thử giao diện và đồng bộ. */
export function createRemoteFilesFixture(): RemoteFileRow[] {
  return [
    {
      id: 1,
      folder_id: 1,
      relative_path: "file1.txt",
      remote_file_id: 10,
      remote_version_id: 20,
      status: "synced",
    },
    {
      id: 2,
      folder_id: 1,
      relative_path: "file2.txt",
      remote_file_id: 11,
      remote_version_id: 21,
      status: "conflict",
    },
  ];
}
