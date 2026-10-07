import { useState, type SubmitEvent } from "react";
import { useT } from "../../locale";
import type { Locale } from "../../i18n";
import { LanguageSwitch } from "../../components";
import { OdooUrlField } from "./OdooUrlField";

/** Thuộc tính đầu vào của màn hình đăng nhập: trạng thái form, giá trị URL Odoo và callback submit/đổi ngôn ngữ. */
type LoginScreenProps = {
  busy: boolean;
  error: string | null;
  odooUrl: string;
  odooUrlHistory: string[];
  sessionExpired: boolean;
  locale: string | undefined;
  onOdooUrlChange: (value: string) => void;
  onLocaleChange: (locale: Locale) => void;
  onSubmit: (credentials: { account: string; password: string }) => void;
};

/** Màn hình đăng nhập Odoo, hiện trước khi có phiên hợp lệ. */
export function LoginScreen({
  busy,
  error,
  odooUrl,
  odooUrlHistory,
  sessionExpired,
  locale,
  onOdooUrlChange,
  onLocaleChange,
  onSubmit,
}: Readonly<LoginScreenProps>) {
  const t = useT();
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(event: SubmitEvent) {
    event.preventDefault();
    onSubmit({ account, password });
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t("app.title")}</h1>
        <LanguageSwitch locale={locale} onChange={onLocaleChange} />
      </div>
      <p className="mt-2 text-slate-600">{t("login.subtitle")}</p>
      {sessionExpired ? (
        <p className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t("login.sessionExpired")}
        </p>
      ) : null}
      <form className="mt-6 space-y-3" onSubmit={handleSubmit}>
        <OdooUrlField value={odooUrl} history={odooUrlHistory} onChange={onOdooUrlChange} />
        <label className="block text-sm font-medium">
          <span>{t("login.account")}</span>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={account}
            onChange={(event) => setAccount(event.target.value)}
          />
        </label>
        <label className="block text-sm font-medium">
          <span>{t("login.password")}</span>
          <input
            type="password"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <button className="btn btn-primary" disabled={busy} type="submit">
          {t("login.submit")}
        </button>
      </form>
    </main>
  );
}
