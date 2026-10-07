import { createContext, useContext, useMemo, type ReactNode } from "react";
import { normalizeLocale, translate, type Locale, type MessageKey, type Translate } from "./i18n";

const LocaleContext = createContext<{ locale: Locale; t: Translate }>({
  locale: "vi",
  t: (key, vars) => translate("vi", key, vars),
});

/** Cung cấp locale đã chuẩn hóa và hàm dịch `t` cho toàn bộ cây component bên dưới. */
export function LocaleProvider({
  locale,
  children,
}: Readonly<{ locale: string | null | undefined; children: ReactNode }>) {
  const resolved = normalizeLocale(locale);
  const value = useMemo(() => {
    /** Hàm dịch đã gắn sẵn locale đã chuẩn hóa của provider này. */
    const t: Translate = (key: MessageKey, vars) => translate(resolved, key, vars);
    return { locale: resolved, t };
  }, [resolved]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

/** Hàm dịch theo locale hiện tại. */
export function useT(): Translate {
  return useContext(LocaleContext).t;
}

/** Locale hiện tại đã chuẩn hóa. */
export function useLocale(): Locale {
  return useContext(LocaleContext).locale;
}
