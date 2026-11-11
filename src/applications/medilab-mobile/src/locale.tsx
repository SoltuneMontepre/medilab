import { createContext, useCallback, useContext, type ReactNode } from "react";

import { translate, type Locale, type Translate } from "./i18n";

const LocaleContext = createContext<Locale>("vi");

/** Gives the components below the locale that `useT` translates into. */
export function LocaleProvider({ locale, children }: Readonly<{ locale: Locale; children: ReactNode }>) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useT(): Translate {
  const locale = useContext(LocaleContext);
  return useCallback((key, vars) => translate(locale, key, vars), [locale]);
}
