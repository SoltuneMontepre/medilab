import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "./locale";
import { normalizeLocale, type Locale, type MessageKey, type Translate } from "./i18n";

const CATEGORY_KEYS: Record<string, MessageKey> = {
  raw: "folders.category.raw",
  working: "folders.category.working",
  result: "folders.category.result",
  report: "folders.category.report",
};

/** Tên loại thư mục của mẫu bằng lời; loại chưa biết thì giữ nguyên giá trị máy chủ gửi. */
export function categoryLabel(t: Translate, category: string): string {
  const key = CATEGORY_KEYS[category];
  return key ? t(key) : category;
}

/** Nội dung một câu hỏi xác nhận: câu hỏi, lời giải thích và nhãn nút thực hiện. */
export type ConfirmOptions = {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
};

/** Hộp thoại xác nhận trong ứng dụng; nút thực hiện mang tên hành động, Esc hoặc Hủy để bỏ qua. */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  danger = false,
  onConfirm,
  onCancel,
}: Readonly<ConfirmOptions & { onConfirm: () => void; onCancel: () => void }>) {
  const t = useT();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      className="m-auto w-full max-w-md rounded-lg border bg-white p-4 shadow-lg backdrop:bg-slate-900/40"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2 id="confirm-title" className="text-lg font-semibold">
        {title}
      </h2>
      <p className="mt-2 text-sm text-slate-600">{body}</p>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn btn-secondary" autoFocus onClick={onCancel}>
          {t("action.cancel")}
        </button>
        <button type="button" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

/** Hỏi xác nhận bằng `ConfirmDialog`: `confirm()` trả về lựa chọn của người dùng, `dialog` là phần
 * tử cần đặt vào cây render. */
export function useConfirm() {
  const [request, setRequest] = useState<(ConfirmOptions & { resolve: (confirmed: boolean) => void }) | null>(null);
  const confirm = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setRequest({ ...options, resolve })),
    [],
  );
  /** Trả lời câu hỏi đang mở rồi đóng hộp thoại. */
  function settle(confirmed: boolean) {
    request?.resolve(confirmed);
    setRequest(null);
  }
  const dialog = request ? (
    <ConfirmDialog
      title={request.title}
      body={request.body}
      confirmLabel={request.confirmLabel}
      danger={request.danger}
      onConfirm={() => settle(true)}
      onCancel={() => settle(false)}
    />
  ) : null;
  return { confirm, dialog };
}

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
