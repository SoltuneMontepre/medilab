import { useEffect, useRef, useState, type KeyboardEvent, type SubmitEvent } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { StatusDto } from "../../types";
import { displayLocalPath, ToggleSwitch } from "../../components";
import { SharedFolders } from "../access/SharedFolders";

/** True nếu app đang chạy trên Windows (theo user agent/platform của trình duyệt). */
function isWindowsHost(): boolean {
  return /Windows/i.test(navigator.userAgent) || navigator.platform.startsWith("Win");
}

const RULE_KIND_VALUES = ["prefix", "glob", "extension"] as const;

/** Key thông điệp hiện cho một loại rule (tiền tố/glob/phần mở rộng). */
function ruleKindMessageKey(kind: string): MessageKey {
  if (kind === "prefix") {
    return "folders.rule.prefix";
  }
  if (kind === "extension") {
    return "folders.rule.extension";
  }
  return "folders.rule.glob";
}

/** Nhãn ô nhập mẫu lọc theo loại rule đang chọn. */
function rulePatternLabelKey(kind: string): MessageKey {
  if (kind === "prefix") {
    return "folders.pattern.prefix";
  }
  return kind === "extension" ? "folders.pattern.extension" : "folders.pattern.glob";
}

/** Gợi ý dưới ô nhập mẫu lọc theo loại rule đang chọn. */
function rulePatternHintKey(kind: string): MessageKey {
  if (kind === "prefix") {
    return "folders.patternHint.prefix";
  }
  return kind === "extension" ? "folders.patternHint.extension" : "folders.patternHint.glob";
}

/** Ví dụ mẫu lọc hiện mờ trong ô nhập. */
function rulePatternPlaceholder(kind: string): string {
  if (kind === "prefix") {
    return "ABC";
  }
  return kind === "extension" ? "xlsx" : "ABC*.xlsx";
}

/** Dropdown tự vẽ để chọn loại rule (tiền tố/glob/phần mở rộng); `<select>` gốc lỗi popup trên
 * WebKitGTK. Chọn xong là đóng; bấm ra ngoài hoặc Esc cũng đóng; mũi tên lên/xuống đổi lựa chọn.
 * KHÔNG bọc component này trong `<label>`: label chuyển tiếp cú bấm vào option sang nút mở, làm
 * danh sách vừa đóng đã mở lại. */
function RuleKindSelect({
  value,
  labelId,
  onChange,
}: Readonly<{ value: string; labelId: string; onChange: (value: string) => void }>) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    /** Đóng danh sách khi bấm ra ngoài component. */
    function closeOnOutsideClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  /** Bàn phím: Esc đóng; mũi tên lên/xuống chuyển sang lựa chọn kề bên. */
  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      return;
    }
    event.preventDefault();
    const index = RULE_KIND_VALUES.indexOf(value as (typeof RULE_KIND_VALUES)[number]);
    const step = event.key === "ArrowDown" ? 1 : -1;
    const next = (index + step + RULE_KIND_VALUES.length) % RULE_KIND_VALUES.length;
    onChange(RULE_KIND_VALUES[next]);
  }

  return (
    <div ref={rootRef} className="relative mt-1">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded border px-3 py-2 text-left"
        aria-haspopup="true"
        aria-expanded={open}
        aria-labelledby={labelId}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={handleKeyDown}
      >
        <span>{t(ruleKindMessageKey(value))}</span>
        <span aria-hidden="true" className="text-slate-500">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {open ? (
        <ul
          aria-labelledby={labelId}
          className="absolute z-10 mt-1 w-full overflow-hidden rounded border bg-white shadow-lg"
        >
          {RULE_KIND_VALUES.map((kind) => (
            <li key={kind}>
              <button
                type="button"
                aria-current={kind === value}
                onKeyDown={handleKeyDown}
                className={`flex w-full items-center justify-between px-3 py-2 text-left hover:bg-slate-50 ${
                  kind === value ? "bg-slate-100 font-medium" : ""
                }`}
                onClick={() => {
                  onChange(kind);
                  setOpen(false);
                }}
              >
                <span>{t(ruleKindMessageKey(kind))}</span>
                {kind === value ? <span aria-hidden="true">✓</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Thuộc tính đầu vào của tab Thư mục: giá trị form đăng ký folder (kể cả kéo-thả) và các callback thay đổi/đăng ký/hủy đăng ký. */
type FoldersTabProps = {
  status: StatusDto;
  busy: boolean;
  logicalRoot: string;
  localPath: string;
  ruleKind: string;
  rulePattern: string;
  recursive: boolean;
  filterEnabled: boolean;
  onFilterEnabledChange: (value: boolean) => void;
  onLogicalRootChange: (value: string) => void;
  onLocalPathChange: (value: string) => void;
  onRuleKindChange: (value: string) => void;
  onRulePatternChange: (value: string) => void;
  onRecursiveChange: (value: boolean) => void;
  onChooseFolder: () => void;
  onRegister: (event: SubmitEvent) => void;
  onUnregister: (folderId: number, logicalRoot: string) => void;
  onManageAccess: (remoteId: number, logicalRoot: string) => void;
  onSharedBound: (status: StatusDto) => void;
  dropActive: boolean;
};

/** Tab Thư mục: form đăng ký folder mới (kể cả kéo-thả) và danh sách folder đã đăng ký. */
export function FoldersTab({
  status,
  busy,
  logicalRoot,
  localPath,
  ruleKind,
  rulePattern,
  recursive,
  filterEnabled,
  onFilterEnabledChange,
  onLogicalRootChange,
  onLocalPathChange,
  onRuleKindChange,
  onRulePatternChange,
  onRecursiveChange,
  onChooseFolder,
  onRegister,
  onUnregister,
  onManageAccess,
  onSharedBound,
  dropActive,
}: Readonly<FoldersTabProps>) {
  const t = useT();
  const windowsHost = isWindowsHost();
  return (
    <div
      className={`grid gap-6 lg:grid-cols-2 ${dropActive ? "rounded-lg ring-2 ring-slate-700 ring-offset-2" : ""}`}
    >
      <form className="space-y-4 rounded-lg border bg-white p-4" onSubmit={onRegister}>
        <h2 className="font-semibold">{t("folders.register")}</h2>
        <p className="text-sm text-slate-600">{t("folders.registerIntro")}</p>
        <label className="block text-sm">
          <span className="font-medium">{t("folders.localFolder")}</span>
          <div className="mt-1 flex gap-2">
            <input
              className="w-full rounded border px-3 py-2"
              value={localPath}
              placeholder={windowsHost ? String.raw`C:\Users\...\lab-results` : "/path/to/lab-results"}
              onChange={(event) => onLocalPathChange(event.target.value)}
            />
            <button type="button" className="btn btn-secondary shrink-0" onClick={onChooseFolder}>
              {t("folders.choose")}
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {t("folders.pickHint")}
            {windowsHost ? null : ` ${t("folders.hyprlandHint")}`} {t("folders.dropHint")}
          </p>
        </label>
        <label className="block text-sm">
          <span className="font-medium">{t("folders.logicalName")}</span>
          <input
            className="mt-1 w-full rounded border px-3 py-2"
            value={logicalRoot}
            onChange={(event) => onLogicalRootChange(event.target.value)}
          />
          <p className="mt-1 text-xs text-slate-500">{t("folders.logicalNameHint")}</p>
        </label>
        <ToggleSwitch
          checked={recursive}
          label={t("folders.recursive")}
          hint={t(recursive ? "folders.recursiveOnHint" : "folders.recursiveOffHint")}
          onChange={onRecursiveChange}
        />
        <div className="rounded border border-slate-200 bg-slate-50 p-3">
          <ToggleSwitch
            checked={filterEnabled}
            label={t("folders.filter")}
            hint={t(filterEnabled ? "folders.filterOnHint" : "folders.filterOffHint")}
            onChange={onFilterEnabledChange}
          />
          {filterEnabled ? (
            <div className="mt-3 space-y-3">
              <div className="text-sm">
                <span id="rule-kind-label" className="font-medium">
                  {t("folders.ruleKind")}
                </span>
                <RuleKindSelect value={ruleKind} labelId="rule-kind-label" onChange={onRuleKindChange} />
              </div>
              <label className="block text-sm">
                <span className="font-medium">{t(rulePatternLabelKey(ruleKind))}</span>
                <input
                  className="mt-1 w-full rounded border bg-white px-3 py-2"
                  value={rulePattern}
                  placeholder={rulePatternPlaceholder(ruleKind)}
                  onChange={(event) => onRulePatternChange(event.target.value)}
                />
                <p className="mt-1 text-xs text-slate-500">{t(rulePatternHintKey(ruleKind))}</p>
              </label>
            </div>
          ) : null}
        </div>
        <div className="flex justify-end border-t border-slate-200 pt-3">
          <button
            className="btn btn-primary"
            disabled={busy || !localPath.trim() || !logicalRoot.trim()}
            type="submit"
          >
            {t("folders.submit")}
          </button>
        </div>
      </form>
      <div className="rounded-lg border bg-white p-4">
        <h2 className="font-semibold">{t("folders.registered")}</h2>
        <ul className="mt-3 space-y-2 text-sm">
          {status.folders.length === 0 ? (
            <li className="text-slate-500">{t("folders.empty")}</li>
          ) : (
            status.folders.map((folder) => (
              <li key={folder.id} className="flex items-start justify-between gap-3 rounded border p-3">
                <div>
                  <div className="font-medium">{folder.logical_root}</div>
                  {folder.sample_name ? (
                    <div className="text-slate-700">
                      {t("folders.sample")}: {folder.sample_name}
                      {folder.category ? ` · ${folder.category}` : ""}
                    </div>
                  ) : null}
                  {folder.workflow_status ? (
                    <div className="text-slate-600">
                      {t("folders.workflow")}: {folder.workflow_status}
                    </div>
                  ) : null}
                  {folder.instrument_label ? (
                    <div className="text-slate-600">
                      {t("folders.instrument")}: {folder.instrument_label}
                    </div>
                  ) : null}
                  {folder.access_state === "denied" ? (
                    <div className="text-amber-700">{t("folders.denied")}</div>
                  ) : null}
                  <div className="break-words text-slate-600" title={folder.local_path}>
                    {displayLocalPath(folder.local_path)}
                  </div>
                  <div className="text-xs text-slate-500">remote_id: {folder.remote_id ?? "—"}</div>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  {folder.remote_id != null ? (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => onManageAccess(folder.remote_id as number, folder.logical_root)}
                    >
                      {t("access.manage")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="btn btn-danger"
                    disabled={busy}
                    onClick={() => onUnregister(folder.id, folder.logical_root)}
                  >
                    {t("folders.unregister")}
                  </button>
                </div>
              </li>
            ))
          )}
        </ul>
      </div>
      <SharedFolders boundCount={status.folders.length} onBound={onSharedBound} />
    </div>
  );
}
