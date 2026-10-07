import { memo, useMemo, type ReactNode } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { JobRow, RemoteFileRow, StatusDto } from "../../types";
import { isOfficeDocument } from "../office/OfficeEditor";

/** Key thông điệp hiện cho một trạng thái job/tệp. */
export function statusMessageKey(status: string): MessageKey {
  switch (status) {
    case "pending":
      return "status.pending";
    case "running":
      return "status.running";
    case "retry_wait":
      return "status.retry_wait";
    case "completed":
      return "status.completed";
    case "failed":
      return "status.failed";
    case "conflict":
      return "status.conflict";
    case "unauthenticated":
      return "status.unauthenticated";
    default:
      return "status.synced";
  }
}

/** Phần trăm hoàn thành (0–100) của job: job xong luôn là 100, còn lại tính theo byte đã truyền. */
export function jobPercent(job: JobRow): number {
  if (job.status === "completed") {
    return 100;
  }
  if (job.bytes_total <= 0) {
    return 0;
  }
  return Math.min(100, Math.floor((job.bytes_done / job.bytes_total) * 100));
}

/** Cột tiến độ của job: phần trăm hoàn thành, ví dụ `42%`. */
export const JobProgress = memo(function JobProgress({ job }: Readonly<{ job: JobRow }>) {
  return <span className="tabular-nums">{jobPercent(job)}%</span>;
});

/** Bảng dùng chung cho các danh sách trên tab Trạng thái (job, tệp): tiêu đề, cột, và trạng thái rỗng. */
export const StatusTable = memo(function StatusTable({
  title,
  columns,
  empty,
  isEmpty,
  children,
}: Readonly<{
  title: string;
  columns: ReactNode[];
  empty: string;
  isEmpty: boolean;
  children: ReactNode;
}>) {
  return (
    <div className="mt-6 overflow-hidden rounded-lg border bg-white">
      <div className="border-b px-3 py-2 text-sm font-medium">{title}</div>
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            {columns.map((column, index) => (
              <th key={`${title}-${index}`} className="px-3 py-2">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isEmpty ? (
            <tr>
              <td className="px-3 py-6 text-slate-500" colSpan={columns.length}>
                {empty}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  );
});

/** Thuộc tính đầu vào cho nhóm thẻ thống kê trạng thái. */
export type StatusCardsProps = {
  completed: number;
  uploading: number;
  downloading: number;
  pending: number;
  failed: number;
  conflict: number;
  paused: boolean;
};

/** Nhóm thẻ đếm số lượng công việc theo từng trạng thái đồng bộ (đã memoize). */
export const StatusCards = memo(function StatusCards({
  completed,
  uploading,
  downloading,
  pending,
  failed,
  conflict,
  paused,
}: Readonly<StatusCardsProps>) {
  const t = useT();
  const cards = [
    [t("card.synced"), completed],
    [t("card.uploading"), uploading],
    [t("card.downloading"), downloading],
    [t("card.pending"), pending],
    [t("card.failed"), failed],
    [t("card.conflict"), conflict],
    [t("card.paused"), paused ? 1 : 0],
  ] as const;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {cards.map(([label, value]) => (
        <div key={String(label)} className="rounded-lg border bg-white p-4">
          <div className="text-xs text-slate-500">{label}</div>
          <div className="mt-1 text-2xl font-semibold">{value}</div>
        </div>
      ))}
    </div>
  );
});

/** Thuộc tính đầu vào của một hàng job trong bảng tiến độ. */
export type JobRowProps = {
  job: JobRow;
  accessPaused: boolean;
  busy: boolean;
  onRetry: (jobId: number) => void;
};

/** Một hàng hiển thị tiến độ và thông tin lỗi của một job đồng bộ (đã memoize). */
export const JobRowView = memo(function JobRowView({
  job,
  accessPaused,
  busy,
  onRetry,
}: Readonly<JobRowProps>) {
  const t = useT();
  return (
    <tr className="border-t">
      <td className="px-3 py-2">{job.relative_path}</td>
      <td className="px-3 py-2">
        {t(accessPaused ? "status.access_paused" : statusMessageKey(job.status))}
      </td>
      <td className="px-3 py-2">
        <JobProgress job={job} />
      </td>
      {accessPaused ? (
        <td className="px-3 py-2 text-amber-700">{t("status.access_paused.detail")}</td>
      ) : (
        <td className="px-3 py-2 text-red-700">{job.last_error || "—"}</td>
      )}
      <td className="px-3 py-2">
        {!accessPaused && (job.status === "failed" || job.status === "retry_wait") ? (
          <button
            type="button"
            className="btn btn-secondary px-2 py-1"
            disabled={busy}
            onClick={() => onRetry(job.id)}
          >
            {t("action.retry")}
          </button>
        ) : null}
      </td>
    </tr>
  );
});

/** Thuộc tính đầu vào của bảng danh sách job. */
export type JobsTableProps = {
  jobs: JobRow[];
  deniedFolderIds: Set<number>;
  busy: boolean;
  onRetry: (jobId: number) => void;
};

/** Bảng hiển thị danh sách các tác vụ đồng bộ tệp đang diễn ra hoặc chờ xử lý (đã memoize). */
export const JobsTable = memo(function JobsTable({
  jobs,
  deniedFolderIds,
  busy,
  onRetry,
}: Readonly<JobsTableProps>) {
  const t = useT();
  // Memoize mảng cột để không phá vỡ React.memo của StatusTable khi re-render (N-4).
  const columns = useMemo(
    () => [t("files.col.file"), t("files.col.status"), t("jobs.col.progress"), t("status.failed"), ""],
    [t],
  );
  return (
    <StatusTable
      title={t("jobs.title")}
      columns={columns}
      empty={t("jobs.empty")}
      isEmpty={jobs.length === 0}
    >
      {jobs.map((job) => {
        // Job chờ của folder mất quyền: tạm dừng (không phải lỗi), tự chạy lại khi được cấp lại quyền.
        const accessPaused =
          deniedFolderIds.has(job.folder_id) &&
          (job.status === "pending" || job.status === "retry_wait");
        return (
          <JobRowView
            key={job.id}
            job={job}
            accessPaused={accessPaused}
            busy={busy}
            onRetry={onRetry}
          />
        );
      })}
    </StatusTable>
  );
});

/** Thuộc tính đầu vào của cụm nút giải quyết xung đột tệp. */
export type ConflictResolveButtonsProps = {
  fileId: number;
  busy: boolean;
  onKeepLocal: (fileId: number) => void;
  onAcceptServer: (fileId: number) => void;
};

/** Hai nút xử lý xung đột: giữ bản cục bộ hoặc dùng bản server (có xác nhận, đã memoize). */
export const ConflictResolveButtons = memo(function ConflictResolveButtons({
  fileId,
  busy,
  onKeepLocal,
  onAcceptServer,
}: Readonly<ConflictResolveButtonsProps>) {
  const t = useT();
  return (
    <>
      <button
        type="button"
        className="btn btn-secondary px-2 py-1"
        disabled={busy}
        onClick={() => onKeepLocal(fileId)}
      >
        {t("files.keepLocal")}
      </button>
      <button
        type="button"
        className="btn btn-secondary px-2 py-1"
        disabled={busy}
        onClick={() => {
          if (window.confirm(t("files.useServerConfirm"))) {
            onAcceptServer(fileId);
          }
        }}
      >
        {t("files.useServer")}
      </button>
    </>
  );
});

/** Thuộc tính đầu vào cho một hàng hiển thị tệp từ xa. */
export type RemoteFileRowProps = {
  file: RemoteFileRow;
  busy: boolean;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
};

/** Một hàng hiển thị thông tin và thao tác tệp từ xa (lịch sử, office, xung đột, đã memoize). */
export const RemoteFileRowView = memo(function RemoteFileRowView({
  file,
  busy,
  onOpenHistory,
  onOpenOffice,
  onAcceptServer,
  onKeepLocal,
}: Readonly<RemoteFileRowProps>) {
  const t = useT();
  return (
    <tr className="border-t">
      <td className="px-3 py-2">{file.relative_path}</td>
      <td className="px-3 py-2">{t(statusMessageKey(file.status))}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-2">
          {file.remote_file_id ? (
            <button
              type="button"
              className="btn btn-secondary px-2 py-1"
              disabled={busy}
              onClick={() => onOpenHistory(file.remote_file_id as number, file.relative_path)}
            >
              {t("files.history")}
            </button>
          ) : null}
          {file.remote_file_id && isOfficeDocument(file.relative_path) ? (
            <button
              type="button"
              className="btn btn-secondary px-2 py-1"
              disabled={busy}
              onClick={() => onOpenOffice(file.remote_file_id as number, file.relative_path)}
            >
              {t("files.office")}
            </button>
          ) : null}
          {file.status === "conflict" ? (
            <ConflictResolveButtons
              fileId={file.id}
              busy={busy}
              onKeepLocal={onKeepLocal}
              onAcceptServer={onAcceptServer}
            />
          ) : null}
        </div>
      </td>
    </tr>
  );
});

/** Thuộc tính đầu vào cho bảng danh sách tệp từ xa. */
export type RemoteFilesTableProps = {
  remoteFiles: RemoteFileRow[];
  busy: boolean;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
};

/** Bảng hiển thị danh sách các tệp trên máy chủ đã đồng bộ hoặc xung đột (đã memoize). */
export const RemoteFilesTable = memo(function RemoteFilesTable({
  remoteFiles,
  busy,
  onOpenHistory,
  onOpenOffice,
  onAcceptServer,
  onKeepLocal,
}: Readonly<RemoteFilesTableProps>) {
  const t = useT();
  // Memoize mảng cột để không phá vỡ React.memo của StatusTable khi re-render (N-4).
  const columns = useMemo(() => [t("files.col.file"), t("files.col.status"), ""], [t]);
  return (
    <StatusTable
      title={t("files.title")}
      columns={columns}
      empty={t("files.empty")}
      isEmpty={remoteFiles.length === 0}
    >
      {remoteFiles.map((file) => (
        <RemoteFileRowView
          key={file.id}
          file={file}
          busy={busy}
          onOpenHistory={onOpenHistory}
          onOpenOffice={onOpenOffice}
          onAcceptServer={onAcceptServer}
          onKeepLocal={onKeepLocal}
        />
      ))}
    </StatusTable>
  );
});

/** Thuộc tính đầu vào của tab Trạng thái: dữ liệu status/file từ xa và các callback xử lý xung đột/mở lịch sử. */
export type StatusTabProps = {
  status: StatusDto;
  busy: boolean;
  remoteFiles: RemoteFileRow[];
  onRetry: (jobId: number) => void;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
};

/** Tab Trạng thái: thẻ đếm theo loại, danh sách job, và danh sách tệp đã đồng bộ (đã memoize). */
export const StatusTab = memo(function StatusTab({
  status,
  busy,
  remoteFiles,
  onRetry,
  onOpenHistory,
  onOpenOffice,
  onAcceptServer,
  onKeepLocal,
}: Readonly<StatusTabProps>) {
  const deniedFolderIds = useMemo(
    () =>
      new Set(
        status.folders
          .filter((folder) => folder.access_state === "denied")
          .map((folder) => folder.id),
      ),
    [status.folders],
  );

  return (
    <>
      <StatusCards
        completed={status.completed}
        uploading={status.uploading}
        downloading={status.downloading}
        pending={status.pending}
        failed={status.failed}
        conflict={status.conflict}
        paused={status.paused}
      />
      <JobsTable
        jobs={status.jobs}
        deniedFolderIds={deniedFolderIds}
        busy={busy}
        onRetry={onRetry}
      />
      <RemoteFilesTable
        remoteFiles={remoteFiles}
        busy={busy}
        onOpenHistory={onOpenHistory}
        onOpenOffice={onOpenOffice}
        onAcceptServer={onAcceptServer}
        onKeepLocal={onKeepLocal}
      />
    </>
  );
});
