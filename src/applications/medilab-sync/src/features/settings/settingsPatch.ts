import type { AppSettings } from "../../types";

/**
 * Áp một thay đổi lên cấu hình mà GIỮ NGUYÊN mọi field khác, kể cả field ẩn không có trên form
 * (`upload_concurrency`, `download_concurrency`, `part_concurrency`) hay field của bản app mới hơn:
 * backend lưu đúng object nhận được, nên rơi field nào là mất giá trị đó.
 */
export function withSettingsPatch(settings: AppSettings, patch: Partial<AppSettings>): AppSettings {
  return { ...settings, ...patch };
}
