import { describe, expect, test } from "bun:test";
import React from "react";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import { translate } from "../../i18n";
import type { AppSettings } from "../../types";
import { SettingsTab } from "./SettingsTab";

/** Helper bọc component bằng LocaleProvider để test render html. */
function renderWithLocale(element: React.ReactElement, locale: "vi" | "en" = "vi"): string {
  return renderToString(<LocaleProvider locale={locale}>{element}</LocaleProvider>);
}

/** Cài đặt mẫu phục vụ kiểm thử render SettingsTab. */
function createMockSettings(): AppSettings {
  return {
    odoo_url: "https://odoo.example.com",
    autostart: true,
    debounce_ms: 1000,
    reconcile_secs: 300,
    change_poll_secs: 15,
    paused: false,
    locale: "vi",
  };
}

describe("SettingsTab and version display", () => {
  test("i18n settings.device chèn chính xác tham số phiên bản", () => {
    // Kiểm tra định dạng chuỗi tiếng Việt với tham số phiên bản động
    const viText = translate("vi", "settings.device", { version: "0.1.3" });
    expect(viText).toBe("Phiên bản ứng dụng: MediLab File Sync 0.1.3");

    // Kiểm tra định dạng chuỗi tiếng Anh với tham số phiên bản động
    const enText = translate("en", "settings.device", { version: "0.1.3" });
    expect(enText).toBe("App version: MediLab File Sync 0.1.3");
  });

  test("SettingsTab render hiển thị phiên bản ứng dụng mặc định", () => {
    const settings = createMockSettings();
    const html = renderWithLocale(
      <SettingsTab
        settings={settings}
        busy={false}
        onChange={() => {}}
        onLocaleChange={() => {}}
        onUpdateFound={() => {}}
        onSubmit={(e) => e.preventDefault()}
      />,
    );

    // Xác nhận chuỗi phiên bản xuất hiện trong giao diện cài đặt
    expect(html).toContain("Phiên bản ứng dụng: MediLab File Sync");
    expect(html).toContain("0.1.3");
  });
});
