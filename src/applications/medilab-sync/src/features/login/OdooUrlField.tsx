import { useState } from "react";
import { useT } from "../../locale";

const HISTORY_KEY = "odooUrlHistory";
const HISTORY_MAX = 8;

/** Đọc danh sách URL Odoo đã đăng nhập thành công (mới nhất trước) từ localStorage. */
export function loadOdooUrlHistory(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((url): url is string => typeof url === "string") : [];
  } catch {
    return [];
  }
}

/** Bỏ các dấu `/` ở cuối chuỗi bằng vòng lặp thay cho regex `/\/+$/` (regex đó quay lui siêu tuyến
 * tính trên chuỗi nhiều dấu `/` không nằm ở cuối). */
function trimTrailingSlashes(value: string): string {
  let end = value.length;
  while (end > 0 && value[end - 1] === "/") {
    end -= 1;
  }
  return value.slice(0, end);
}

/** Ghi nhớ URL vừa đăng nhập thành công: đưa lên đầu, bỏ trùng, giới hạn `HISTORY_MAX` mục.
 * Trả về danh sách mới để component cập nhật state. */
export function rememberOdooUrl(url: string): string[] {
  const normalized = trimTrailingSlashes(url.trim());
  const current = loadOdooUrlHistory();
  if (!normalized) {
    return current;
  }
  const next = [normalized, ...current.filter((entry) => entry !== normalized)].slice(0, HISTORY_MAX);
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  } catch {
    // localStorage bị chặn thì chỉ mất lịch sử, đăng nhập vẫn chạy bình thường.
  }
  return next;
}

/** Ô nhập URL Odoo kèm dropdown các URL đã dùng. Dùng danh sách tự vẽ vì `<datalist>` và popup
 * `<select>` native không đáng tin trên WebKitGTK. ponytail: chọn bằng chuột, chưa hỗ trợ phím mũi tên. */
export function OdooUrlField({
  value,
  history,
  onChange,
}: Readonly<{ value: string; history: string[]; onChange: (value: string) => void }>) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const showList = open && history.length > 0;
  return (
    <div className="block text-sm font-medium">
      <label htmlFor="odoo-url">{t("login.odooUrl")}</label>
      <div className="relative mt-1">
        <input
          id="odoo-url"
          className="w-full rounded border border-slate-300 px-3 py-2 pr-9"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
        />
        {history.length > 0 ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={t("login.odooUrl.history")}
            className="absolute inset-y-0 right-0 px-3 text-slate-500"
            // Giữ focus ở ô nhập để onBlur không đóng danh sách trước khi click kịp xử lý.
            onMouseDown={(event) => {
              event.preventDefault();
              setOpen((current) => !current);
            }}
          >
            ▾
          </button>
        ) : null}
        {showList ? (
          <ul
            className="absolute z-10 mt-1 w-full overflow-hidden rounded border border-slate-300 bg-white shadow"
          >
            {history.map((url) => (
              <li key={url}>
                <button
                  type="button"
                  tabIndex={-1}
                  className="block w-full truncate px-3 py-2 text-left font-normal hover:bg-slate-100"
                  // Giữ focus ở ô nhập khi bấm một mục (handler nằm trên nút, không nằm trên `ul`).
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    onChange(url);
                    setOpen(false);
                  }}
                >
                  {url}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
