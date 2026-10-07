import { useT } from "../../locale";

/** Màn hình khi kho mật khẩu của hệ điều hành đang khóa: mời mở khóa rồi thử lại, hoặc chủ động
 * đăng nhập bằng mật khẩu. Không phải "phiên hết hạn". */
export function CredentialStoreLockedScreen({
  busy,
  error,
  onUsePassword,
  onRetry,
}: Readonly<{ busy: boolean; error: string | null; onUsePassword: () => void; onRetry: () => void }>) {
  const t = useT();
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md space-y-4 rounded-lg border bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold">{t("keyring.lockedTitle")}</h1>
        <p className="text-sm text-slate-700">{t("keyring.lockedBody")}</p>
        <p className="text-sm text-slate-600">{t("keyring.lockedSafe")}</p>
        {error ? <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={onUsePassword}>
            {t("keyring.usePassword")}
          </button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onRetry}>
            {busy ? t("keyring.retrying") : t("keyring.retry")}
          </button>
        </div>
      </div>
    </main>
  );
}
