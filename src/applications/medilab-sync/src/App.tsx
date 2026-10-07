import { withSettingsPatch } from "./features/settings/settingsPatch";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type SubmitEvent,
} from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { AppSettings, OfficeSession, ProgressDeltaDto, RemoteFileRow, StatusDto, SyncRule } from "./types";
import { OfficeEditor } from "./features/office/OfficeEditor";
import { UpdateDialog } from "./features/update/UpdateDialog";
import { AccessDialog } from "./features/access/AccessDialog";
import { loadOdooUrlHistory, rememberOdooUrl } from "./features/login/OdooUrlField";
import { LoginScreen } from "./features/login/LoginScreen";
import { CredentialStoreLockedScreen } from "./features/login/CredentialStoreLockedScreen";
import { VersionHistoryDialog } from "./features/history/VersionHistoryDialog";
import { SettingsTab } from "./features/settings/SettingsTab";
import { FoldersTab } from "./features/sync/FoldersTab";
import { StatusTab } from "./features/sync/StatusTab";
import { AppHeader } from "./features/header/AppHeader";
import { displayLocalPath } from "./components";
import { DevelopmentProfiler } from "./components/DevelopmentProfiler";
import { LocaleProvider, useT } from "./locale";
import { normalizeLocale, type Locale, type MessageKey } from "./i18n";
import {
  applyProgressDelta,
  createRemoteFilesRefreshController,
  mergeRemoteFiles,
  mergeStatusSnapshot,
} from "./lib/syncEvents";
import {
  chooseSyncFolder,
  getSettings,
  listRemoteFiles,
  login,
  logout,
  onConflictCreated,
  onDownloadProgress,
  onFilesChanged,
  onNativeFolderDrop,
  onStatusChanged,
  onSyncError,
  onUpdateAvailable,
  onUploadProgress,
  openOfficeEditor,
  pauseSync,
  registerSyncFolder,
  resolveDroppedSyncFolder,
  unregisterSyncFolder,
  restoreSession,
  retrySyncJob,
  saveSettings,
  startSync,
  acceptServerVersion,
  keepLocalConflict,
  type UpdateAvailable,
} from "./lib/tauri";

type Tab = "status" | "folders" | "settings";

/** Tên thư mục cuối cùng của một đường dẫn (Windows hoặc POSIX), dùng gợi ý tên trên máy chủ. */
function folderBaseName(path: string): string {
  return path.split(/[\\/]/).findLast(Boolean) ?? "";
}

/** Trạng thái đồng bộ rỗng, dùng làm state khởi tạo trước khi tải lần đầu. */
function emptyStatus(): StatusDto {
  return {
    paused: false,
    degraded: false,
    logged_in: false,
    session_expired: false,
    user_name: null,
    odoo_url: "",
    pending: 0,
    uploading: 0,
    downloading: 0,
    failed: 0,
    conflict: 0,
    completed: 0,
    folders: [],
    jobs: [],
  };
}

/** Hook bọc một action bất đồng bộ: bật cờ busy, xóa lỗi cũ, bắt lỗi mới thành chuỗi. */
function useAsyncRunner(setBusy: (busy: boolean) => void, setError: (error: string | null) => void) {
  return useCallback(
    async function run<T>(fn: () => Promise<T>) {
      setBusy(true);
      setError(null);
      try {
        return await fn();
      } catch (err) {
        setError(String(err));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [setBusy, setError],
  );
}

/** Key thông điệp hiện cho tên một tab. */
function tabMessageKey(tab: Tab): MessageKey {
  switch (tab) {
    case "folders":
      return "tab.folders";
    case "settings":
      return "tab.settings";
    default:
      return "tab.status";
  }
}

/** Gốc component: cung cấp locale rồi render toàn bộ app. */
export default function App() {
  const [locale, setLocale] = useState<Locale>("vi");
  return (
    <LocaleProvider locale={locale}>
      <AppBody onLocaleChange={setLocale} />
    </LocaleProvider>
  );
}

/** Các dải thông báo đầu trang: lỗi, thông báo thành công, phiên hết hạn, và xung đột (đóng được). */
function AppBanners({
  error,
  notice,
  sessionExpired,
  conflict,
  onDismissConflict,
}: Readonly<{
  error: string | null;
  notice: string | null;
  sessionExpired: boolean;
  conflict: string | null;
  onDismissConflict: () => void;
}>) {
  const t = useT();
  return (
    <>
      {error ? <p className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="mb-4 rounded bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p> : null}
      {sessionExpired ? (
        <p className="mb-4 rounded bg-amber-50 p-3 text-sm text-amber-800">{t("session.expiredBanner")}</p>
      ) : null}
      {conflict ? (
        <p className="mb-4 flex items-start justify-between gap-3 rounded bg-amber-50 p-3 text-sm text-amber-800">
          <span>{conflict}</span>
          <button type="button" className="btn btn-secondary px-2 py-1" onClick={onDismissConflict}>
            {t("conflict.dismiss")}
          </button>
        </p>
      ) : null}
    </>
  );
}

/** Cấu hình và các hàm cập nhật state phục vụ đăng ký sự kiện đồng bộ từ backend. */
interface SyncListenerOptions {
  setStatus: Dispatch<SetStateAction<StatusDto>>;
  refreshController: ReturnType<typeof createRemoteFilesRefreshController>;
  setRemoteFiles: Dispatch<SetStateAction<RemoteFileRow[]>>;
  tRef: { readonly current: (key: MessageKey, params?: Record<string, string | number>) => string };
  setConflict: Dispatch<SetStateAction<string | null>>;
  setTab: Dispatch<SetStateAction<Tab>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setPendingUpdate: Dispatch<SetStateAction<UpdateAvailable | null>>;
  isCancelled: () => boolean;
}

/**
 * Đăng ký tuần tự các listener sự kiện backend vào mảng unlisteners để phục vụ dọn dẹp khi unmount (F-1).
 * Tách biệt các hàm xử lý sự kiện ra ngoài để giới hạn độ sâu lồng hàm (tối đa 3 cấp).
 */
async function registerSyncListeners(
  unlisteners: Array<() => void>,
  options: SyncListenerOptions,
): Promise<void> {
  const handleStatus = (next: StatusDto) => {
    options.setStatus((prev) => mergeStatusSnapshot(prev, next));
    if (!next.logged_in) {
      options.refreshController.cancel();
      options.setRemoteFiles((prev) => (prev.length === 0 ? prev : []));
    }
  };

  const handleFiles = (payload: { revision: number }) => {
    void options.refreshController.invalidate(payload.revision);
  };

  const handleProgress = (delta: ProgressDeltaDto) => {
    options.setStatus((prev) => applyProgressDelta(prev, delta));
  };

  const handleConflict = (payload: unknown) => {
    options.setConflict(options.tRef.current("conflict.bannerDetail", { detail: JSON.stringify(payload) }));
    options.setTab("status");
  };

  const handleSyncError = (payload: unknown) => {
    options.setError(options.tRef.current("sync.errorDetail", { detail: JSON.stringify(payload) }));
  };

  const handleUpdate = (info: UpdateAvailable) => {
    options.setPendingUpdate(info);
  };

  const listenerFactories: Array<() => Promise<() => void>> = [
    () => onStatusChanged(handleStatus),
    () => onFilesChanged(handleFiles),
    () => onUploadProgress(handleProgress),
    () => onDownloadProgress(handleProgress),
    () => onConflictCreated(handleConflict),
    () => onSyncError(handleSyncError),
    () => onUpdateAvailable(handleUpdate),
  ];

  for (const registerListener of listenerFactories) {
    const unlisten = await registerListener();
    if (options.isCancelled()) {
      unlisten();
      break;
    }
    unlisteners.push(unlisten);
  }
}

/** Thân ứng dụng chính: quản lý toàn bộ state (phiên, cài đặt, tab, dialog) và lắng nghe sự kiện
 * từ backend; hiện màn đăng nhập cho tới khi có phiên hợp lệ. */
function AppBody({ onLocaleChange }: Readonly<{ onLocaleChange: (locale: Locale) => void }>) {
  const t = useT();
  const tRef = useRef(t);
  tRef.current = t;
  const [status, setStatus] = useState<StatusDto>(emptyStatus());
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [tab, setTab] = useState<Tab>("status");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [odooUrl, setOdooUrl] = useState("");
  const [odooUrlHistory, setOdooUrlHistory] = useState(loadOdooUrlHistory);
  const [logicalRoot, setLogicalRoot] = useState("");
  // Tên trên máy chủ tự gợi ý theo tên thư mục đã chọn cho tới khi người dùng tự sửa.
  // Là ref (không phải state) vì handler kéo-thả được đăng ký một lần và phải đọc giá trị mới nhất.
  const logicalRootEdited = useRef(false);
  const [filterEnabled, setFilterEnabled] = useState(false);
  const [localPath, setLocalPath] = useState("");
  const [ruleKind, setRuleKind] = useState("prefix");
  const [rulePattern, setRulePattern] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [dropActive, setDropActive] = useState(false);
  const [remoteFiles, setRemoteFiles] = useState<RemoteFileRow[]>([]);
  const [historyTarget, setHistoryTarget] = useState<{ fileId: number; label: string } | null>(null);
  // Người dùng chủ động chọn đăng nhập bằng mật khẩu thay vì mở khóa kho mật khẩu của OS.
  const [passwordLoginRequested, setPasswordLoginRequested] = useState(false);
  const [accessTarget, setAccessTarget] = useState<{ remoteId: number; label: string } | null>(null);
  const [officeTarget, setOfficeTarget] = useState<{
    fileId: number;
    label: string;
    session: OfficeSession;
  } | null>(null);
  const [pendingUpdate, setPendingUpdate] = useState<UpdateAvailable | null>(null);
  const run = useAsyncRunner(setBusy, setError);
  // Lệnh Tạm dừng/Tiếp tục có cờ bận riêng: không bị khóa bởi lệnh chạy lâu khác (xem AppHeader).
  const [toggleSyncBusy, setToggleSyncBusy] = useState(false);
  const runToggleSync = useAsyncRunner(setToggleSyncBusy, setError);

  useEffect(() => {
    void getCurrentWindow()
      .setTitle(t("app.title"))
      .catch(() => {
        /* window title is best-effort outside a Tauri webview */
      });
  }, [t]);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  /** Đổi ngôn ngữ giao diện ngay lập tức, rồi lưu vào cấu hình (best-effort, không chặn UI). */
  async function changeLocale(nextLocale: Locale) {
    onLocaleChange(nextLocale);
    setSettings((current) => (current ? { ...current, locale: nextLocale } : current));
    try {
      const stored = await getSettings();
      await saveSettings(withSettingsPatch(stored, { locale: nextLocale }));
    } catch {
      /* keep the UI language even if persist fails */
    }
  }

  const refreshControllerRef = useRef<ReturnType<typeof createRemoteFilesRefreshController> | null>(null);
  if (!refreshControllerRef.current) {
    refreshControllerRef.current = createRemoteFilesRefreshController({
      fetcher: listRemoteFiles,
      onLoaded: (files) => setRemoteFiles((prev) => mergeRemoteFiles(prev, files)),
      // Lỗi tải danh sách tệp không được nuốt im (F-2): thông báo cho người dùng và xóa danh sách cũ.
      onError: (err) => {
        setRemoteFiles((prev) => (prev.length === 0 ? prev : []));
        setError(String(err));
      },
    });
  }
  const refreshController = refreshControllerRef.current;

  /** Tải lại danh sách tệp đã đồng bộ từ backend qua refresh controller; rỗng nếu lỗi. */
  const refreshRemoteFiles = useCallback(async () => {
    await refreshController.invalidate();
  }, [refreshController]);

  useEffect(() => {
    let cancelled = false;
    const unlisteners: Array<() => void> = [];
    void (async () => {
      try {
        // Điền URL mặc định ngay khi đọc xong settings (local, tức thì); restoreSession có thể treo đến
        // hết timeout mạng khi server không phản hồi, không được chặn ô URL trống trong lúc đó.
        const settingsRequest = getSettings();
        void settingsRequest
          .then((loaded) => {
            if (!cancelled) {
              setOdooUrl((typed) => typed || loaded.odoo_url);
            }
          })
          .catch(() => {});
        const [current, currentSettings] = await Promise.all([restoreSession(), settingsRequest]);
        if (cancelled) {
          return;
        }
        setStatus((prev) => mergeStatusSnapshot(prev, current));
        setSettings(currentSettings);
        onLocaleChange(normalizeLocale(currentSettings.locale));
        // Không ghi đè URL người dùng đã gõ hoặc chọn trong lúc chờ restoreSession.
        setOdooUrl((typed) => typed || current.odoo_url || currentSettings.odoo_url);
        if (current.logged_in) {
          void refreshController.invalidate();
        }
      } catch (err) {
        if (!cancelled) {
          setError(String(err));
        }
      }
      // Đăng ký tuần tự các listener qua hàm phụ trợ để đảm bảo các lượt đăng ký thành công
      // luôn được lưu vào unlisteners phục vụ dọn dẹp kể cả khi một lượt sau đó thất bại (F-1),
      // đồng thời tránh gọi Array#push lặp lại nhiều lần và giới hạn độ sâu lồng hàm.
      try {
        await registerSyncListeners(unlisteners, {
          setStatus,
          refreshController,
          setRemoteFiles,
          tRef,
          setConflict,
          setTab,
          setError,
          setPendingUpdate,
          isCancelled: () => cancelled,
        });
      } catch (listenErr) {
        // Lỗi đăng ký listener là best-effort: các listener đã đăng ký thành công vẫn nằm trong
        // unlisteners và sẽ được dọn dẹp khi component unmount.
        if (!cancelled) {
          setError(String(listenErr));
        }
      }
    })();
    return () => {
      cancelled = true;
      refreshController.cancel();
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let stop: (() => void) | undefined;
    void onNativeFolderDrop({
      onEnter: () => setDropActive(true),
      onLeave: () => setDropActive(false),
      onDrop: (paths) => {
        setDropActive(false);
        void resolveDroppedSyncFolder(paths)
          .then((path) => applyLocalPath(displayLocalPath(path)))
          .catch((err) => setError(String(err)));
      },
    }).then((unlisten) => {
      if (disposed) {
        unlisten();
        return;
      }
      stop = unlisten;
    });
    return () => {
      disposed = true;
      stop?.();
    };
  }, []);

  /** Xử lý submit form đăng nhập: đăng nhập, cập nhật trạng thái, tải lại danh sách tệp. */
  async function onLogin(credentials: { account: string; password: string }) {
    const next = await run(() => login(odooUrl, credentials.account, credentials.password));
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
      setOdooUrlHistory(rememberOdooUrl(odooUrl));
      void refreshRemoteFiles();
    }
  }

  /** Bật hoặc tắt tạm dừng đồng bộ, tùy theo trạng thái hiện tại. */
  async function toggleSync() {
    const next = await runToggleSync(status.paused ? startSync : pauseSync);
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
    }
  }

  /** Đăng xuất và xóa state cục bộ gắn với phiên (tệp, dialog lịch sử/office đang mở). */
  async function onLogout() {
    const next = await run(logout);
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
      refreshController.cancel();
      setRemoteFiles([]);
      setHistoryTarget(null);
      setOfficeTarget(null);
    }
  }

  /** Xử lý submit form đăng ký thư mục với đúng một rule đang cấu hình trên form. */
  async function onRegisterFolder(event: SubmitEvent) {
    event.preventDefault();
    // Mặc định đồng bộ cả thư mục: không gửi rule nào (engine và server đều hiểu "không rule" là
    // mọi tệp). Chỉ gửi rule khi người dùng bật lọc VÀ có nhập mẫu.
    const pattern = rulePattern.trim();
    const rules: SyncRule[] =
      filterEnabled && pattern ? [{ kind: ruleKind, pattern, recursive, enabled: true }] : [];
    const next = await run(() =>
      registerSyncFolder({
        local_path: localPath,
        logical_root: logicalRoot,
        recursive,
        rules,
      }),
    );
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
      setLocalPath("");
      setLogicalRoot("");
      logicalRootEdited.current = false;
    }
  }

  /** Nhận đường dẫn thư mục cục bộ (chọn, dán hoặc kéo-thả) và gợi ý tên trên máy chủ theo tên
   * thư mục, trừ khi người dùng đã tự đặt tên. */
  function applyLocalPath(path: string) {
    setLocalPath(path);
    if (!logicalRootEdited.current) {
      setLogicalRoot(folderBaseName(path));
    }
  }

  /** Mở dialog chọn thư mục; báo lỗi picker thiếu nếu không có đường dẫn nào trả về. */
  async function onChooseFolder() {
    try {
      const path = await chooseSyncFolder();
      if (path) {
        applyLocalPath(displayLocalPath(path));
        return;
      }
      setError(t("folders.pickerMissing"));
    } catch (err) {
      setError(String(err));
    }
  }

  /** Xác nhận với người dùng rồi hủy đăng ký một thư mục. */
  async function onUnregisterFolder(folderId: number, folderLogicalRoot: string) {
    if (!window.confirm(t("folders.unregisterConfirm", { name: folderLogicalRoot }))) {
      return;
    }
    const next = await run(() => unregisterSyncFolder(folderId));
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
    }
  }

  /** Xử lý submit form cài đặt: lưu cấu hình, đồng bộ ngôn ngữ đang chọn, và hiện thông báo đã
   * lưu. */
  async function onSaveSettings(event: SubmitEvent) {
    event.preventDefault();
    if (!settings) {
      return;
    }
    setNotice(null);
    const next = await run(() =>
      saveSettings(withSettingsPatch(settings, { locale: normalizeLocale(settings.locale) })),
    );
    if (next) {
      setStatus((prev) => mergeStatusSnapshot(prev, next));
      onLocaleChange(normalizeLocale(settings.locale));
      setNotice(t("settings.saved"));
    }
  }

  const handleRetryJob = useCallback(
    (jobId: number) => {
      void run(() => retrySyncJob(jobId)).then((next) => {
        if (next) {
          setStatus((prev) => mergeStatusSnapshot(prev, next));
        }
      });
    },
    [run],
  );

  const handleOpenHistory = useCallback((fileId: number, label: string) => {
    setHistoryTarget({ fileId, label });
  }, []);

  const handleOpenOffice = useCallback(
    (fileId: number, label: string) => {
      void run(() => openOfficeEditor(fileId)).then((session) => {
        if (session) {
          setOfficeTarget({ fileId, label, session });
        }
      });
    },
    [run],
  );

  const handleKeepLocal = useCallback(
    (fileId: number) => {
      void run(() => keepLocalConflict(fileId)).then((next) => {
        if (next) {
          setStatus((prev) => mergeStatusSnapshot(prev, next));
          setConflict(null);
          void refreshRemoteFiles();
        }
      });
    },
    [refreshRemoteFiles, run],
  );

  const handleAcceptServer = useCallback(
    (fileId: number) => {
      void run(() => acceptServerVersion(fileId)).then((next) => {
        if (next) {
          setStatus((prev) => mergeStatusSnapshot(prev, next));
          setConflict(null);
          void refreshRemoteFiles();
        }
      });
    },
    [refreshRemoteFiles, run],
  );

  // Kho mật khẩu của OS đang khóa: key có thể vẫn hợp lệ, nên mời mở khóa rồi thử lại thay vì
  // bắt đăng nhập lại bằng mật khẩu (và không nói dối là "phiên hết hạn").
  if (status.auth_state === "credential_store_locked" && !passwordLoginRequested) {
    return (
      <CredentialStoreLockedScreen
        busy={busy}
        error={error}
        onUsePassword={() => setPasswordLoginRequested(true)}
        onRetry={() =>
          void run(() => restoreSession()).then((next) => {
            if (next) {
              setStatus((prev) => mergeStatusSnapshot(prev, next));
            }
          })
        }
      />
    );
  }

  if (!status.logged_in) {
    return (
      <LoginScreen
        busy={busy}
        error={error}
        odooUrl={odooUrl}
        odooUrlHistory={odooUrlHistory}
        sessionExpired={status.session_expired}
        locale={settings?.locale}
        onOdooUrlChange={setOdooUrl}
        onLocaleChange={(locale) => void changeLocale(locale)}
        onSubmit={(credentials) => void onLogin(credentials)}
      />
    );
  }

  return (
    <main className="min-h-screen">
      <AppHeader
        status={status}
        busy={busy}
        toggleBusy={toggleSyncBusy}
        locale={settings?.locale}
        onLocaleChange={(locale) => void changeLocale(locale)}
        onToggleSync={() => void toggleSync()}
        onLogout={() => void onLogout()}
      />

      <nav className="flex gap-4 border-b bg-white px-6 py-2 text-sm">
        {(["status", "folders", "settings"] as Tab[]).map((item) => (
          <button
            key={item}
            type="button"
            className={`tab-btn ${tab === item ? "tab-btn-active" : ""}`}
            onClick={() => setTab(item)}
          >
            {t(tabMessageKey(item))}
          </button>
        ))}
      </nav>

      <section className="p-6">
        <AppBanners
          error={error}
          notice={notice}
          sessionExpired={status.session_expired}
          conflict={conflict}
          onDismissConflict={() => setConflict(null)}
        />

        {tab === "status" ? (
          <DevelopmentProfiler id="StatusTab">
            <StatusTab
              status={status}
              busy={busy}
              remoteFiles={remoteFiles}
              onRetry={handleRetryJob}
              onOpenHistory={handleOpenHistory}
              onOpenOffice={handleOpenOffice}
              onKeepLocal={handleKeepLocal}
              onAcceptServer={handleAcceptServer}
            />
          </DevelopmentProfiler>
        ) : null}

        {tab === "folders" ? (
          <DevelopmentProfiler id="FoldersTab">
            <FoldersTab
              status={status}
              busy={busy}
              logicalRoot={logicalRoot}
              localPath={localPath}
              ruleKind={ruleKind}
              rulePattern={rulePattern}
              recursive={recursive}
              filterEnabled={filterEnabled}
              onFilterEnabledChange={setFilterEnabled}
              onLogicalRootChange={(value) => {
                setLogicalRoot(value);
                logicalRootEdited.current = value.trim() !== "";
              }}
              onLocalPathChange={applyLocalPath}
              onRuleKindChange={setRuleKind}
              onRulePatternChange={setRulePattern}
              onRecursiveChange={setRecursive}
              onChooseFolder={() => void onChooseFolder()}
              onRegister={(event) => void onRegisterFolder(event)}
              onUnregister={(folderId, folderLogicalRoot) =>
                void onUnregisterFolder(folderId, folderLogicalRoot)
              }
              onManageAccess={(remoteId, label) => setAccessTarget({ remoteId, label })}
              onSharedBound={(next) => setStatus((prev) => mergeStatusSnapshot(prev, next))}
              dropActive={dropActive}
            />
          </DevelopmentProfiler>
        ) : null}

        {tab === "settings" && settings ? (
          <SettingsTab
            settings={settings}
            busy={busy}
            onChange={setSettings}
            onLocaleChange={onLocaleChange}
            onUpdateFound={setPendingUpdate}
            onSubmit={(event) => void onSaveSettings(event)}
          />
        ) : null}
      </section>
      {historyTarget ? (
        <DevelopmentProfiler id="VersionHistoryDialog">
          <VersionHistoryDialog
            fileId={historyTarget.fileId}
            label={historyTarget.label}
            onClose={() => setHistoryTarget(null)}
          />
        </DevelopmentProfiler>
      ) : null}
      {accessTarget ? (
        <DevelopmentProfiler id="AccessDialog">
          <AccessDialog
            remoteId={accessTarget.remoteId}
            label={accessTarget.label}
            onClose={() => setAccessTarget(null)}
          />
        </DevelopmentProfiler>
      ) : null}
      {officeTarget ? (
        <OfficeEditor
          session={officeTarget.session}
          label={officeTarget.label}
          onClose={() => setOfficeTarget(null)}
        />
      ) : null}
      {pendingUpdate ? (
        <UpdateDialog
          info={pendingUpdate}
          onDismiss={() => setPendingUpdate(null)}
        />
      ) : null}
    </main>
  );
}
