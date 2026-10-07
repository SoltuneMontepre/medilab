import { expect, test } from "bun:test";
import type { AppSettings } from "../../types";
import { withSettingsPatch } from "./settingsPatch";

/** Cấu hình như `get_settings` trả về, gồm cả field ẩn không có trên form. */
function storedSettings(): AppSettings {
  return {
    odoo_url: "https://odoo.example.com",
    autostart: false,
    debounce_ms: 1000,
    reconcile_secs: 600,
    change_poll_secs: 15,
    paused: false,
    locale: "vi",
    upload_concurrency: 2,
    download_concurrency: 4,
    part_concurrency: 1,
  };
}

test("sửa field hiển thị giữ nguyên các setting concurrency ẩn", () => {
  const stored = storedSettings();
  const edited = withSettingsPatch(withSettingsPatch(stored, { debounce_ms: 1500 }), { locale: "en" });
  expect(edited.debounce_ms).toBe(1500);
  expect(edited.locale).toBe("en");
  expect(edited.upload_concurrency).toBe(2);
  expect(edited.download_concurrency).toBe(4);
  expect(edited.part_concurrency).toBe(1);
  expect(stored.debounce_ms).toBe(1000);
});

test("field không biết tới (bản app mới hơn) cũng được giữ khi lưu lại", () => {
  const stored = { ...storedSettings(), future_field: "keep" } as AppSettings;
  const edited = withSettingsPatch(stored, { autostart: true }) as AppSettings & { future_field: string };
  expect(edited.future_field).toBe("keep");
  expect(edited.autostart).toBe(true);
});
