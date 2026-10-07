import { useEffect, useState } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { FolderMember, FolderMembers, MemberUser } from "../../types";
import {
  addFolderMember,
  listFolderMembers,
  removeFolderMember,
  searchMemberCandidates,
} from "../../lib/tauri";

const SEARCH_MIN_CHARS = 2;
const SEARCH_DEBOUNCE_MS = 300;

/** Nhãn hiển thị cho key vai trò lưu trên server. `upload` là thành viên đọc + ghi, không phải
 * "chỉ tải lên".
 *
 * Luật nghiệp vụ: docs/business/file-sync-governance.md#who-may-manage-members */
function roleLabelKey(role: string): MessageKey {
  if (role === "owner") {
    return "access.role.owner";
  }
  if (role === "manager") {
    return "access.role.manager";
  }
  return "access.role.upload";
}

/** Một dòng thành viên: tên + login, vai trò, có truy cập được thật không, và nút gỡ (nếu được). */
function MemberRow({
  member,
  removable,
  busy,
  onRemove,
}: Readonly<{
  member: FolderMember;
  removable: boolean;
  busy: boolean;
  onRemove: (memberId: number, name: string) => void;
}>) {
  const t = useT();
  return (
    <li className="flex items-center justify-between gap-3 p-2 text-sm">
      <div>
        <div className="font-medium">
          {member.user.name}
          {member.user.login ? (
            <span className="ml-2 text-xs font-normal text-slate-500">{member.user.login}</span>
          ) : null}
        </div>
        <div className="text-xs text-slate-500">{t(roleLabelKey(member.role))}</div>
        <div className={member.effective_access ? "text-xs text-emerald-700" : "text-xs text-amber-700"}>
          {t(member.effective_access ? "access.effective.ok" : "access.effective.noSample")}
        </div>
      </div>
      {removable ? (
        <button
          type="button"
          className="btn btn-danger px-2 py-1"
          disabled={busy}
          onClick={() => onRemove(member.id, member.user.name)}
        >
          {t("access.remove")}
        </button>
      ) : null}
    </li>
  );
}

/** Ô tìm và danh sách ứng viên để thêm thành viên (chỉ hiện cho chủ sở hữu/Sync Manager). */
function AddMemberPanel({
  query,
  candidates,
  busy,
  onQueryChange,
  onAdd,
}: Readonly<{
  query: string;
  candidates: MemberUser[] | null;
  busy: boolean;
  onQueryChange: (value: string) => void;
  onAdd: (userId: number) => void;
}>) {
  const t = useT();
  return (
    <div className="mt-4">
      <label className="text-sm font-semibold" htmlFor="access-search">
        {t("access.add")}
      </label>
      <input
        id="access-search"
        type="text"
        className="mt-1 w-full rounded border px-2 py-1 text-sm"
        placeholder={t("access.searchPlaceholder")}
        value={query}
        disabled={busy}
        onChange={(event) => onQueryChange(event.target.value)}
      />
      {candidates?.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">{t("access.noCandidates")}</p>
      ) : null}
      {candidates?.length ? (
        <ul className="mt-2 divide-y rounded border">
          {candidates.map((user) => (
            <li key={user.id} className="flex items-center justify-between gap-3 p-2 text-sm">
              <div>
                {user.name}
                {user.login ? <span className="ml-2 text-xs text-slate-500">{user.login}</span> : null}
              </div>
              <button
                type="button"
                className="btn btn-secondary px-2 py-1"
                disabled={busy}
                onClick={() => onAdd(user.id)}
              >
                {t("access.addAction")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Thuộc tính đầu vào của dialog quyền truy cập: folder trên server và callback đóng. */
type AccessDialogProps = Readonly<{
  remoteId: number;
  label: string;
  onClose: () => void;
}>;

/** Dialog quyền truy cập của một folder. Chủ sở hữu/Sync Manager thấy đủ thành viên, thêm và gỡ
 * được; thành viên thường chỉ xem chủ sở hữu và tư cách của mình. Ẩn/hiện nút ở đây không phải
 * phân quyền — server kiểm lại ở từng lần gọi. */
export function AccessDialog({ remoteId, label, onClose }: AccessDialogProps) {
  const t = useT();
  const [info, setInfo] = useState<FolderMembers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<MemberUser[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listFolderMembers(remoteId)
      .then((next) => {
        if (!cancelled) {
          setInfo(next);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [remoteId]);

  // Tìm ứng viên: chờ người dùng ngừng gõ, tối thiểu 2 ký tự (server cũng ép giới hạn này).
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < SEARCH_MIN_CHARS) {
      setCandidates(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      searchMemberCandidates(remoteId, trimmed)
        .then((rows) => {
          if (!cancelled) {
            setCandidates(rows);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setError(String(err));
          }
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, remoteId]);

  /** Chạy một thao tác đổi thành viên, cập nhật danh sách và thông báo kết quả. */
  async function mutate(action: () => Promise<FolderMembers>, doneKey: MessageKey) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setInfo(await action());
      setNotice(t(doneKey));
      setQuery("");
      setCandidates(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  /** Gỡ một thành viên sau khi người dùng xác nhận. */
  function handleRemove(memberId: number, name: string) {
    if (!window.confirm(t("access.removeConfirm", { name }))) {
      return;
    }
    void mutate(() => removeFolderMember(remoteId, memberId), "access.removed");
  }

  const canManage = info?.can_manage_members ?? false;

  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center overflow-auto bg-slate-900/40 p-6">
      <div className="w-full max-w-2xl rounded-lg border bg-white p-4 shadow-lg">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{t("access.title")}</h2>
            <p className="text-sm text-slate-600">{label}</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            {t("action.close")}
          </button>
        </div>
        {error ? <p className="mt-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p> : null}
        {notice ? (
          <p className="mt-3 rounded bg-emerald-50 p-2 text-sm text-emerald-800">{notice}</p>
        ) : null}
        {!info && !error ? <p className="mt-3 text-sm text-slate-500">{t("access.loading")}</p> : null}
        {info ? (
          <>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-500">{t("access.owner")}</dt>
              <dd>{info.owner.name}</dd>
              <dt className="text-slate-500">{t("access.myRole")}</dt>
              <dd>{t(roleLabelKey(info.my_role))}</dd>
            </dl>
            {info.mapped ? (
              <p className="mt-3 rounded bg-amber-50 p-2 text-sm text-amber-800">
                {t("access.mappedHint")}
              </p>
            ) : null}
            <h3 className="mt-4 text-sm font-semibold">{t("access.members")}</h3>
            <p className="text-xs text-slate-500">{t("access.memberHint")}</p>
            <ul className="mt-2 divide-y rounded border">
              {info.members.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  removable={canManage && member.role !== "owner"}
                  busy={busy}
                  onRemove={handleRemove}
                />
              ))}
            </ul>
            {canManage ? (
              <AddMemberPanel
                query={query}
                candidates={candidates}
                busy={busy}
                onQueryChange={setQuery}
                onAdd={(userId) => void mutate(() => addFolderMember(remoteId, userId), "access.added")}
              />
            ) : (
              <p className="mt-4 text-sm text-slate-600">{t("access.readOnlyHint")}</p>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
