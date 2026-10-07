import { expect, test } from "bun:test";

type RenderProfilerModule = typeof import("./renderProfiler");

/** Tải module profiler nếu đã được hiện thực; trả về null để bài test RED có lỗi assertion rõ ràng. */
async function loadRenderProfiler(): Promise<RenderProfilerModule | null> {
  try {
    return await import("./renderProfiler");
  } catch {
    return null;
  }
}

/** Bắt lỗi thiếu hoặc sai nhánh development khiến số liệu render không được ghi ra debug console. */
test("profiler callback logs structured render metrics in development", async () => {
  const renderProfiler = await loadRenderProfiler();
  expect(renderProfiler).not.toBeNull();
  if (!renderProfiler) {
    return;
  }

  const debugEntries: unknown[][] = [];
  const callback = renderProfiler.createRenderProfilerCallback(true, (...entry) => {
    debugEntries.push(entry);
  });

  callback("StatusTab", "update", 12.5, 18.25, 100, 120);

  expect(debugEntries).toEqual([
    [
      "[React Profiler]",
      {
        id: "StatusTab",
        phase: "update",
        actualDuration: 12.5,
        baseDuration: 18.25,
        startTime: 100,
        commitTime: 120,
      },
    ],
  ]);
});

/** Bắt lỗi làm profiler ghi console trong production dù instrumentation đã bị tắt. */
test("profiler callback stays silent outside development", async () => {
  const renderProfiler = await loadRenderProfiler();
  expect(renderProfiler).not.toBeNull();
  if (!renderProfiler) {
    return;
  }

  const debugEntries: unknown[][] = [];
  const callback = renderProfiler.createRenderProfilerCallback(false, (...entry) => {
    debugEntries.push(entry);
  });

  callback("FoldersTab", "mount", 4, 4, 10, 14);

  expect(debugEntries).toEqual([]);
});
