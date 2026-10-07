import { useEffect, useRef, useState } from "react";
import type { OfficeSession } from "../../types";
import { useT } from "../../locale";

/** Instance editor ONLYOFFICE tối thiểu app cần: chỉ để hủy khi đóng. */
type DocsEditor = {
  destroyEditor?: () => void;
};

declare global {
  /** Mở rộng `Window` toàn cục: script `api.js` của ONLYOFFICE gắn `DocsAPI` lên `window` sau khi tải xong. */
  interface Window {
    DocsAPI?: {
      DocEditor: new (placeholder: string, config: Record<string, unknown>) => DocsEditor;
    };
  }
}

const PLACEHOLDER_ID = "medilab-onlyoffice-editor";

/** URL script `api.js` của ONLYOFFICE Document Server, từ URL server đã cấu hình. */
function docsApiSrc(serverUrl: string): string {
  return `${serverUrl.replace(/\/$/, "")}/web-apps/apps/api/documents/api.js`;
}

/** Quá thời gian này mà script `api.js` chưa tải xong thì coi như không kết nối được. */
const SCRIPT_TIMEOUT_MS = 15_000;
/** Quá thời gian này mà editor chưa báo sẵn sàng thì báo lỗi thay vì treo ở "đang tải". */
const EDITOR_READY_TIMEOUT_MS = 60_000;

/** Nạp script `DocsAPI` của ONLYOFFICE nếu chưa có sẵn. Thẻ script của một lần nạp HỎNG phải bị
 * gỡ đi: nếu tái dùng thẻ đã lỗi thì sự kiện load/error của nó đã bắn xong từ trước, promise
 * không bao giờ kết thúc và màn hình treo mãi ở "Đang tải…" (lần mở thứ hai khi máy chủ
 * ONLYOFFICE không chạy). Có giới hạn thời gian cho trường hợp kết nối treo không phản hồi. */
function loadDocsApi(serverUrl: string): Promise<void> {
  if (window.DocsAPI) {
    return Promise.resolve();
  }
  document.querySelector(`script[data-onlyoffice-api="1"]`)?.remove();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    /** Gỡ thẻ script hỏng để lần thử sau nạp lại từ đầu. */
    const fail = (reason: string) => {
      window.clearTimeout(timer);
      script.remove();
      reject(new Error(reason));
    };
    const timer = window.setTimeout(() => fail("timeout"), SCRIPT_TIMEOUT_MS);
    script.src = docsApiSrc(serverUrl);
    script.async = true;
    script.dataset.onlyofficeApi = "1";
    script.onload = () => {
      window.clearTimeout(timer);
      resolve();
    };
    script.onerror = () => fail("script");
    document.head.appendChild(script);
  });
}

/** True nếu đường dẫn có phần mở rộng văn phòng hỗ trợ chỉnh sửa trực tuyến (docx/xlsx/pptx). */
export function isOfficeDocument(path: string): boolean {
  return /\.(docx|xlsx|pptx)$/i.test(path);
}

/** Props của `OfficeEditor`: phiên chỉnh sửa đã mở, nhãn hiện cho người dùng, và callback đóng. */
type OfficeEditorProps = {
  session: OfficeSession;
  label: string;
  onClose: () => void;
};

/** Nhúng ONLYOFFICE Document Server cho một phiên chỉnh sửa đã mở; tự nạp script API và hủy
 * editor khi đóng hoặc đổi phiên. */
export function OfficeEditor({ session, label, onClose }: Readonly<OfficeEditorProps>) {
  const t = useT();
  const tRef = useRef(t);
  tRef.current = t;
  const editorRef = useRef<DocsEditor | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Giai đoạn đang chờ, để người dùng thấy app đang làm gì: kết nối máy chủ → mở tài liệu.
  const [stage, setStage] = useState<"connecting" | "opening">("connecting");
  // Tăng để thử lại mà không phải đóng rồi mở lại.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let readyTimer: number | undefined;
    setReady(false);
    setError(null);
    setStage("connecting");
    void (async () => {
      try {
        await loadDocsApi(session.document_server_url);
        if (cancelled) {
          return;
        }
        if (!window.DocsAPI) {
          throw new Error("missing DocsAPI");
        }
        setStage("opening");
        // DocsAPI không có sự kiện tiến độ; nếu editor không bao giờ báo sẵn sàng (máy chủ
        // ONLYOFFICE không lấy được tệp từ Odoo, iframe bị chặn...) thì báo lỗi chứ không treo.
        readyTimer = window.setTimeout(() => {
          if (!cancelled) {
            setError(tRef.current("office.openTimeout"));
          }
        }, EDITOR_READY_TIMEOUT_MS);
        const config = {
          ...session.config,
          events: {
            onAppReady: () => {
              window.clearTimeout(readyTimer);
              if (!cancelled) {
                setReady(true);
              }
            },
            onDocumentReady: () => {
              window.clearTimeout(readyTimer);
              if (!cancelled) {
                setReady(true);
              }
            },
            onError: () => {
              window.clearTimeout(readyTimer);
              if (!cancelled) {
                setError(tRef.current("office.openFailed"));
              }
            },
          },
        };
        editorRef.current = new window.DocsAPI.DocEditor(PLACEHOLDER_ID, config);
      } catch {
        if (!cancelled) {
          setError(tRef.current("office.connectFailed"));
        }
      }
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(readyTimer);
      try {
        editorRef.current?.destroyEditor?.();
      } catch {
        /* editor may already be gone */
      }
      editorRef.current = null;
    };
  }, [session, attempt]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-900/70">
      <div className="flex items-center justify-between border-b bg-white px-4 py-2">
        <div>
          <h2 className="text-lg font-semibold">{t("office.title")}</h2>
          <p className="text-sm text-slate-600">{label}</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          {t("action.close")}
        </button>
      </div>
      {error ? (
        <div className="m-4 flex flex-wrap items-center justify-between gap-3 rounded bg-red-50 p-3 text-sm text-red-700">
          <p>{error}</p>
          <button
            type="button"
            className="btn btn-secondary shrink-0"
            onClick={() => setAttempt((current) => current + 1)}
          >
            {t("office.retry")}
          </button>
        </div>
      ) : null}
      {!ready && !error ? (
        <output className="flex items-center gap-3 px-4 py-3 text-sm text-white">
          <span className="sync-spinner" aria-hidden="true" />
          <span>
            {t(stage === "connecting" ? "office.stage.connecting" : "office.stage.opening")}
            <span className="ml-2 text-slate-300">
              {t(stage === "connecting" ? "office.stage.step1" : "office.stage.step2")}
            </span>
          </span>
        </output>
      ) : null}
      <div className="min-h-0 flex-1 bg-white">
        <div id={PLACEHOLDER_ID} className="h-full w-full" />
      </div>
    </div>
  );
}
