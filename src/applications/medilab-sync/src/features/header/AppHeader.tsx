import type { Locale } from "../../i18n";
import { LanguageSwitch } from "../../components";
import { useT } from "../../locale";
import type { StatusDto } from "../../types";

/**
 * Thanh đầu trang: tên app, người dùng + máy chủ + trạng thái, đổi ngôn ngữ, tạm dừng, đăng xuất.
 *
 * Nút Tạm dừng/Tiếp tục chỉ bị khóa khi CHÍNH lệnh đó đang chạy (`toggleBusy`), không theo `busy`
 * chung của app: các lệnh khác (gắn thư mục, đối soát…) có thể chạy lâu trong lúc transfer đang
 * chạy, và người dùng phải luôn dừng được transfer. Nhãn theo cờ tạm dừng của engine.
 */
export function AppHeader({
  status,
  busy,
  toggleBusy,
  locale,
  onLocaleChange,
  onToggleSync,
  onLogout,
}: Readonly<{
  status: StatusDto;
  busy: boolean;
  toggleBusy: boolean;
  locale: string | undefined;
  onLocaleChange: (locale: Locale) => void;
  onToggleSync: () => void;
  onLogout: () => void;
}>) {
  const t = useT();
  const flags = [
    status.user_name || t("app.technician"),
    status.odoo_url,
    status.degraded ? t("app.degraded") : "",
    status.paused ? t("app.paused") : "",
  ].filter(Boolean);
  return (
    <header className="flex items-center justify-between border-b bg-white px-6 py-3">
      <div>
        <h1 className="text-lg font-semibold">{t("app.title")}</h1>
        <p className="text-sm text-slate-600">{flags.join(" · ")}</p>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <LanguageSwitch locale={locale} onChange={onLocaleChange} />
        <button type="button" className="btn btn-secondary" disabled={toggleBusy} onClick={onToggleSync}>
          {status.paused ? t("action.resume") : t("action.pause")}
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={onLogout}>
          {t("action.logout")}
        </button>
      </div>
    </header>
  );
}
