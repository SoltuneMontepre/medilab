import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent as ReactMouseEvent } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { FolderRow } from "../../types";
import { categoryLabel, displayLocalPath } from "../../components";
import type { DropPoint } from "../../lib/tauri";

const MODE_KEYS: Record<string, MessageKey> = {
  upload_only: "folders.mode.upload_only",
  two_way: "folders.mode.two_way",
};

const MODE_SHORT_KEYS: Record<string, MessageKey> = {
  upload_only: "folders.modeShort.upload_only",
  two_way: "folders.modeShort.two_way",
};

/** Thao tác trên một thư mục đã thêm, dùng chung cho khung chi tiết và menu chuột phải. */
export type FolderActions = {
  busy: boolean;
  onOpen: (folderId: number) => void;
  onManageAccess: (remoteId: number, logicalRoot: string) => void;
  onUnregister: (folderId: number, logicalRoot: string) => void;
  onRebind: (folder: FolderRow) => void;
};

/** True khi thư mục cần người dùng xử lý: chưa gắn với máy chủ hoặc mất quyền. */
function needsAttention(folder: FolderRow): boolean {
  return folder.access_state === "unbound" || folder.access_state === "denied";
}

/** Tên thư mục trên máy, như trình quản lý tệp hiện. */
function folderName(folder: FolderRow): string {
  return displayLocalPath(folder.local_path).split(/[\\/]/).findLast(Boolean) ?? folder.logical_root;
}

/** Id và tên của dòng thư mục nằm dưới điểm thả, nếu có. */
export function dropFolderAt(point: DropPoint): { id: number; name: string } | null {
  const row = document.elementFromPoint(point.x, point.y)?.closest<HTMLElement>("[data-drop-folder-id]");
  return row ? { id: Number(row.dataset.dropFolderId), name: row.dataset.dropFolderName ?? "" } : null;
}

/** Biểu tượng thư mục màu vàng như trình quản lý tệp. */
function FolderIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 16" className="h-4 w-5 shrink-0">
      <path d="M1 3a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2z" fill="#f5c542" />
      <path d="M1 6h18v7a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2z" fill="#fbd96b" />
    </svg>
  );
}

/** Trạng thái gắn của một thư mục, gọn trong một ô của bảng. */
function StateLabel({ folder }: Readonly<{ folder: FolderRow }>) {
  const t = useT();
  if (folder.access_state === "unbound") {
    return <span className="text-amber-700">⚠ {t("folders.state.unbound")}</span>;
  }
  if (folder.access_state === "denied") {
    return <span className="text-amber-700">⚠ {t("folders.state.denied")}</span>;
  }
  return <span className="text-emerald-700">✓ {t("folders.state.ok")}</span>;
}

/** Khung chi tiết của thư mục đang chọn: mẫu, chế độ, lời giải thích trạng thái, đường dẫn và các
 * thao tác. */
export function FolderCard({ folder, busy, onOpen, onManageAccess, onUnregister, onRebind }: Readonly<{ folder: FolderRow } & FolderActions>) {
  const t = useT();
  const sample = folder.sample_name ?? folder.sample_code;
  const modeKey = folder.sync_mode ? MODE_KEYS[folder.sync_mode] : undefined;
  return (
    <div className="text-sm">
      <div className="font-medium">{folder.logical_root}</div>
      {sample ? (
        <div className="text-slate-700">
          {t("folders.sample")}: {sample}
          {folder.category ? ` · ${categoryLabel(t, folder.category)}` : ""}
        </div>
      ) : null}
      {folder.workflow_status ? (
        <div className="text-slate-600">
          {t("folders.workflow")}: {folder.workflow_status}
        </div>
      ) : null}
      {folder.instrument_label ? (
        <div className="text-slate-600">
          {t("folders.instrument")}: {folder.instrument_label}
        </div>
      ) : null}
      {modeKey ? <div className="text-slate-600">{t(modeKey)}</div> : null}
      {folder.access_state === "unbound" ? <div className="text-amber-700">{t("folders.unbound")}</div> : null}
      {folder.access_state === "denied" ? <div className="text-amber-700">{t("folders.denied")}</div> : null}
      <div className="break-words text-slate-600" title={folder.local_path}>
        {displayLocalPath(folder.local_path)}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {folder.access_state === "unbound" ? (
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => onRebind(folder)}>
            {t("folders.rebind")}
          </button>
        ) : null}
        <button type="button" className="btn btn-secondary" onClick={() => onOpen(folder.id)}>
          {t("folders.open")}
        </button>
        {folder.remote_id != null ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onManageAccess(folder.remote_id as number, folder.logical_root)}
          >
            {t("access.manage")}
          </button>
        ) : null}
        <button
          type="button"
          className="btn btn-danger"
          disabled={busy}
          onClick={() => onUnregister(folder.id, folder.logical_root)}
        >
          {t("folders.unregister")}
        </button>
      </div>
    </div>
  );
}

/** Menu chuột phải của một thư mục; bấm ra ngoài hoặc Esc để đóng. */
function FolderMenu({
  folder,
  x,
  y,
  actions,
  onClose,
}: Readonly<{ folder: FolderRow; x: number; y: number; actions: FolderActions; onClose: () => void }>) {
  const t = useT();
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    ref.current?.querySelector("button")?.focus();
    /** Đóng menu khi bấm ra ngoài nó. */
    function closeOnOutside(event: MouseEvent) {
      if (!ref.current?.contains(event.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", closeOnOutside);
    return () => document.removeEventListener("mousedown", closeOnOutside);
  }, [onClose]);

  const items: Array<{ label: string; run: () => void; danger?: boolean; disabled?: boolean }> = [
    { label: t("folders.open"), run: () => actions.onOpen(folder.id) },
  ];
  if (folder.access_state === "unbound") {
    items.push({ label: t("folders.rebind"), run: () => actions.onRebind(folder), disabled: actions.busy });
  }
  if (folder.remote_id != null) {
    const remoteId = folder.remote_id;
    items.push({ label: t("access.manage"), run: () => actions.onManageAccess(remoteId, folder.logical_root) });
  }
  items.push({
    label: t("folders.unregister"),
    run: () => actions.onUnregister(folder.id, folder.logical_root),
    danger: true,
    disabled: actions.busy,
  });

  return (
    <ul
      ref={ref}
      role="menu"
      className="fixed z-20 min-w-48 rounded border bg-white py-1 text-sm shadow-lg"
      style={{ left: Math.min(x, globalThis.innerWidth - 200), top: Math.min(y, globalThis.innerHeight - 40 * items.length - 16) }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onClose();
        }
      }}
    >
      {items.map((item) => (
        <li key={item.label} role="none">
          <button
            type="button"
            role="menuitem"
            disabled={item.disabled}
            className={`w-full px-3 py-1.5 text-left hover:bg-slate-100 disabled:opacity-50 ${item.danger ? "text-red-700" : ""}`}
            onClick={() => {
              onClose();
              item.run();
            }}
          >
            {item.label}
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Bảng thư mục đã thêm kiểu trình quản lý tệp: mỗi mẫu một dòng mở/gập được, bên dưới là thư mục
 * của mẫu; thư mục không thuộc mẫu nằm ở nhóm cuối. Bấm để chọn, bấm đúp hoặc Enter để mở, chuột
 * phải hoặc Shift+F10 để xem thao tác. Dòng `dropFolderId` được tô khi người dùng kéo tệp qua. */
export function FolderExplorer({
  folders,
  dropFolderId,
  ...actions
}: Readonly<{ folders: FolderRow[]; dropFolderId: number | null } & FolderActions>) {
  const t = useT();
  // Nhóm người dùng đã tự mở/gập; nhóm chưa đụng tới mở sẵn nếu lần đầu thấy nó đang cần xử lý, và
  // giữ nguyên như thế sau đó để nhóm không tự gập lại ngay khi vừa Gắn lại xong.
  const [toggled, setToggled] = useState<Map<string, boolean>>(new Map());
  const firstSeenOpen = useRef(new Map<string, boolean>());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [menu, setMenu] = useState<{ folder: FolderRow; x: number; y: number } | null>(null);

  const groups = new Map<string, FolderRow[]>();
  for (const folder of folders) {
    const key = folder.sample_code ?? "";
    groups.set(key, [...(groups.get(key) ?? []), folder]);
  }
  const ordered = [...groups].sort(([a], [b]) => (a === "" ? 1 : 0) - (b === "" ? 1 : 0));
  const selected = folders.find((folder) => folder.id === selectedId);

  /** Nhóm của một mẫu đang mở hay gập. */
  function isOpen(code: string, rows: FolderRow[]): boolean {
    if (!firstSeenOpen.current.has(code)) {
      firstSeenOpen.current.set(code, rows.some(needsAttention));
    }
    return toggled.get(code) ?? firstSeenOpen.current.get(code) ?? false;
  }

  /** Mở hoặc gập nhóm của một mẫu. */
  function toggle(code: string, open: boolean) {
    setToggled((current) => new Map(current).set(code, !open));
  }

  /** Chuột phải trên một dòng: chọn dòng và mở menu tại con trỏ. */
  function openMenu(event: ReactMouseEvent, folder: FolderRow) {
    event.preventDefault();
    setSelectedId(folder.id);
    setMenu({ folder, x: event.clientX, y: event.clientY });
  }

  /** Bàn phím trên một dòng: Enter mở thư mục, phím Menu hoặc Shift+F10 mở menu thao tác. */
  function handleRowKey(event: KeyboardEvent<HTMLTableRowElement>, folder: FolderRow) {
    if (event.key === "Enter") {
      actions.onOpen(folder.id);
    } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      setSelectedId(folder.id);
      setMenu({ folder, x: rect.left + 24, y: rect.bottom });
    }
  }

  return (
    <div>
      <table className="w-full table-fixed text-left text-sm">
        <thead className="border-b text-slate-500">
          <tr>
            <th className="w-1/2 px-2 py-1.5 font-normal">{t("folders.col.name")}</th>
            <th className="px-2 py-1.5 font-normal">{t("folders.col.category")}</th>
            <th className="px-2 py-1.5 font-normal">{t("folders.col.mode")}</th>
            <th className="px-2 py-1.5 font-normal">{t("folders.col.state")}</th>
          </tr>
        </thead>
        {ordered.map(([code, rows]) => {
          const open = isOpen(code, rows);
          return (
            <tbody key={code}>
              <tr className="hover:bg-slate-50">
                <td className="px-2 py-1.5" colSpan={2}>
                  <button
                    type="button"
                    aria-expanded={open}
                    className="flex w-full items-center gap-2 text-left font-medium"
                    onClick={() => toggle(code, open)}
                  >
                    <span aria-hidden="true" className="w-3 text-slate-500">
                      {open ? "▾" : "▸"}
                    </span>
                    <FolderIcon />
                    <span className="truncate">{code || t("folders.otherGroup")}</span>
                  </button>
                </td>
                <td className="px-2 py-1.5 text-slate-500">{t("folders.groupCount", { count: rows.length })}</td>
                <td className="px-2 py-1.5">
                  {rows.some(needsAttention) ? (
                    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
                      {t("folders.groupAttention")}
                    </span>
                  ) : null}
                </td>
              </tr>
              {open
                ? rows.map((folder) => {
                    const isSelected = folder.id === selectedId;
                    const isDropTarget = folder.id === dropFolderId;
                    let rowTone = "hover:bg-slate-50";
                    if (isDropTarget) {
                      rowTone = "bg-blue-100 outline outline-2 -outline-offset-2 outline-blue-500";
                    } else if (isSelected) {
                      rowTone = "bg-blue-50";
                    }
                    return (
                      <tr
                        key={folder.id}
                        tabIndex={0}
                        aria-selected={isSelected}
                        data-drop-folder-id={folder.id}
                        data-drop-folder-name={folderName(folder)}
                        title={displayLocalPath(folder.local_path)}
                        className={`cursor-default select-none ${rowTone}`}
                        onClick={() => setSelectedId(folder.id)}
                        onDoubleClick={() => actions.onOpen(folder.id)}
                        onContextMenu={(event) => openMenu(event, folder)}
                        onKeyDown={(event) => handleRowKey(event, folder)}
                      >
                        <td className="px-2 py-1.5 pl-9">
                          <span className="flex items-center gap-2">
                            <FolderIcon />
                            <span className="truncate">{folderName(folder)}</span>
                          </span>
                        </td>
                        <td className="truncate px-2 py-1.5 text-slate-600">
                          {folder.category ? categoryLabel(t, folder.category) : "—"}
                        </td>
                        <td className="truncate px-2 py-1.5 text-slate-600">
                          {folder.sync_mode && MODE_SHORT_KEYS[folder.sync_mode] ? t(MODE_SHORT_KEYS[folder.sync_mode]) : "—"}
                        </td>
                        <td className="truncate px-2 py-1.5">
                          <StateLabel folder={folder} />
                        </td>
                      </tr>
                    );
                  })
                : null}
            </tbody>
          );
        })}
      </table>
      <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-3">
        {selected ? (
          <FolderCard folder={selected} {...actions} />
        ) : (
          <p className="text-sm text-slate-500">{t("folders.selectHint")}</p>
        )}
      </div>
      {menu ? (
        <FolderMenu folder={menu.folder} x={menu.x} y={menu.y} actions={actions} onClose={() => setMenu(null)} />
      ) : null}
    </div>
  );
}
