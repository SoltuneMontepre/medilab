export type Locale = "vi" | "en";

// Every string the app shows, in Vietnamese and English.
const messages = {
  "home.server": { vi: "Máy chủ: {url}", en: "Server: {url}" },
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
