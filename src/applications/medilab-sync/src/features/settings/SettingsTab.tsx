import { withSettingsPatch } from "./settingsPatch";
import { useEffect, useState, type SubmitEvent } from "react";
import { useT } from "../../locale";
import type { Locale } from "../../i18n";
import type { AppSettings } from "../../types";
import { checkUpdate, DEFAULT_APP_VERSION, getAppVersion, type UpdateAvailable } from "../../lib/tauri";
import { LanguageSwitch, ToggleSwitch } from "../../components";

/** Thuộc tính đầu vào của tab Cài đặt: cấu hình app hiện tại và các callback thay đổi/lưu/kiểm tra cập nhật. */
type SettingsTabProps = {
  settings: AppSettings;
  busy: boolean;
  onChange: (settings: AppSettings) => void;
  onLocaleChange: (locale: Locale) => void;
  onUpdateFound: (info: UpdateAvailable) => void;
  onSubmit: (event: SubmitEvent) => void;
};

/** Tab Cài đặt: cấu hình app và nút kiểm tra cập nhật thủ công. */
export function SettingsTab({
  settings,
  busy,
  onChange,
  onLocaleChange,
  onUpdateFound,
  onSubmit,
}: Readonly<SettingsTabProps>) {
  const t = useT();
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [updateStatusText, setUpdateStatusText] = useState<string | null>(null);
  const [appVersion, setAppVersion] = useState<string>(DEFAULT_APP_VERSION);

  useEffect(() => {
    let cancelled = false;
    // Đọc phiên bản từ metadata của tiến trình Tauri đang chạy
    void getAppVersion().then((version) => {
      if (!cancelled && version) {
        setAppVersion(version);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Kiểm tra cập nhật thủ công; báo cha nếu có bản mới, hoặc hiện thông báo đã cập nhật/lỗi. */
  async function handleManualCheck() {
    setCheckingUpdate(true);
    setUpdateStatusText(null);
    try {
      const update = await checkUpdate();
      if (update) {
        onUpdateFound(update);
      } else {
        setUpdateStatusText(t("update.upToDate"));
      }
    } catch {
      setUpdateStatusText(t("update.checkFailed"));
    } finally {
      setCheckingUpdate(false);
    }
  }

  return (
    <form className="max-w-xl space-y-5 rounded-lg border bg-white p-4" onSubmit={onSubmit}>
      <section className="space-y-4">
        <h2 className="font-semibold">{t("settings.section.general")}</h2>
        <ToggleSwitch
          checked={settings.autostart}
          label={t("settings.autostart")}
          hint={t("settings.autostartHint")}
          onChange={(autostart) => onChange(withSettingsPatch(settings, { autostart }))}
        />
        <LanguageSwitch
          locale={settings.locale}
          onChange={(locale) => {
            onChange(withSettingsPatch(settings, { locale }));
            onLocaleChange(locale);
          }}
        />
      </section>
      <section className="space-y-4 border-t border-slate-200 pt-4">
        <h2 className="font-semibold">{t("settings.section.connection")}</h2>
        <label className="block text-sm">
          <span className="font-medium">{t("settings.odoo")}</span>
          <input
            className="mt-1 w-full rounded border px-3 py-2"
            value={settings.odoo_url}
            onChange={(event) => onChange(withSettingsPatch(settings, { odoo_url: event.target.value }))}
          />
          <p className="mt-1 text-xs text-slate-500">{t("settings.odooHint")}</p>
        </label>
      </section>
      <section className="space-y-4 border-t border-slate-200 pt-4">
        <div>
          <h2 className="font-semibold">{t("settings.section.timing")}</h2>
          <p className="text-xs text-slate-500">{t("settings.section.timingHint")}</p>
        </div>
        <label className="block text-sm">
          <span className="font-medium">{t("settings.debounce")}</span>
          <input
            type="number"
            className="mt-1 w-full rounded border px-3 py-2"
            value={settings.debounce_ms}
            onChange={(event) => onChange(withSettingsPatch(settings, { debounce_ms: Number(event.target.value) }))}
          />
          <p className="mt-1 text-xs text-slate-500">{t("settings.debounceHint")}</p>
        </label>
        <label className="block text-sm">
          <span className="font-medium">{t("settings.reconcile")}</span>
          <input
            type="number"
            className="mt-1 w-full rounded border px-3 py-2"
            value={settings.reconcile_secs}
            onChange={(event) => onChange(withSettingsPatch(settings, { reconcile_secs: Number(event.target.value) }))}
          />
          <p className="mt-1 text-xs text-slate-500">{t("settings.reconcileHint")}</p>
        </label>
        <label className="block text-sm">
          <span className="font-medium">{t("settings.poll")}</span>
          <input
            type="number"
            className="mt-1 w-full rounded border px-3 py-2"
            value={settings.change_poll_secs ?? 15}
            onChange={(event) =>
              onChange(withSettingsPatch(settings, { change_poll_secs: Number(event.target.value) }))
            }
          />
          <p className="mt-1 text-xs text-slate-500">{t("settings.pollHint")}</p>
        </label>
      </section>
      <p className="border-t border-slate-200 pt-4 text-sm text-slate-600">
        {t("settings.device", { version: appVersion ? `${appVersion}` : "" })}
      </p>
      <div className="flex items-center justify-between pt-2 border-t border-slate-200">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={checkingUpdate || busy}
            onClick={() => void handleManualCheck()}
          >
            {checkingUpdate ? t("update.checking") : t("update.check")}
          </button>
          {updateStatusText ? (
            <span className="text-sm text-slate-600">{updateStatusText}</span>
          ) : null}
        </div>
        <button className="btn btn-primary" disabled={busy} type="submit">
          {t("settings.save")}
        </button>
      </div>
    </form>
  );
}
