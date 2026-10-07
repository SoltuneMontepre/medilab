import { useState } from "react";
import { useT } from "../../locale";
import { downloadAndInstallUpdate, dismissUpdateSession, type UpdateAvailable } from "../../lib/tauri";

type Phase = "confirm" | "downloading" | "ready" | "error";

/** Thuộc tính đầu vào của dialog cập nhật: bản cập nhật đang chờ và callback đóng dialog. */
type UpdateDialogProps = Readonly<{
  info: UpdateAvailable;
  onDismiss: () => void;
}>;

/** Dialog xác nhận cài đặt bản cập nhật: xác nhận → đang tải → sẵn sàng, hoặc báo lỗi. */
export function UpdateDialog({ info, onDismiss }: UpdateDialogProps) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>("confirm");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  /** Bỏ qua nhắc cập nhật cho phiên chạy này và đóng dialog. */
  function handleLater() {
    dismissUpdateSession();
    onDismiss();
  }

  /** Tải và cài bản cập nhật, theo dõi giai đoạn (đang tải/sẵn sàng/lỗi). */
  async function handleInstall() {
    setPhase("downloading");
    try {
      await downloadAndInstallUpdate();
      setPhase("ready");
    } catch (err) {
      setErrorMsg(String(err));
      setPhase("error");
    }
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-900/40 p-6">
      <div className="w-full max-w-md rounded-lg border bg-white p-5 shadow-lg">
        <h2 className="text-lg font-semibold">{t("update.dialogTitle")}</h2>

        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex gap-2">
            <dt className="font-medium text-slate-600">{t("update.currentVersion")}:</dt>
            <dd>{info.current_version}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-slate-600">{t("update.newVersion")}:</dt>
            <dd className="font-semibold">{info.new_version}</dd>
          </div>
          {info.pub_date ? (
            <div className="flex gap-2">
              <dt className="font-medium text-slate-600">{t("update.releaseNotes")}:</dt>
              <dd>{info.pub_date}</dd>
            </div>
          ) : null}
        </dl>

        {info.notes ? (
          <p className="mt-3 rounded border bg-slate-50 px-3 py-2 text-sm whitespace-pre-wrap">
            {info.notes}
          </p>
        ) : null}

        {phase === "confirm" ? (
          <div className="mt-5 flex gap-2 justify-end">
            <button type="button" className="btn btn-secondary" onClick={handleLater}>
              {t("update.later")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleInstall()}
            >
              {t("update.installNow")}
            </button>
          </div>
        ) : null}

        {phase === "downloading" ? (
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-700">
            <span className="sync-spinner" aria-hidden="true" />
            <span>{t("update.downloading")}</span>
          </div>
        ) : null}

        {phase === "ready" ? (
          <p className="mt-4 rounded bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {t("update.ready")}
          </p>
        ) : null}

        {phase === "error" ? (
          <div className="mt-4 space-y-2">
            <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{errorMsg}</p>
            <div className="flex justify-end">
              <button type="button" className="btn btn-secondary" onClick={onDismiss}>
                {t("action.close")}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
