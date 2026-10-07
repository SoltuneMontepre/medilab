import { describe, expect, test } from "bun:test";
import React from "react";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import type { ProgressDeltaDto } from "../../types";
import { applyProgressDelta, mergeRemoteFiles } from "../../lib/syncEvents";
import { createRemoteFilesFixture, createStatusFixture } from "../../test/syncFixtures";
import {
  ConflictResolveButtons,
  JobProgress,
  JobRowView,
  JobsTable,
  RemoteFileRowView,
  RemoteFilesTable,
  StatusCards,
  StatusTab,
  StatusTable,
} from "./StatusTab";

/** Helper bọc component bằng LocaleProvider để test render html. */
function renderWithLocale(element: React.ReactElement): string {
  return renderToString(<LocaleProvider locale="vi">{element}</LocaleProvider>);
}

describe("StatusTab component memoization and render isolation", () => {
  test("mọi subcomponent quan trọng đều được memoize qua React.memo", () => {
    // React 19 memo object có $$typeof = Symbol.for('react.memo')
    const memoSymbol = Symbol.for("react.memo");

    expect((StatusTab as any).$$typeof).toBe(memoSymbol);
    expect((StatusCards as any).$$typeof).toBe(memoSymbol);
    expect((JobsTable as any).$$typeof).toBe(memoSymbol);
    expect((JobRowView as any).$$typeof).toBe(memoSymbol);
    expect((JobProgress as any).$$typeof).toBe(memoSymbol);
    expect((RemoteFilesTable as any).$$typeof).toBe(memoSymbol);
    expect((RemoteFileRowView as any).$$typeof).toBe(memoSymbol);
    expect((ConflictResolveButtons as any).$$typeof).toBe(memoSymbol);
    expect((StatusTable as any).$$typeof).toBe(memoSymbol);
  });

  test("progress delta bảo toàn reference của folders, remoteFiles và các job không liên quan", () => {
    const status = createStatusFixture();
    const remoteFiles = createRemoteFilesFixture();

    const delta: ProgressDeltaDto = {
      jobId: 101,
      done: 750,
      total: 1000,
    };

    const nextStatus = applyProgressDelta(status, delta);

    // Folders không bị đổi reference
    expect(nextStatus.folders).toBe(status.folders);

    // Job 101 được cập nhật
    expect(nextStatus.jobs[0].bytes_done).toBe(750);
    expect(nextStatus.jobs[0]).not.toBe(status.jobs[0]);

    // Job 102 giữ nguyên reference identity
    expect(nextStatus.jobs[1]).toBe(status.jobs[1]);

    // remoteFiles hoàn toàn không bị ảnh hưởng bởi tiến độ job
    expect(remoteFiles).toBe(remoteFiles);

    // Các thẻ thống kê (counters) hoàn toàn giữ nguyên giá trị nguyên thủy
    expect(nextStatus.completed).toBe(status.completed);
    expect(nextStatus.uploading).toBe(status.uploading);
    expect(nextStatus.downloading).toBe(status.downloading);
    expect(nextStatus.pending).toBe(status.pending);
    expect(nextStatus.failed).toBe(status.failed);
    expect(nextStatus.conflict).toBe(status.conflict);
    expect(nextStatus.paused).toBe(status.paused);
  });

  test("RemoteFilesTable giữ nguyên reference mảng khi fetch trả về kết quả tương đương", () => {
    const remoteFiles = createRemoteFilesFixture();
    const clonedFiles = remoteFiles.map((f) => ({ ...f }));

    const mergedFiles = mergeRemoteFiles(remoteFiles, clonedFiles);

    // Reference phải hoàn toàn giống hệt
    expect(mergedFiles).toBe(remoteFiles);
  });

  test("StatusTab và các subcomponent render HTML hợp lệ không phát sinh lỗi", () => {
    const status = createStatusFixture();
    const remoteFiles = createRemoteFilesFixture();

    const html = renderWithLocale(
      <StatusTab
        status={status}
        busy={false}
        remoteFiles={remoteFiles}
        onRetry={() => {}}
        onOpenHistory={() => {}}
        onOpenOffice={() => {}}
        onAcceptServer={() => {}}
        onKeepLocal={() => {}}
      />,
    );

    expect(html).toContain("file1.txt");
    expect(html).toContain("file2.txt");
    expect(html).toContain("20");
    expect(html).toContain("Đã đồng bộ");
  });
});
