import { expect, test } from "bun:test";

type IpcProfilerModule = typeof import("./ipcProfiler");

/** Performance API giả ghi lại tên mark/measure và phát thời gian xác định cho từng bài test. */
function createFakePerformance(timestamps: number[]) {
  const markNames: string[] = [];
  const measurements: Array<{ name: string; startMark: string; endMark: string }> = [];
  let timestampIndex = 0;

  return {
    markNames,
    measurements,
    api: {
      /** Trả mốc thời gian tiếp theo do bài test cung cấp. */
      now(): number {
        const timestamp = timestamps[timestampIndex];
        timestampIndex += 1;
        if (timestamp === undefined) {
          throw new Error("Thiếu timestamp giả cho performance.now()");
        }
        return timestamp;
      },
      /** Ghi tên mark để kiểm tra không chứa dữ liệu nhạy cảm. */
      mark(name: string): void {
        markNames.push(name);
      },
      /** Ghi quan hệ measure để kiểm tra wrapper dùng đúng hai mark. */
      measure(name: string, startMark: string, endMark: string): void {
        measurements.push({ name, startMark, endMark });
      },
      /** Mô phỏng dọn mark; lịch sử gọi vẫn được giữ trong test fixture. */
      clearMarks(): void {},
      /** Mô phỏng dọn measure; lịch sử gọi vẫn được giữ trong test fixture. */
      clearMeasures(): void {},
    },
  };
}

/** Tạo bộ thu metric an toàn để bài test kiểm tra output mà không dùng mock framework. */
function createRecordCollector() {
  const records: unknown[] = [];

  /** Lưu một metric profiler vào danh sách theo đúng thứ tự phát. */
  function record(metric: unknown): void {
    records.push(metric);
  }

  return { records, record };
}

/** Tải module profiler nếu đã hiện thực; trả null để trạng thái RED là assertion rõ ràng. */
async function loadIpcProfiler(): Promise<IpcProfilerModule | null> {
  try {
    return await import("./ipcProfiler");
  } catch {
    return null;
  }
}

/** Bắt lỗi wrapper làm đổi kết quả hoặc không ghi latency thành công bằng Performance API. */
test("profiled invoke returns the result and records safe success timing", async () => {
  const ipcProfiler = await loadIpcProfiler();
  expect(ipcProfiler).not.toBeNull();
  if (!ipcProfiler) {
    return;
  }

  const fakePerformance = createFakePerformance([10, 26]);
  const { records, record } = createRecordCollector();

  /** Trả kết quả giả có kiểu generic giống Tauri invoke. */
  async function returnSettings<T>(): Promise<T> {
    return "settings-loaded" as T;
  }

  const profiledInvoke = ipcProfiler.createProfiledInvoke({
    enabled: true,
    performanceApi: fakePerformance.api,
    invoker: returnSettings,
    record,
  });

  const result = await profiledInvoke<string>("get_settings");

  expect(result).toBe("settings-loaded");
  expect(records).toEqual([
    {
      command: "get_settings",
      durationMs: 16,
      outcome: "success",
      concurrentCalls: 1,
    },
  ]);
  expect(fakePerformance.markNames).toHaveLength(2);
  expect(fakePerformance.measurements).toHaveLength(1);
});

/** Bắt lỗi wrapper nuốt exception hoặc ghi sai outcome khi Tauri invoke bị reject. */
test("profiled invoke preserves rejection and records an error outcome", async () => {
  const ipcProfiler = await loadIpcProfiler();
  expect(ipcProfiler).not.toBeNull();
  if (!ipcProfiler) {
    return;
  }

  const fakePerformance = createFakePerformance([50, 57.5]);
  const { records, record } = createRecordCollector();
  const failure = new Error("backend unavailable");

  /** Reject bằng đúng lỗi backend giả để kiểm tra wrapper không thay đổi exception. */
  function rejectInvoke<T>(): Promise<T> {
    return Promise.reject(failure);
  }

  const profiledInvoke = ipcProfiler.createProfiledInvoke({
    enabled: true,
    performanceApi: fakePerformance.api,
    invoker: rejectInvoke,
    record,
  });

  await expect(profiledInvoke("restore_session")).rejects.toBe(failure);
  expect(records).toEqual([
    {
      command: "restore_session",
      durationMs: 7.5,
      outcome: "error",
      concurrentCalls: 1,
    },
  ]);
});

/** Bắt lỗi production path vẫn gọi Performance API hoặc phát telemetry khi đã disable. */
test("profiled invoke bypasses all instrumentation when disabled", async () => {
  const ipcProfiler = await loadIpcProfiler();
  expect(ipcProfiler).not.toBeNull();
  if (!ipcProfiler) {
    return;
  }

  const fakePerformance = createFakePerformance([]);
  const { records, record } = createRecordCollector();

  /** Trả số giả để chứng minh disabled path vẫn giữ nguyên result. */
  async function returnAnswer<T>(): Promise<T> {
    return 42 as T;
  }

  const profiledInvoke = ipcProfiler.createProfiledInvoke({
    enabled: false,
    performanceApi: fakePerformance.api,
    invoker: returnAnswer,
    record,
  });

  const result = await profiledInvoke<number>("list_remote_files");

  expect(result).toBe(42);
  expect(records).toEqual([]);
  expect(fakePerformance.markNames).toEqual([]);
  expect(fakePerformance.measurements).toEqual([]);
});

/** Bắt lỗi telemetry làm rò argument, response, credential, đường dẫn hoặc URL vào record/mark. */
test("profiled invoke never records arguments or response data", async () => {
  const ipcProfiler = await loadIpcProfiler();
  expect(ipcProfiler).not.toBeNull();
  if (!ipcProfiler) {
    return;
  }

  const password = "secret-password-value";
  const rawPath = "/private/patient/result.pdf";
  const url = "https://odoo.example.invalid/private";
  const responseToken = "secret-response-token";
  const fakePerformance = createFakePerformance([100, 101]);
  const { records, record } = createRecordCollector();

  /** Trả response chứa token giả để chứng minh profiler không record response body. */
  async function returnSensitiveResponse<T>(): Promise<T> {
    return { token: responseToken } as T;
  }

  const profiledInvoke = ipcProfiler.createProfiledInvoke({
    enabled: true,
    performanceApi: fakePerformance.api,
    invoker: returnSensitiveResponse,
    record,
  });

  const result = await profiledInvoke<{ token: string }>("login", {
    args: { login: "technician", password, local_path: rawPath, odoo_url: url },
  });
  const telemetry = JSON.stringify({
    records,
    markNames: fakePerformance.markNames,
    measurements: fakePerformance.measurements,
  });

  expect(result).toEqual({ token: responseToken });
  expect(telemetry).not.toContain(password);
  expect(telemetry).not.toContain(rawPath);
  expect(telemetry).not.toContain(url);
  expect(telemetry).not.toContain(responseToken);
  expect(telemetry).not.toContain("technician");
});

/** Bắt lỗi listener không đo khoảng cách giữa hai status event hoặc thời gian chạy handler. */
test("status event profiling records cadence and handler duration without payload", async () => {
  const ipcProfiler = await loadIpcProfiler();
  expect(ipcProfiler).not.toBeNull();
  if (!ipcProfiler) {
    return;
  }

  const payloadSecret = "status-payload-secret";
  const fakePerformance = createFakePerformance([100, 104, 350, 355]);
  const { records, record } = createRecordCollector();
  let handledEvents = 0;

  /** Đếm event đã chuyển tới handler thật mà không đọc payload. */
  function handleStatusEvent(): void {
    handledEvents += 1;
  }

  const profiledHandler = ipcProfiler.createProfiledEventHandler({
    enabled: true,
    eventName: "sync-status-changed",
    performanceApi: fakePerformance.api,
    handler: handleStatusEvent,
    record,
  });

  profiledHandler({ secret: payloadSecret });
  profiledHandler({ secret: payloadSecret });

  expect(handledEvents).toBe(2);
  expect(records).toEqual([
    {
      command: "event:sync-status-changed",
      durationMs: 4,
      outcome: "success",
      concurrentCalls: 1,
      cadenceMs: null,
    },
    {
      command: "event:sync-status-changed",
      durationMs: 5,
      outcome: "success",
      concurrentCalls: 1,
      cadenceMs: 250,
    },
  ]);
  expect(JSON.stringify(records)).not.toContain(payloadSecret);
});
