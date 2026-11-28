import { useEffect, useState } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { SharedFolder, StatusDto, UnboundFolders } from "../../types";
import { bindSharedFolder, chooseSyncFolder, listSharedFolders } from "../../lib/tauri";
import { categoryLabel } from "../../components";

const EMPTY: UnboundFolders = { shared: [], owned: [] };

/** Nhãn hiển thị cho tư cách của mình trên folder chưa gắn. */
function roleLabelKey(role?: string | null): MessageKey {
  return role === "owner" ? "access.role.owner" : "access.role.upload";
}

/** Các folder trên server mà máy này chưa gắn: `shared` = người khác chia sẻ, `owned` = của chính
 * mình (ví dụ sau khi bấm "Ngừng đồng bộ"). Tải lại khi số folder đã gắn đổi. `bind` cho người
 * dùng chọn thư mục trên máy rồi gắn folder vào đó bằng ID trên server — không gõ tên, nên không
 * tạo folder trùng lặp trên server.
 *
 * Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-manage-members */
export function useUnboundFolders(boundCount: number, onBound: (status: StatusDto) => void) {
  const [folders, setFolders] = useState<UnboundFolders>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listSharedFolders()
      .then((rows) => {
        if (!cancelled) {
          setFolders(rows);
        }
      })
      .catch(() => {
        // Offline/hết phiên: banner chung của app đã báo; ở đây chỉ không hiện danh sách.
        if (!cancelled) {
          setFolders(EMPTY);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [boundCount]);

  /** Cho người dùng chọn thư mục trên máy rồi gắn folder chưa gắn vào đó. */
  async function bind(folder: SharedFolder) {
    setError(null);
    setBusy(true);
    try {
      const localPath = await chooseSyncFolder();
      if (!localPath) {
        return;
      }
      onBound(await bindSharedFolder({ remote_id: folder.id, local_path: localPath, recursive: true }));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return { folders, error, busy, bind };
}

/** Danh sách folder trên server chưa gắn ở máy này, mỗi dòng một nút chọn thư mục trên máy để gắn. */
export function UnboundFolderList({
  rows,
  busy,
  onBind,
}: Readonly<{ rows: SharedFolder[]; busy: boolean; onBind: (folder: SharedFolder) => void }>) {
  const t = useT();
  return (
    <ul className="space-y-2 text-sm">
      {rows.map((folder) => (
        <li key={folder.id} className="flex items-start justify-between gap-3 rounded border p-3">
          <div>
            <div className="font-medium">{folder.name || folder.logical_root}</div>
            <div className="text-xs text-slate-600">
              {t("access.owner")}: {folder.owner_name ?? "—"} · {t("access.myRole")}:{" "}
              {t(roleLabelKey(folder.my_role))}
            </div>
            {folder.sample_name || folder.sample_code || folder.category ? (
              <div className="text-xs text-slate-600">
                {t("folders.sample")}: {folder.sample_name ?? folder.sample_code ?? "—"}
                {folder.category ? ` · ${categoryLabel(t, folder.category)}` : ""}
              </div>
            ) : null}
          </div>
          <button type="button" className="btn btn-secondary shrink-0" disabled={busy} onClick={() => onBind(folder)}>
            {t("shared.bind")}
          </button>
        </li>
      ))}
    </ul>
  );
}
