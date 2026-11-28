import { useEffect, useRef, useState, type KeyboardEvent, type SubmitEvent } from "react";
import { useT } from "../../locale";
import type { MessageKey } from "../../i18n";
import type { FolderRow, StatusDto } from "../../types";
import { displayLocalPath, ToggleSwitch } from "../../components";
import { FolderExplorer } from "./FolderExplorer";
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

/** Thẻ thư mục chính: chọn một lần, sau đó thư mục của các mẫu được giao tự được gắn vào bên trong. */
export function HomeFolderCard({
  homeFolder,
  busy,
  onChoose,
}: Readonly<{ homeFolder: string | null | undefined; busy: boolean; onChoose: () => void }>) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-4">
      <div className="text-sm">
        <h2 className="text-base font-semibold">{t("home.title")}</h2>
        <p className="text-slate-600">{t(homeFolder ? "home.set" : "home.unset")}</p>
        {homeFolder ? (
          <p className="break-words font-medium">{displayLocalPath(homeFolder)}</p>
        ) : null}
      </div>
      <button
        type="button"
        className={`btn shrink-0 ${homeFolder ? "btn-secondary" : "btn-primary"}`}
        disabled={busy}
        onClick={onChoose}
      >
        {t(homeFolder ? "home.change" : "folders.choose")}
      </button>
    </div>
  );
}

/** Thuộc tính đầu vào của tab Thư mục: giá trị form thêm thư mục (kể cả kéo-thả), hộp thoại thêm,
 * dòng đang được kéo tệp qua và các callback thao tác trên thư mục. */
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
  addOpen: boolean;
  onAddOpenChange: (open: boolean) => void;
  onOpenFolder: (folderId: number) => void;
  onUnregister: (folderId: number, logicalRoot: string) => void;
  onRebind: (folder: FolderRow) => void;
  onManageAccess: (remoteId: number, logicalRoot: string) => void;
  onSharedBound: (status: StatusDto) => void;
  dropActive: boolean;
  dropFolderId: number | null;
  homeFolder: string | null | undefined;
  onChooseHomeFolder: () => void;
};

/** Hộp thoại thêm thư mục đồng bộ: chọn, dán hoặc kéo-thả một thư mục, đặt tên trên máy chủ và
 * tuỳ chọn nâng cao. Esc hoặc Hủy để đóng. */
function AddFolderDialog(props: Readonly<FoldersTabProps>) {
  const t = useT();
  const ref = useRef<HTMLDialogElement>(null);
  const windowsHost = isWindowsHost();
  // Chỉ đọc lúc mở: đổi `open` khi người dùng đang tắt công tắc sẽ làm khung gập lại giữa chừng.
  const startAdvancedOpen = useRef(props.filterEnabled || !props.recursive).current;
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby="add-folder-title"
      className="m-auto w-full max-w-xl rounded-lg border bg-white p-0 shadow-lg backdrop:bg-slate-900/40"
      onCancel={(event) => {
        event.preventDefault();
        props.onAddOpenChange(false);
      }}
    >
      <form className="space-y-4 p-4" onSubmit={props.onRegister}>
        <h2 id="add-folder-title" className="text-lg font-semibold">
          {t("folders.register")}
        </h2>
        <p className="text-sm text-slate-600">{t("folders.registerIntro")}</p>
        <label className="block text-sm">
          <span className="font-medium">{t("folders.localFolder")}</span>
          <div className="mt-1 flex gap-2">
            <input
              className="w-full rounded border px-3 py-2"
              value={props.localPath}
              placeholder={windowsHost ? String.raw`C:\Users\...\lab-results` : "/path/to/lab-results"}
              onChange={(event) => props.onLocalPathChange(event.target.value)}
            />
            <button type="button" className="btn btn-secondary shrink-0" onClick={props.onChooseFolder}>
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
            value={props.logicalRoot}
            onChange={(event) => props.onLogicalRootChange(event.target.value)}
          />
          <p className="mt-1 text-xs text-slate-500">{t("folders.logicalNameHint")}</p>
        </label>
        {/* Mặc định đồng bộ mọi tệp nên các tuỳ chọn gập lại; mở sẵn khi đang khác mặc định để không ẩn bộ lọc đang áp dụng. */}
        <details className="space-y-4" open={startAdvancedOpen}>
          <summary className="cursor-pointer text-sm font-medium">{t("folders.advanced")}</summary>
          <ToggleSwitch
            checked={props.recursive}
            label={t("folders.recursive")}
            hint={t(props.recursive ? "folders.recursiveOnHint" : "folders.recursiveOffHint")}
            onChange={props.onRecursiveChange}
          />
          <div className="rounded border border-slate-200 bg-slate-50 p-3">
            <ToggleSwitch
              checked={props.filterEnabled}
              label={t("folders.filter")}
              hint={t(props.filterEnabled ? "folders.filterOnHint" : "folders.filterOffHint")}
              onChange={props.onFilterEnabledChange}
            />
            {props.filterEnabled ? (
              <div className="mt-3 space-y-3">
                <div className="text-sm">
                  <span id="rule-kind-label" className="font-medium">
                    {t("folders.ruleKind")}
                  </span>
                  <RuleKindSelect value={props.ruleKind} labelId="rule-kind-label" onChange={props.onRuleKindChange} />
                </div>
                <label className="block text-sm">
                  <span className="font-medium">{t(rulePatternLabelKey(props.ruleKind))}</span>
                  <input
                    className="mt-1 w-full rounded border bg-white px-3 py-2"
                    value={props.rulePattern}
                    placeholder={rulePatternPlaceholder(props.ruleKind)}
                    onChange={(event) => props.onRulePatternChange(event.target.value)}
                  />
                  <p className="mt-1 text-xs text-slate-500">{t(rulePatternHintKey(props.ruleKind))}</p>
                </label>
              </div>
            ) : null}
          </div>
        </details>
        <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
          <button type="button" className="btn btn-secondary" onClick={() => props.onAddOpenChange(false)}>
            {t("action.cancel")}
          </button>
          <button
            className="btn btn-primary"
            disabled={props.busy || !props.localPath.trim() || !props.logicalRoot.trim()}
            type="submit"
          >
            {t("folders.submit")}
          </button>
        </div>
      </form>
    </dialog>
  );
}

/** Tab Thư mục: thư mục chính, bảng thư mục đã thêm kiểu trình quản lý tệp (kéo tệp vào một dòng để
 * chép vào thư mục đó), hộp thoại thêm thư mục và các thư mục trên máy chủ chưa gắn. */
export function FoldersTab(props: Readonly<FoldersTabProps>) {
  const t = useT();
  const { status, busy } = props;
  return (
    <div className="space-y-6">
      <HomeFolderCard homeFolder={props.homeFolder} busy={busy} onChoose={props.onChooseHomeFolder} />
      <div
        className={`rounded-lg border bg-white p-4 ${
          props.dropActive && props.dropFolderId === null ? "ring-2 ring-slate-700 ring-offset-2" : ""
        }`}
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-semibold">{t("folders.registered")}</h2>
            <p className="text-xs text-slate-500">{t("folders.explorerHint")}</p>
          </div>
          <button type="button" className="btn btn-primary shrink-0" onClick={() => props.onAddOpenChange(true)}>
            + {t("folders.submit")}
          </button>
        </div>
        {status.folders.length === 0 ? (
          <p className="text-sm text-slate-500">{t("folders.empty")}</p>
        ) : (
          <FolderExplorer
            folders={status.folders}
            dropFolderId={props.dropFolderId}
            busy={busy}
            onOpen={props.onOpenFolder}
            onManageAccess={props.onManageAccess}
            onUnregister={props.onUnregister}
            onRebind={props.onRebind}
          />
        )}
      </div>
      {props.addOpen ? <AddFolderDialog {...props} /> : null}
      <SharedFolders
        boundCount={status.folders.filter((folder) => folder.remote_id != null).length}
        onBound={props.onSharedBound}
      />
    </div>
  );
}

