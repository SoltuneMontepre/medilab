export type Locale = "vi" | "en";

export const LOCALES: readonly Locale[] = ["vi", "en"];

// Every string the app shows, in Vietnamese and English.
const messages = {
  "home.server": { vi: "Máy chủ: {url}", en: "Server: {url}" },
  "home.signedIn": { vi: "Đã đăng nhập", en: "Signed in" },
  "language.vi": { vi: "Tiếng Việt", en: "Tiếng Việt" },
  "language.en": { vi: "English", en: "English" },
  "signIn.title": { vi: "Đăng nhập MediLab", en: "Sign in to MediLab" },
  "signIn.server": { vi: "Địa chỉ MediLab", en: "MediLab address" },
  "signIn.login": { vi: "Tên đăng nhập", en: "Login" },
  "signIn.password": { vi: "Mật khẩu", en: "Password" },
  "signIn.submit": { vi: "Đăng nhập", en: "Sign in" },
  "signIn.missing": { vi: "Nhập tên đăng nhập và mật khẩu.", en: "Enter your login and password." },
  "server.invalid": {
    vi: "Địa chỉ MediLab phải bắt đầu bằng https://.",
    en: "The MediLab address must start with https://.",
  },
  "server.invalidDevelopment": {
    vi: "Địa chỉ MediLab phải bắt đầu bằng http:// hoặc https://.",
    en: "The MediLab address must start with http:// or https://.",
  },
  "signOut.submit": { vi: "Đăng xuất", en: "Sign out" },
  "unreachable.message": {
    vi: "Không kết nối được MediLab, nên chưa có gì thay đổi. Kiểm tra kết nối rồi thử lại.",
    en: "MediLab cannot be reached, so nothing was changed. Check the connection and try again.",
  },
  "unreachable.retry": { vi: "Thử lại", en: "Try again" },
  "loading": { vi: "Đang tải...", en: "Loading..." },
} as const satisfies Record<string, Record<Locale, string>>;

export type MessageKey = keyof typeof messages;

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Translates a message into the locale and fills in its `{name}` variables. */
export function translate(locale: Locale, key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = messages[key][locale];
  for (const [name, value] of Object.entries(vars ?? {})) {
    text = text.split(`{${name}}`).join(String(value));
  }
  return text;
}

export function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value);
}
