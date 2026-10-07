import { invoke, type InvokeArgs } from "@tauri-apps/api/core";

/** Danh sách command IPC tĩnh được frontend gọi; không nhận tên tạo từ dữ liệu người dùng. */
export type IpcCommandName =
  | "login"
  | "logout"
  | "choose_sync_folder"
  | "resolve_dropped_sync_folder"
  | "register_sync_folder"
  | "unregister_sync_folder"
  | "start_sync"
  | "pause_sync"
  | "restore_session"
  | "list_folder_members"
  | "add_folder_member"
  | "remove_folder_member"
  | "search_member_candidates"
  | "list_shared_folders"
  | "bind_shared_folder"
  | "retry_sync_job"
  | "get_settings"
  | "save_settings"
  | "list_remote_files"
  | "get_file_versions"
  | "get_file_version_detail"
  | "restore_file_version"
  | "accept_server_version"
  | "keep_local_conflict"
  | "open_office_editor"
  | "check_update"
  | "download_and_install_update"
  | "dismiss_update_session";

/** Sự kiện duy nhất được đo cadence trong Step 2. */
type ProfiledEventName = "sync-status-changed";

/** Tên operation an toàn gồm command IPC tĩnh hoặc tên event tĩnh. */
type ProfiledOperationName = IpcCommandName | `event:${ProfiledEventName}`;

/** Bản ghi hiệu năng không chứa argument, response, credential, path, URL hay event payload. */
export type SafeIpcPerformanceMetric = Readonly<{
  command: ProfiledOperationName;
  durationMs: number;
  outcome: "success" | "error";
  concurrentCalls: number;
  cadenceMs?: number | null;
}>;

/** Phần Performance API tối thiểu dùng để đánh dấu và đo một operation. */
type PerformanceApi = Readonly<{
  now: () => number;
  mark: (name: string) => void;
  measure: (name: string, startMark: string, endMark: string) => void;
  clearMarks: (name?: string) => void;
}>;

/** Chữ ký invoke có thể tiêm fake trong test mà vẫn giữ generic return type. */
type InvokeFunction = <T>(command: IpcCommandName, args?: InvokeArgs) => Promise<T>;

/** Chữ ký wrapper IPC giữ nguyên kiểu kết quả của command. */
export type ProfiledInvoke = <T>(command: IpcCommandName, args?: InvokeArgs) => Promise<T>;

/** Dependency của wrapper IPC; chỉ record nhận bản ghi đã được giới hạn field an toàn. */
type ProfiledInvokeOptions = Readonly<{
  enabled: boolean;
  performanceApi: PerformanceApi;
  invoker: InvokeFunction;
  record: (metric: SafeIpcPerformanceMetric) => void;
}>;

/** Dependency của event wrapper; payload chỉ được chuyển thẳng vào handler. */
type ProfiledEventHandlerOptions<T> = Readonly<{
  enabled: boolean;
  eventName: ProfiledEventName;
  performanceApi: PerformanceApi;
  handler: (payload: T) => void;
  record: (metric: SafeIpcPerformanceMetric) => void;
}>;

/** Kết thúc một Performance measure và dọn mark tạm để tránh tăng bộ nhớ theo số lượt gọi. */
function finishMeasurement(
  performanceApi: PerformanceApi,
  measureName: string,
  startMark: string,
  endMark: string,
): void {
  performanceApi.mark(endMark);
  performanceApi.measure(measureName, startMark, endMark);
  performanceApi.clearMarks(startMark);
  performanceApi.clearMarks(endMark);
}

/** Phát duy nhất metadata an toàn ra debug console trong development mode. */
function recordToDebugConsole(metric: SafeIpcPerformanceMetric): void {
  console.debug("[IPC Profiler]", metric);
}

/** Gọi Tauri invoke thật; helper này giúp factory nhận dependency generic có kiểu rõ ràng. */
async function invokeTauri<T>(command: IpcCommandName, args?: InvokeArgs): Promise<T> {
  return invoke<T>(command, args);
}

/** Tạo wrapper invoke có đo latency; khi disable sẽ chuyển thẳng tới invoker, không gọi Performance API. */
export function createProfiledInvoke({
  enabled,
  performanceApi,
  invoker,
  record,
}: ProfiledInvokeOptions): ProfiledInvoke {
  let activeInvocations = 0;
  let invocationSequence = 0;

  /** Gọi một command và chỉ record metadata tĩnh cùng timing của lượt gọi đó. */
  async function invokeWithProfiling<T>(command: IpcCommandName, args?: InvokeArgs): Promise<T> {
    if (!enabled) {
      return invoker<T>(command, args);
    }

    invocationSequence += 1;
    const measureName = `ipc:${command}:${invocationSequence}`;
    const startMark = `${measureName}:start`;
    const endMark = `${measureName}:end`;
    let startedAt: number;

    try {
      performanceApi.mark(startMark);
      startedAt = performanceApi.now();
    } catch {
      // Instrumentation là best-effort và không được phép chặn IPC thật.
      return invoker<T>(command, args);
    }

    activeInvocations += 1;
    const concurrentCalls = activeInvocations;
    let outcome: "success" | "error" = "success";

    try {
      return await invoker<T>(command, args);
    } catch (error) {
      outcome = "error";
      throw error;
    } finally {
      try {
        const durationMs = performanceApi.now() - startedAt;
        finishMeasurement(performanceApi, measureName, startMark, endMark);
        record({ command, durationMs, outcome, concurrentCalls });
      } catch {
        // Lỗi profiler không được thay đổi success/error của IPC gốc.
      } finally {
        activeInvocations -= 1;
      }
    }
  }

  return invokeWithProfiling;
}

/** Tạo handler đo cadence và thời gian xử lý event mà không record payload. */
export function createProfiledEventHandler<T>({
  enabled,
  eventName,
  performanceApi,
  handler,
  record,
}: ProfiledEventHandlerOptions<T>): (payload: T) => void {
  let activeHandlers = 0;
  let eventSequence = 0;
  let previousEventStartedAt: number | null = null;

  /** Chuyển payload nguyên vẹn vào handler và chỉ record timing của event. */
  function handleWithProfiling(payload: T): void {
    if (!enabled) {
      handler(payload);
      return;
    }

    eventSequence += 1;
    const command: ProfiledOperationName = `event:${eventName}`;
    const measureName = `ipc:${command}:${eventSequence}`;
    const startMark = `${measureName}:start`;
    const endMark = `${measureName}:end`;
    let startedAt: number;

    try {
      performanceApi.mark(startMark);
      startedAt = performanceApi.now();
    } catch {
      // Instrumentation là best-effort và không được phép chặn event handler thật.
      handler(payload);
      return;
    }

    const cadenceMs = previousEventStartedAt === null ? null : startedAt - previousEventStartedAt;
    previousEventStartedAt = startedAt;
    activeHandlers += 1;
    const concurrentCalls = activeHandlers;
    let outcome: "success" | "error" = "success";

    try {
      handler(payload);
    } catch (error) {
      outcome = "error";
      throw error;
    } finally {
      try {
        const durationMs = performanceApi.now() - startedAt;
        finishMeasurement(performanceApi, measureName, startMark, endMark);
        record({ command, durationMs, outcome, concurrentCalls, cadenceMs });
      } catch {
        // Lỗi profiler không được thay đổi success/error của event handler gốc.
      } finally {
        activeHandlers -= 1;
      }
    }
  }

  return handleWithProfiling;
}

const defaultProfiledInvoke: ProfiledInvoke = import.meta.env.DEV
  ? createProfiledInvoke({
      enabled: true,
      performanceApi: performance,
      invoker: invokeTauri,
      record: recordToDebugConsole,
    })
  : invokeTauri;

/** Wrapper dùng chung cho mọi typed IPC call của frontend. */
export function profiledInvoke<T>(command: IpcCommandName, args?: InvokeArgs): Promise<T> {
  return defaultProfiledInvoke<T>(command, args);
}

/** Bọc listener `sync-status-changed` bằng profiler development-only. */
export function profileStatusEventHandler<T>(handler: (payload: T) => void): (payload: T) => void {
  if (!import.meta.env.DEV) {
    return handler;
  }

  return createProfiledEventHandler({
    enabled: true,
    eventName: "sync-status-changed",
    performanceApi: performance,
    handler,
    record: recordToDebugConsole,
  });
}
