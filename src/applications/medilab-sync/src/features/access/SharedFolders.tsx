import { useEffect, useState } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { SharedFolder, StatusDto, UnboundFolders } from "../../types";
import { bindSharedFolder, chooseSyncFolder, listSharedFolders } from "../../lib/tauri";

const EMPTY: UnboundFolders = { shared: [], owned: [] };

/** Nhãn hiển thị cho tư cách của mình trên folder chưa gắn. */
function roleLabelKey(role?: string | null): MessageKey {
  return role === "owner" ? "access.role.owner" : "access.role.upload";
}

/** Thuộc tính đầu vào: số folder đã gắn cục bộ (đổi thì tải lại danh sách) và callback nhận trạng
 * thái mới sau khi gắn. */
type SharedFoldersProps = Readonly<{
  boundCount: number;
  onBound: (status: StatusDto) => void;
}>;

/** Khối folder trên server mà máy này chưa gắn: "Được chia sẻ với bạn" và "Thư mục của bạn chưa
 * đồng bộ trên máy này" (ví dụ sau khi bấm "Ngừng đồng bộ"). Gắn bằng ID của folder trên server —
 * người dùng chỉ chọn thư mục trên máy, không gõ tên, nên không tạo folder trùng lặp trên server.
 *
 * Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-manage-members */
export function SharedFolders({ boundCount, onBound }: SharedFoldersProps) {
  const t = useT();
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

  /** Cho người dùng chọn thư mục trên máy rồi gắn folder chia sẻ vào đó. */
  async function handleBind(folder: SharedFolder) {
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

  if (folders.shared.length === 0 && folders.owned.length === 0 && !error) {
    return null;
  }

  const groups: Array<[MessageKey, MessageKey, SharedFolder[]]> = [
    ["shared.title", "shared.hint", folders.shared],
    ["shared.ownedTitle", "shared.ownedHint", folders.owned],
  ];

  return (
    <div className="rounded-lg border bg-white p-4 lg:col-span-2">
      {error ? <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p> : null}
      {groups.map(([titleKey, hintKey, rows]) =>
        rows.length === 0 ? null : (
          <div key={titleKey} className="mb-4 last:mb-0">
            <h2 className="font-semibold">{t(titleKey)}</h2>
            <p className="text-xs text-slate-500">{t(hintKey)}</p>
            <ul className="mt-3 space-y-2 text-sm">
              {rows.map((folder) => (
                <li
                  key={folder.id}
                  className="flex items-start justify-between gap-3 rounded border p-3"
                >
                  <div>
                    <div className="font-medium">{folder.name || folder.logical_root}</div>
                    <div className="text-xs text-slate-600">
                      {t("access.owner")}: {folder.owner_name ?? "—"} · {t("access.myRole")}:{" "}
                      {t(roleLabelKey(folder.my_role))}
                    </div>
                    {folder.sample_name || folder.category ? (
                      <div className="text-xs text-slate-600">
                        {t("folders.sample")}: {folder.sample_name ?? "—"}
                        {folder.category ? ` · ${folder.category}` : ""}
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => void handleBind(folder)}
                  >
                    {t("shared.bind")}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
    </div>
  );
}
