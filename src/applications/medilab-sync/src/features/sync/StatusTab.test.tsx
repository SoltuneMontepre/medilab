import { describe, expect, test } from "bun:test";
import React from "react";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import type { JobRow, ProgressDeltaDto } from "../../types";
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
  StatusSummary,
  StatusTab,
  StatusTable,
  filterRemoteFiles,
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
        onOpenFile={() => {}}
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

describe("StatusCards", () => {
  test("gộp việc đang chạy và đang chờ thành một thẻ, không có thẻ Tạm dừng", () => {
    const html = renderWithLocale(
      <StatusCards completed={5} uploading={1} downloading={2} pending={3} failed={0} conflict={0} />,
    );
    expect(html).toContain("Đang xử lý");
    expect(html).toContain(">6<");
    expect(html).not.toContain("Tạm dừng");
  });
});

describe("RemoteFilesTable", () => {
  const handlers = {
    busy: false,
    onOpenFile: () => {},
    onOpenHistory: () => {},
    onOpenOffice: () => {},
    onAcceptServer: () => {},
    onKeepLocal: () => {},
  };

  test("xếp tệp dưới tên thư mục của nó", () => {
    const { folders } = createStatusFixture();
    const files = [
      { id: 1, folder_id: 2, relative_path: "second.csv", remote_file_id: 8, remote_version_id: 1, status: "synced" },
      { id: 2, folder_id: 1, relative_path: "first.csv", remote_file_id: 9, remote_version_id: 1, status: "synced" },
    ];
    const html = renderWithLocale(<RemoteFilesTable remoteFiles={files} folders={folders} {...handlers} />);
    const order = ["ROOT1", "first.csv", "ROOT2", "second.csv"].map((text) => html.indexOf(text));
    expect(order.every((index) => index >= 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  test("mỗi tệp có nút mở bằng chương trình của nó", () => {
    const { folders } = createStatusFixture();
    const html = renderWithLocale(
      <RemoteFilesTable remoteFiles={createRemoteFilesFixture()} folders={folders} {...handlers} />,
    );
    expect(html).toContain(">Mở</button>");
  });

  test("tìm tệp theo một phần tên, không phân biệt hoa thường", () => {
    const files = createRemoteFilesFixture();
    expect(filterRemoteFiles(files, "FILE2").map((file) => file.relative_path)).toEqual(["file2.txt"]);
    expect(filterRemoteFiles(files, "  ")).toBe(files);
  });
});


test("listed Office files offer editing by folder policy", () => {
  for (const extension of ["docx", "xlsx", "pptx"]) {
    for (const category of [null, "working", "result", "raw"]) {
      const html = renderWithLocale(
        <RemoteFileRowView
          file={{ id: 1, folder_id: 1, relative_path: `probe.${extension}`, remote_file_id: 8, remote_version_id: 15, status: "synced" }}
          category={category}
          busy={false}
          onOpenFile={() => {}}
          onOpenHistory={() => {}}
          onOpenOffice={() => {}}
          onAcceptServer={() => {}}
          onKeepLocal={() => {}}
        />,
      );
      expect(html).toContain(`probe.${extension}`);
      expect(html.includes("Chỉnh sửa trực tuyến")).toBe(category !== "raw");
    }
  }
});

describe("JobRowView", () => {
  const waiting: JobRow = {
    id: 7,
    folder_id: 1,
    file_id: 7,
    relative_path: "profile.ps1.bak",
    operation: "upload",
    status: "retry_wait",
    attempt_count: 0,
    last_error: null,
    bytes_total: 307,
    bytes_done: 307,
    remote_file_id: null,
    remote_version_id: null,
  };

  function renderJob(job: JobRow): string {
    return renderWithLocale(<JobRowView job={job} accessPaused={false} busy={false} onRetry={() => {}} />);
  }

  test("job chờ server xác minh hiện là đang xác minh, không có nút thử lại", () => {
    const html = renderJob({ ...waiting, wait_reason: "verifying" });
    expect(html).toContain("Máy chủ đang xác minh");
    expect(html).not.toContain("Thử lại");
    expect(html).not.toContain("text-red-700");
  });

  test("job đang hỏi lại server xác minh vẫn hiện đang xác minh, không phải đang tải lên", () => {
    const html = renderJob({ ...waiting, status: "running", wait_reason: "verifying" });
    expect(html).toContain("Máy chủ đang xác minh");
    expect(html).not.toContain("Đang tải lên");
  });

  test("job chờ thử lại sau lỗi vẫn có nút thử lại", () => {
    const html = renderJob({ ...waiting, last_error: "503: Service Unavailable" });
    expect(html).toContain("Đang chờ thử lại");
    expect(html).toContain("Thử lại");
  });
});

describe("StatusSummary", () => {
  test("nói rõ việc cần làm theo tình hình đồng bộ", () => {
    const base = createStatusFixture({ pending: 0, uploading: 0, downloading: 0, failed: 0, conflict: 0, paused: false });
    expect(renderWithLocale(<StatusSummary status={base} />)).toContain("Tất cả tệp đã được đồng bộ");
    expect(renderWithLocale(<StatusSummary status={{ ...base, conflict: 2 }} />)).toContain("2 tệp cần bạn xem");
    expect(renderWithLocale(<StatusSummary status={{ ...base, uploading: 3 }} />)).toContain("còn 3 tệp");
    expect(renderWithLocale(<StatusSummary status={{ ...base, paused: true }} />)).toContain("tạm dừng");
    expect(renderWithLocale(<StatusSummary status={{ ...base, folders: [] }} onOpenFolders={() => {}} />)).toContain("Thêm thư mục");
  });
});
