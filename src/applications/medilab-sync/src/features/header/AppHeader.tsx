import type { ReactNode } from "react";
import type { Locale } from "../../i18n";
import { LanguageSwitch } from "../../components";
import { useT } from "../../locale";
import type { StatusDto } from "../../types";

/**
 * Thanh đầu trang kiểu thanh điều hướng của Odoo: tên app, các tab (`children`), người dùng +
 * trạng thái, đổi ngôn ngữ, tạm dừng, đăng xuất.
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
  children,
}: Readonly<{
  status: StatusDto;
  busy: boolean;
  toggleBusy: boolean;
  locale: string | undefined;
  onLocaleChange: (locale: Locale) => void;
  onToggleSync: () => void;
  onLogout: () => void;
  children?: ReactNode;
}>) {
  const t = useT();
  const flags = [
    status.user_name || t("app.technician"),
    status.degraded ? t("app.degraded") : "",
    status.paused ? t("app.paused") : "",
  ].filter(Boolean);
  return (
    <header className="navbar flex h-13 items-stretch gap-2 px-3 shadow-sm">
      <h1 className="flex items-center px-2 text-base font-semibold">{t("app.title")}</h1>
      {children}
      <div className="ml-auto flex items-center gap-2">
        <p className="max-w-64 truncate text-xs text-white/80" title={flags.join(" · ")}>
          {flags.join(" · ")}
        </p>
        <LanguageSwitch locale={locale} onChange={onLocaleChange} />
        <button type="button" className="btn btn-secondary" disabled={toggleBusy} onClick={onToggleSync}>
          {status.paused ? t("action.resume") : t("action.pause")}
        </button>
        <button type="button" className="btn btn-danger" disabled={busy} onClick={onLogout}>
          {t("action.logout")}
        </button>
      </div>
    </header>
  );
}
