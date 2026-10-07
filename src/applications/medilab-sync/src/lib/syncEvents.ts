import type { FolderRow, JobRow, ProgressDeltaDto, RemoteFileRow, StatusDto } from "../types";

/**
 * Cập nhật tiến độ của một job cụ thể trong StatusDto mà không tạo object mới cho
 * các job hay folder không bị ảnh hưởng, giữ nguyên reference identity.
 */
export function applyProgressDelta(status: StatusDto, delta: ProgressDeltaDto): StatusDto {
  const targetIndex = status.jobs.findIndex((job) => job.id === delta.jobId);
  if (targetIndex === -1) {
    return status;
  }

  const currentJob = status.jobs[targetIndex];
  if (currentJob.bytes_done === delta.done && currentJob.bytes_total === delta.total) {
    return status;
  }

  const updatedJob: JobRow = {
    ...currentJob,
    bytes_done: delta.done,
    bytes_total: delta.total,
  };

  const nextJobs = [...status.jobs];
  nextJobs[targetIndex] = updatedJob;

  return {
    ...status,
    jobs: nextJobs,
  };
}

/** Tùy chọn khởi tạo bộ điều phối làm mới danh sách tệp từ xa. */
export type RemoteFilesRefreshControllerOptions = {
  fetcher: () => Promise<RemoteFileRow[]>;
  onLoaded: (files: RemoteFileRow[]) => void;
  onError?: (error: unknown) => void;
};

/** Giao diện bộ điều phối làm mới danh sách tệp từ xa (latest-only, chống trùng lặp request). */
export type RemoteFilesRefreshController = {
  /** Yêu cầu làm mới danh sách tệp; gộp các lượt gọi liên tiếp và tuần tự hóa tối đa 1 request in-flight. */
  invalidate: (revision?: number) => Promise<void>;
  /** Hủy bỏ việc lắng nghe và dừng mọi lượt follow-up chưa chạy. */
  cancel: () => void;
  /** True nếu đang có một request fetch đang chạy. */
  isInFlight: () => boolean;
  /** True nếu có ít nhất một invalidation đang chờ chạy lượt kế tiếp. */
  isQueued: () => boolean;
};

/**
 * Tạo bộ điều phối làm mới danh sách tệp từ xa (latest-only):
 * - Đảm bảo chỉ có tối đa 1 request `listRemoteFiles` đang chạy trên đường truyền (in-flight).
 * - Nếu nhận thêm tín hiệu thay đổi trong lúc request đang chạy, sẽ đánh dấu và kích hoạt duy nhất
 *   1 lượt follow-up ngay sau khi lượt hiện tại kết thúc.
 * - Cho phép hủy bỏ (cancel) khi component unmount hoặc khi logout.
 */
export function createRemoteFilesRefreshController(
  options: RemoteFilesRefreshControllerOptions,
): RemoteFilesRefreshController {
  let inFlight = false;
  let queued = false;
  let cancelled = false;

  let currentWaiters: Array<() => void> = [];
  let queuedWaiters: Array<() => void> = [];

  function notifyWaiters(waiters: Array<() => void>): void {
    for (const resolve of waiters) {
      resolve();
    }
  }

  async function executeFetch(): Promise<void> {
    inFlight = true;
    try {
      const result = await options.fetcher();
      if (!cancelled) {
        options.onLoaded(result);
      }
    } catch (err) {
      if (!cancelled) {
        options.onError?.(err);
      }
    } finally {
      inFlight = false;
      const finishedWaiters = currentWaiters;
      currentWaiters = [];
      notifyWaiters(finishedWaiters);

      if (!cancelled && queued) {
        queued = false;
        currentWaiters = queuedWaiters;
        queuedWaiters = [];
        void executeFetch();
      }
    }
  }

  return {
    invalidate(_revision?: number): Promise<void> {
      if (cancelled) {
        return Promise.resolve();
      }

      if (inFlight) {
        queued = true;
        return new Promise<void>((resolve) => {
          queuedWaiters.push(resolve);
        });
      }

      return new Promise<void>((resolve) => {
        currentWaiters.push(resolve);
        void executeFetch();
      });
    },
    cancel(): void {
      cancelled = true;
      queued = false;
      inFlight = false;
      const allWaiters = [...currentWaiters, ...queuedWaiters];
      currentWaiters = [];
      queuedWaiters = [];
      notifyWaiters(allWaiters);
    },
    isInFlight(): boolean {
      return inFlight;
    },
    isQueued(): boolean {
      return queued;
    },
  };
}

/**
 * Kiểm tra tính tương đồng giá trị giữa hai đối tượng FolderRow.
 */
export function isFolderEqual(a: FolderRow, b: FolderRow): boolean {
  return (
    a.id === b.id &&
    a.local_path === b.local_path &&
    a.remote_id === b.remote_id &&
    a.logical_root === b.logical_root &&
    a.enabled === b.enabled &&
    a.recursive === b.recursive &&
    a.sample_name === b.sample_name &&
    a.sample_code === b.sample_code &&
    a.category === b.category &&
    a.workflow_status === b.workflow_status &&
    a.instrument_label === b.instrument_label &&
    a.access_state === b.access_state
  );
}

/**
 * Kiểm tra tính tương đồng giá trị giữa hai đối tượng JobRow.
 */
export function isJobEqual(a: JobRow, b: JobRow): boolean {
  return (
    a.id === b.id &&
    a.folder_id === b.folder_id &&
    a.file_id === b.file_id &&
    a.relative_path === b.relative_path &&
    a.operation === b.operation &&
    a.status === b.status &&
    a.attempt_count === b.attempt_count &&
    a.last_error === b.last_error &&
    a.bytes_total === b.bytes_total &&
    a.bytes_done === b.bytes_done &&
    a.remote_file_id === b.remote_file_id &&
    a.remote_version_id === b.remote_version_id &&
    a.target_version_number === b.target_version_number
  );
}

/**
 * Kiểm tra tính tương đồng giá trị giữa hai đối tượng RemoteFileRow.
 */
export function isRemoteFileEqual(a: RemoteFileRow, b: RemoteFileRow): boolean {
  return (
    a.id === b.id &&
    a.folder_id === b.folder_id &&
    a.relative_path === b.relative_path &&
    a.remote_file_id === b.remote_file_id &&
    a.remote_version_id === b.remote_version_id &&
    a.last_synced_hash === b.last_synced_hash &&
    a.suppress_hash === b.suppress_hash &&
    a.status === b.status
  );
}

/**
 * Hợp nhất mảng các FolderRow có bảo toàn tham chiếu:
 * - Tái sử dụng tham chiếu đối tượng FolderRow nếu các trường không đổi.
 * - Tái sử dụng toàn bộ mảng prev nếu mọi phần tử và thứ tự không thay đổi.
 */
export function mergeFolders(prev: FolderRow[], next: FolderRow[]): FolderRow[] {
  if (prev === next) {
    return prev;
  }
  const prevMap = new Map<number, FolderRow>();
  for (const folder of prev) {
    prevMap.set(folder.id, folder);
  }

  let allSame = prev.length === next.length;
  const merged: FolderRow[] = [];

  for (let i = 0; i < next.length; i++) {
    const nextFolder = next[i];
    const prevFolder = prevMap.get(nextFolder.id);
    if (prevFolder && isFolderEqual(prevFolder, nextFolder)) {
      merged.push(prevFolder);
      if (prev[i] !== prevFolder) {
        allSame = false;
      }
    } else {
      merged.push(nextFolder);
      allSame = false;
    }
  }

  return allSame ? prev : merged;
}

/**
 * Hợp nhất mảng các JobRow có bảo toàn tham chiếu:
 * - Tái sử dụng tham chiếu đối tượng JobRow nếu các trường không đổi.
 * - Tái sử dụng toàn bộ mảng prev nếu mọi phần tử và thứ tự không thay đổi.
 */
export function mergeJobs(prev: JobRow[], next: JobRow[]): JobRow[] {
  if (prev === next) {
    return prev;
  }
  const prevMap = new Map<number, JobRow>();
  for (const job of prev) {
    prevMap.set(job.id, job);
  }

  let allSame = prev.length === next.length;
  const merged: JobRow[] = [];

  for (let i = 0; i < next.length; i++) {
    const nextJob = next[i];
    const prevJob = prevMap.get(nextJob.id);
    if (prevJob && isJobEqual(prevJob, nextJob)) {
      merged.push(prevJob);
      if (prev[i] !== prevJob) {
        allSame = false;
      }
    } else {
      merged.push(nextJob);
      allSame = false;
    }
  }

  return allSame ? prev : merged;
}

/**
 * Hợp nhất mảng RemoteFileRow có bảo toàn tham chiếu:
 * - Tái sử dụng toàn bộ mảng prev nếu danh sách tệp không đổi về nội dung.
 * - Tái sử dụng tham chiếu từng hàng tệp cũ nếu tệp đó không thay đổi.
 */
export function mergeRemoteFiles(prev: RemoteFileRow[], next: RemoteFileRow[]): RemoteFileRow[] {
  if (prev === next) {
    return prev;
  }
  const prevMap = new Map<number, RemoteFileRow>();
  for (const file of prev) {
    prevMap.set(file.id, file);
  }

  let allSame = prev.length === next.length;
  const merged: RemoteFileRow[] = [];

  for (let i = 0; i < next.length; i++) {
    const nextFile = next[i];
    const prevFile = prevMap.get(nextFile.id);
    if (prevFile && isRemoteFileEqual(prevFile, nextFile)) {
      merged.push(prevFile);
      if (prev[i] !== prevFile) {
        allSame = false;
      }
    } else {
      merged.push(nextFile);
      allSame = false;
    }
  }

  return allSame ? prev : merged;
}

/**
 * Hợp nhất snapshot StatusDto mới với state hiện tại theo cấu trúc (structural merging):
 * - Tái sử dụng tham chiếu FolderRow và mảng folders khi không đổi.
 * - Tái sử dụng tham chiếu JobRow và mảng jobs khi không đổi.
 * - Nếu tất cả các trường nguyên thủy và mảng con đều không đổi, trả về chính xác prev (prev === next).
 */
export function mergeStatusSnapshot(prev: StatusDto, next: StatusDto): StatusDto {
  if (prev === next) {
    return prev;
  }

  const mergedFolders = mergeFolders(prev.folders, next.folders);
  const mergedJobs = mergeJobs(prev.jobs, next.jobs);

  const isPrimitivesEqual =
    prev.paused === next.paused &&
    prev.degraded === next.degraded &&
    prev.logged_in === next.logged_in &&
    prev.session_expired === next.session_expired &&
    prev.auth_state === next.auth_state &&
    prev.user_name === next.user_name &&
    prev.odoo_url === next.odoo_url &&
    prev.pending === next.pending &&
    prev.uploading === next.uploading &&
    prev.downloading === next.downloading &&
    prev.failed === next.failed &&
    prev.conflict === next.conflict &&
    prev.completed === next.completed;

  if (isPrimitivesEqual && mergedFolders === prev.folders && mergedJobs === prev.jobs) {
    return prev;
  }

  return {
    ...next,
    folders: mergedFolders,
    jobs: mergedJobs,
  };
}

