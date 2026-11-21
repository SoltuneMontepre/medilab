import { memo, useMemo, type ReactNode } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { JobRow, RemoteFileRow, StatusDto } from "../../types";
import { canEditOnline } from "../office/officeFiles";

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

/** Màu huy hiệu theo trạng thái: xanh = xong, đỏ = lỗi, vàng = cần chú ý hoặc chờ, xanh dương = đang chạy. */
function statusTone(status: string, accessPaused = false): string {
  if (accessPaused || status === "conflict" || status === "retry_wait") {
    return "bg-amber-100 text-amber-800";
  }
  if (status === "failed" || status === "unauthenticated") {
    return "bg-red-100 text-red-700";
  }
  if (status === "running") {
    return "bg-sky-100 text-sky-800";
  }
  if (status === "pending") {
    return "bg-slate-200 text-slate-700";
  }
  return "bg-emerald-100 text-emerald-800";
}

/** Nhãn trạng thái dạng huy hiệu màu, để lỗi và xung đột nổi bật giữa danh sách tệp. */
function StatusBadge({ status, accessPaused = false }: Readonly<{ status: string; accessPaused?: boolean }>) {
  const t = useT();
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${statusTone(status, accessPaused)}`}>
      {t(accessPaused ? "status.access_paused" : statusMessageKey(status))}
    </span>
  );
}

/** Một câu nói rõ tình hình đồng bộ hiện tại và việc cần làm, đặt trên các thẻ đếm. */
export function StatusSummary({
  status,
  onOpenFolders,
}: Readonly<{ status: StatusDto; onOpenFolders?: () => void }>) {
  const t = useT();
  const attention = status.failed + status.conflict;
  const working = status.pending + status.uploading + status.downloading;
  let tone = "border-emerald-200 bg-emerald-50 text-emerald-900";
  let text = t("summary.ok");
  if (status.folders.length === 0) {
    tone = "border-slate-200 bg-white text-slate-800";
    text = t("summary.noFolders");
  } else if (status.paused) {
    tone = "border-amber-200 bg-amber-50 text-amber-900";
    text = t("summary.paused");
  } else if (attention > 0) {
    tone = "border-red-200 bg-red-50 text-red-800";
    text = t("summary.attention", { count: attention });
  } else if (working > 0) {
    tone = "border-sky-200 bg-sky-50 text-sky-900";
    text = t("summary.working", { count: working });
  }
  return (
    <div className={`mb-4 flex items-center justify-between gap-3 rounded-lg border px-4 py-3 ${tone}`} role="status">
      <span className="font-medium">{text}</span>
      {status.folders.length === 0 && onOpenFolders ? (
        <button type="button" className="btn btn-primary shrink-0" onClick={onOpenFolders}>
          {t("summary.addFolder")}
        </button>
      ) : null}
    </div>
  );
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
    [t("card.synced"), completed, false],
    [t("card.uploading"), uploading, false],
    [t("card.downloading"), downloading, false],
    [t("card.pending"), pending, false],
    [t("card.failed"), failed, true],
    [t("card.conflict"), conflict, true],
    [t("card.paused"), paused ? 1 : 0, false],
  ] as const;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {cards.map(([label, value, alert]) => (
        <div
          key={String(label)}
          className={`rounded-lg border p-4 ${
            alert && value > 0 ? "border-red-200 bg-red-50" : "bg-white"
          }`}
        >
          <div className="text-xs text-slate-500">{label}</div>
          <div className={`mt-1 text-2xl font-semibold ${value === 0 ? "text-slate-300" : ""}`}>{value}</div>
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
        <StatusBadge status={job.status} accessPaused={accessPaused} />
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
  category?: string | null;
  busy: boolean;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
};

/** Một hàng hiển thị thông tin và thao tác tệp từ xa (lịch sử, office, xung đột, đã memoize). */
export const RemoteFileRowView = memo(function RemoteFileRowView({
  file,
  category,
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
      <td className="px-3 py-2">
        <StatusBadge status={file.status} />
      </td>
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
          {file.remote_file_id && canEditOnline(file.relative_path, category) ? (
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
  categories?: ReadonlyMap<number, string | null | undefined>;
  busy: boolean;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
};

/** Bảng hiển thị danh sách các tệp trên máy chủ đã đồng bộ hoặc xung đột (đã memoize). */
export const RemoteFilesTable = memo(function RemoteFilesTable({
  remoteFiles,
  categories,
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
          category={categories?.get(file.folder_id)}
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
  categories?: ReadonlyMap<number, string | null | undefined>;
  onRetry: (jobId: number) => void;
  onOpenHistory: (fileId: number, label: string) => void;
  onOpenOffice: (fileId: number, label: string) => void;
  onAcceptServer: (fileId: number) => void;
  onKeepLocal: (fileId: number) => void;
  onOpenFolders?: () => void;
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
  onOpenFolders,
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
      <StatusSummary status={status} onOpenFolders={onOpenFolders} />
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
        categories={new Map(status.folders.map((folder) => [folder.id, folder.category]))}
        busy={busy}
        onOpenHistory={onOpenHistory}
        onOpenOffice={onOpenOffice}
        onAcceptServer={onAcceptServer}
        onKeepLocal={onKeepLocal}
      />
    </>
  );
});
