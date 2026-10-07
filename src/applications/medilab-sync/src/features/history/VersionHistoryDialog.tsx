import { useEffect, useState } from "react";
import { useT } from "../../locale";
import type { FileVersion, FileVersionList } from "../../types";
import { getRestoreActionState, resolveSelectedVersion } from "./versionRules";
import { getFileVersionDetail, getFileVersions, restoreFileVersion } from "../../lib/tauri";

/** Định dạng một số byte thành B/KB/MB dễ đọc. */
function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** Nhãn hiển thị cho nguồn gốc một version (xung đột, phục hồi, ONLYOFFICE, hay đồng bộ từ
 * thiết bị). */
function versionSourceLabel(version: FileVersion, t: ReturnType<typeof useT>): string {
  if (version.source === "CONFLICT") {
    return t("source.conflict");
  }
  if (version.source === "RESTORE") {
    const restored = version.restored_from_version_number;
    return restored ? t("source.restoreFrom", { version: restored }) : t("source.restore");
  }
  if (version.source === "ONLYOFFICE") {
    return t("source.office");
  }
  const device = version.device?.name;
  return device ? t("source.device", { device }) : t("source.desktop");
}

/** Nhãn hiển thị cho việc đối tượng lưu trữ của một version còn tồn tại hay không. */
function objectAvailabilityLabel(
  available: boolean | null | undefined,
  t: ReturnType<typeof useT>,
): string {
  if (available === false) {
    return t("object.gone");
  }
  if (available) {
    return t("object.ok");
  }
  return t("object.unknown");
}

/** `"vN"` nếu có số version, dấu gạch ngang nếu không. */
function versionOrDash(versionNumber: number | null | undefined): string {
  return versionNumber ? `v${versionNumber}` : "—";
}

/** Thuộc tính đầu vào của dialog lịch sử version: file đang xem và callback đóng. */
type VersionHistoryDialogProps = Readonly<{
  fileId: number;
  label: string;
  onClose: () => void;
}>;

/** Bảng phân trang lịch sử version, cho chọn bất kỳ dòng nào để xem chi tiết hoặc khôi phục.
 *
 * Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
 */
function VersionHistoryList({
  page,
  busy,
  offset,
  selectedId,
  onSelect,
  onPrev,
  onNext,
}: Readonly<{
  page: FileVersionList | null;
  busy: boolean;
  offset: number;
  selectedId?: number | null;
  onSelect: (version: FileVersion) => void;
  onPrev: () => void;
  onNext: () => void;
}>) {
  const t = useT();
  const items = page?.items ?? [];
  const rangeLabel = page ? `${page.offset + 1}–${page.offset + page.items.length} / ${page.total}` : "";
  const canPrev = !busy && offset > 0;
  const canNext = Boolean(page) && !busy && offset + items.length < (page?.total ?? 0);

  return (
    <div className="flex min-w-0 flex-col rounded border">
      <div className="flex items-center justify-between border-b bg-slate-50 px-3 py-2 text-xs text-slate-500">
        <span>{t("history.tableHint")}</span>
        <span className="tabular-nums">{rangeLabel}</span>
      </div>
      <div className="min-w-0 overflow-x-auto">
        <table className="w-full text-left text-sm" role="table">
          <thead className="bg-slate-50/70 text-slate-600">
            <tr>
              <th className="px-3 py-2 font-medium">{t("history.col.version")}</th>
              <th className="px-3 py-2 font-medium">{t("history.col.time")}</th>
              <th className="px-3 py-2 font-medium">{t("history.col.source")}</th>
              <th className="px-3 py-2 font-medium">{t("history.col.status")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((version) => {
              const isSelected = selectedId === version.id;
              return (
                <tr
                  key={version.id}
                  tabIndex={0}
                  aria-selected={isSelected}
                  onClick={() => onSelect(version)}
                  onKeyDown={(event) => {
                    // Hỗ trợ chọn dòng bằng bàn phím (Enter hoặc Space)
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(version);
                    }
                  }}
                  className={`border-t cursor-pointer select-none transition-colors outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-inset ${
                    isSelected
                      ? "bg-sky-50 font-medium text-sky-950"
                      : "hover:bg-slate-50 text-slate-800"
                  }`}
                >
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className={isSelected ? "font-semibold text-sky-900" : "font-medium"}>
                      v{version.version_number}
                    </span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{version.created_at || "—"}</td>
                  <td className="px-3 py-2">{versionSourceLabel(version, t)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {version.is_canonical ? (
                      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800">
                        {t("history.current")}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-600">
                        {t("history.past")}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-slate-600">
        <span>{rangeLabel}</span>
        <div className="flex gap-2">
          <button type="button" className="btn btn-secondary px-2 py-1" disabled={!canPrev} onClick={onPrev}>
            {t("history.prev")}
          </button>
          <button type="button" className="btn btn-secondary px-2 py-1" disabled={!canNext} onClick={onNext}>
            {t("history.next")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Chi tiết một version đã chọn, kèm nút phục hồi nếu được phép.
 *
 * Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
 */
function VersionHistoryDetail({
  selected,
  busy,
  onRestore,
}: Readonly<{
  selected: FileVersion | null;
  busy: boolean;
  onRestore: (version: FileVersion) => void;
}>) {
  const t = useT();
  if (!selected) {
    return <p className="text-slate-500">{t("history.pick")}</p>;
  }

  // Quyết định trạng thái nút khôi phục qua quy tắc nghiệp vụ chuẩn
  const { isCurrent, canRestore, reason } = getRestoreActionState(selected);

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold">v{selected.version_number}</h3>
        {isCurrent ? (
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-800">
            {t("history.current")}
          </span>
        ) : (
          <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-600">
            {t("history.past")}
          </span>
        )}
      </div>
      <dl className="mt-2 space-y-1 break-words">
        <div>
          {t("history.col.time")}: {selected.created_at || "—"}
        </div>
        <div>
          {t("history.createdBy")}: {selected.created_by?.name || "—"}
        </div>
        <div>
          {t("history.device")}: {selected.device?.name || "—"}
        </div>
        <div>
          <div>SHA-256:</div>
          {/* Hiện đủ hash để đối chiếu: chữ đơn cách, tự xuống dòng trong khung, không cắt bằng "…". */}
          <div className="break-all font-mono text-xs text-slate-700">{selected.content_hash}</div>
        </div>
        <div>
          {t("history.size")}: {formatBytes(selected.size)}
        </div>
        <div>
          {t("history.source")}: {versionSourceLabel(selected, t)}
        </div>
        <div>
          {t("history.parent")}: {versionOrDash(selected.parent_version_number)}
        </div>
        <div>
          {t("history.restoredFrom")}: {versionOrDash(selected.restored_from_version_number)}
        </div>
        <div>
          {t("history.object")}: {objectAvailabilityLabel(selected.object_available, t)}
        </div>
      </dl>
      <div className="mt-4 border-t pt-3">
        {isCurrent ? (
          <button
            type="button"
            className="btn btn-secondary cursor-not-allowed opacity-60 text-xs"
            disabled
            aria-disabled="true"
          >
            {t("history.alreadyCurrent")}
          </button>
        ) : (
          <div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !canRestore}
              onClick={() => onRestore(selected)}
            >
              {t("history.restoreThis")}
            </button>
            {reason === "object_unavailable" ? (
              <p className="mt-1 text-xs text-red-600">{t("history.objectUnavailableHint")}</p>
            ) : null}
            {reason === "closed" ? (
              <p className="mt-1 text-xs text-amber-600">{t("history.cannotRestoreClosed")}</p>
            ) : null}
          </div>
        )}
      </div>
    </>
  );
}

/** Dialog lịch sử version đầy đủ cho một tệp: danh sách phân trang + chi tiết + xác nhận phục
 * hồi.
 *
 * Luật nghiệp vụ: applications/laboratory-file-sync-application/docs/contract.md#apisyncv1-contract
 */
export function VersionHistoryDialog({
  fileId,
  label,
  onClose,
}: VersionHistoryDialogProps) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState<FileVersionList | null>(null);
  const [selected, setSelected] = useState<FileVersion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<FileVersion | null>(null);
  const offset = page?.offset ?? 0;

  /** Tải một trang lịch sử version. Nếu targetVersionId được chỉ định thì chọn nó; nếu không,
   * giữ lựa chọn hiện tại nếu còn trên trang mới; nếu không còn hoặc chưa chọn thì chọn bản ghi
   * đầu tiên của trang (phiên bản mới nhất của trang đó). */
  async function load(nextOffset = 0, preferredVersionId?: number | null) {
    setBusy(true);
    setError(null);
    try {
      const list = await getFileVersions(fileId, 20, nextOffset);
      setPage(list);
      // Xác định phiên bản cần hiển thị qua helper chuẩn
      const target = resolveSelectedVersion(list.items, preferredVersionId, selected?.id);
      if (!target) {
        setSelected(null);
        return;
      }
      setSelected(target);
      // Tải chi tiết đầy đủ của phiên bản đã chọn (bao gồm kiểm tra tính sẵn sàng của object)
      const detail = await getFileVersionDetail(fileId, target.id);
      setSelected(detail);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load(0);
  }, [fileId]);

  /** Chọn một version cụ thể và tải chi tiết đầy đủ của nó. */
  async function selectVersion(version: FileVersion) {
    // Hiển thị ngay metadata sẵn có từ danh sách để giao diện phản hồi tức thì
    setSelected(version);
    setBusy(true);
    setError(null);
    try {
      const detail = await getFileVersionDetail(fileId, version.id);
      setSelected(detail);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  /** Xác nhận và thực hiện phục hồi version đang chờ xác nhận. */
  async function confirmRestore() {
    if (!confirming) {
      return;
    }
    const targetVersion = confirming;
    setBusy(true);
    setError(null);
    try {
      const restored = await restoreFileVersion(fileId, targetVersion.id);
      setConfirming(null);
      setNotice(t("history.restoredSuccess", { version: targetVersion.version_number }));
      // Làm mới danh sách từ trang đầu và chọn ngay phiên bản chuẩn mới được tạo ra
      await load(0, restored.id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    // Lớp phủ căn giữa dialog theo cả hai chiều; dialog cao tối đa bằng viewport trừ lề và tự cuộn
    // phần nội dung bên trong, nên không bao giờ trôi ra ngoài màn hình hay lệch lên trên.
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-6">
      <div className="flex max-h-[calc(100vh-3rem)] w-full max-w-4xl flex-col rounded-lg border bg-white p-4 shadow-lg">
        <div className="flex shrink-0 items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">{t("history.title")}</h2>
            <p className="break-words text-sm text-slate-600">{label}</p>
          </div>
          <button type="button" className="btn btn-secondary shrink-0" onClick={onClose}>
            {t("action.close")}
          </button>
        </div>
        <div className="mt-1 min-h-0 overflow-y-auto">
          {error ? <p className="mt-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p> : null}
          {notice ? <p className="mt-3 rounded bg-emerald-50 p-2 text-sm text-emerald-800">{notice}</p> : null}
          {/* min-w-0 trên các ô lưới: nội dung dài (SHA-256, tên thiết bị) không được nới rộng cột. */}
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <VersionHistoryList
              page={page}
              busy={busy}
              offset={offset}
              selectedId={selected?.id}
              onSelect={(version) => void selectVersion(version)}
              onPrev={() => void load(Math.max(0, offset - 20))}
              onNext={() => void load(offset + 20)}
            />
            <div className="min-w-0 rounded border p-3 text-sm">
              <VersionHistoryDetail selected={selected} busy={busy} onRestore={setConfirming} />
            </div>
          </div>
          {confirming ? (
            <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-3">
              <p className="font-medium">{t("history.restoreConfirm", { version: confirming.version_number })}</p>
              <p className="mt-1 text-sm text-slate-700">
                {t("history.restoreHelp", { version: confirming.version_number })}
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn btn-secondary" onClick={() => setConfirming(null)}>
                  {t("action.cancel")}
                </button>
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void confirmRestore()}>
                  {t("history.restore")}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
