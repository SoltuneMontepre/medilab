import { useT } from "./locale";
import { normalizeLocale, type Locale } from "./i18n";

/** Ô chọn ngôn ngữ giao diện (vi/en). */
export function LanguageSwitch({
  locale,
  onChange,
}: Readonly<{ locale: string | undefined; onChange: (locale: Locale) => void }>) {
  const t = useT();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span>{t("settings.language")}</span>
      <select
        className="rounded border border-slate-300 px-2 py-1"
        value={normalizeLocale(locale)}
        onChange={(event) => onChange(normalizeLocale(event.target.value))}
      >
        <option value="vi">{t("settings.language.vi")}</option>
        <option value="en">{t("settings.language.en")}</option>
      </select>
    </label>
  );
}

/** Rút gọn tiền tố đường dẫn kiểu Windows (`\\?\`, `\\?\UNC\`) để hiện thân thiện hơn. */
export function displayLocalPath(path: string): string {
  if (path.startsWith("\\\\?\\UNC\\")) {
    return `\\\\${path.slice("\\\\?\\UNC\\".length)}`;
  }
  if (path.startsWith("\\\\?\\")) {
    return path.slice("\\\\?\\".length);
  }
  return path;
}

/** Công tắc bật/tắt rõ trạng thái: nền xanh + chữ "Bật" khi bật, nền xám + chữ "Tắt" khi tắt. Bấm
 * vào nhãn cũng đổi trạng thái (nút nằm trong `<label>`). */
export function ToggleSwitch({
  checked,
  label,
  hint,
  onChange,
}: Readonly<{
  checked: boolean;
  label: string;
  hint?: string;
  onChange: (checked: boolean) => void;
}>) {
  const t = useT();
  return (
    <label className="flex cursor-pointer items-start gap-3 text-sm">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-700 ${
          checked ? "bg-emerald-600" : "bg-slate-300"
        }`}
        onClick={() => onChange(!checked)}
      >
        <span
          aria-hidden="true"
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : ""
          }`}
        />
      </button>
      <span>
        <span className="font-medium">{label}</span>
        <span
          className={`ml-2 rounded px-1.5 py-0.5 text-xs font-semibold ${
            checked ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"
          }`}
        >
          {t(checked ? "toggle.on" : "toggle.off")}
        </span>
        {hint ? <span className="mt-0.5 block text-xs text-slate-500">{hint}</span> : null}
      </span>
    </label>
  );
}
