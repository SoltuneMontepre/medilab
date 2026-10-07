import type { ProfilerOnRenderCallback } from "react";

/** Hàm ghi debug được tiêm vào callback để test mà không đụng console thật. */
type DebugLogger = (...data: unknown[]) => void;

/** Chuyển bản ghi profiler sang debug console của WebView. */
function logToDebugConsole(...data: unknown[]): void {
  console.debug(...data);
}

/** Tạo callback React Profiler chỉ ghi số liệu khi ứng dụng đang chạy ở development mode. */
export function createRenderProfilerCallback(
  isDevelopment: boolean,
  logger: DebugLogger,
): ProfilerOnRenderCallback {
  /** Ghi một lần commit render với các trường thời gian do React Profiler cung cấp. */
  function onRender(
    id: string,
    phase: "mount" | "update" | "nested-update",
    actualDuration: number,
    baseDuration: number,
    startTime: number,
    commitTime: number,
  ): void {
    if (!isDevelopment) {
      return;
    }

    logger("[React Profiler]", {
      id,
      phase,
      actualDuration,
      baseDuration,
      startTime,
      commitTime,
    });
  }

  return onRender;
}

/** Callback dùng chung cho các subtree; production build không phát log. */
export const recordRenderProfile = createRenderProfilerCallback(import.meta.env.DEV, logToDebugConsole);
