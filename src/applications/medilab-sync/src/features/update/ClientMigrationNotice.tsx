import { useEffect, useState } from "react";
import { useT } from "../../locale";
import {
  getClientMigration,
  onClientMigrationChanged,
  openClientDownload,
  type ClientMigration,
} from "../../lib/tauri";

export function useClientMigration(serverUrl: string) {
  const [notice, setNotice] = useState<ClientMigration | null>(null);
  useEffect(() => {
    setNotice(null);
    let active = true;
    let revision = 0;
    let unlisten: (() => void) | undefined;
    const refresh = () => {
      const requested = ++revision;
      void getClientMigration(serverUrl).then((value) => {
        if (active && requested === revision) setNotice(value);
      }).catch(() => {});
    };
    void onClientMigrationChanged(refresh).then((stop) => {
      if (!active) {
        stop();
        return;
      }
      unlisten = stop;
      refresh();
    }).catch(() => {});
    return () => {
      active = false;
      unlisten?.();
    };
  }, [serverUrl]);
  return notice;
}

export function ClientMigrationNotice({ notice, serverUrl, onOpen }: Readonly<{
  notice: ClientMigration | null;
  serverUrl?: string;
  onOpen?: () => Promise<void>;
}>) {
  const t = useT();
  const [error, setError] = useState<string | null>(null);
  if (!notice) return null;
  return (
    <aside role="alert" className="m-4 rounded border border-amber-300 bg-amber-50 p-4 text-amber-950">
      <h2 className="font-semibold">{t("migration.required")}</h2>
      <p>{notice.message}</p>
      <p className="mt-2 text-sm">{t("migration.preserve")}</p>
      {notice.download_url ? <>
        <p className="mt-2 break-all text-sm">{notice.download_url}</p>
        <button type="button" className="btn btn-primary mt-2" onClick={() => {
          setError(null);
          void (onOpen ? onOpen() : openClientDownload(serverUrl))
            .catch((reason: unknown) => setError(String(reason)));
        }}>{t("migration.download")}</button>
      </> : <p className="mt-2 text-sm">{t("migration.contact")}</p>}
      {error ? <p className="mt-2 text-red-700">{error}</p> : null}
    </aside>
  );
}
