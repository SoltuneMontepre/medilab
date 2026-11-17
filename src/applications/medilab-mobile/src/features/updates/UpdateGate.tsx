import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ActivityIndicator, AppState } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles } from "../../styles";
import { checkRelease, installApk, installCode, takesUpdates, type Release } from "./release";
import { UpdatingScreen } from "./UpdatingScreen";

type Gate = { kind: "checking" } | { kind: "open" } | { kind: "updating"; release: Release; failed: boolean };

async function install(release: Release): Promise<boolean> {
  if (release.action === "code") {
    return installCode();
  }
  if (release.action === "install") {
    await installApk(release);
  }
  // The installer, or an administrator for a version no longer served, finishes the update; the app stays shut.
  return true;
}

/** Keeps the app shut behind the updating screen while MediLab has an update for the phone. The app asks when it starts
 * and whenever it comes back to the foreground; the person cannot skip the update. */
export function UpdateGate({ children }: Readonly<{ children: ReactNode }>) {
  const t = useT();
  const { language } = useSession();
  const [gate, setGate] = useState<Gate>(() => (takesUpdates() ? { kind: "checking" } : { kind: "open" }));
  const checking = useRef(false);
  const languageRef = useRef(language);
  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const check = useCallback(async () => {
    if (!takesUpdates() || checking.current) {
      return;
    }
    checking.current = true;
    try {
      let release: Release | null;
      try {
        release = await checkRelease(languageRef.current);
      } catch {
        // A MediLab that cannot answer, which then refuses every call too, does not lock the app.
        setGate((current) => (current.kind === "updating" ? current : { kind: "open" }));
        return;
      }
      if (release === null) {
        setGate({ kind: "open" });
        return;
      }
      setGate({ kind: "updating", release, failed: false });
      try {
        if (!(await install(release))) {
          setGate({ kind: "open" });
        }
      } catch {
        // The update is refused or did not arrive: the app keeps the version it has and stays shut.
        setGate({ kind: "updating", release, failed: true });
      }
    } finally {
      checking.current = false;
    }
  }, []);

  useEffect(() => {
    check();
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        check();
      }
    });
    return () => subscription.remove();
  }, [check]);

  if (gate.kind === "checking") {
    return (
      <SafeAreaView style={styles.screen}>
        <ActivityIndicator accessibilityLabel={t("update.checking")} />
      </SafeAreaView>
    );
  }
  if (gate.kind === "updating") {
    return <UpdatingScreen release={gate.release} failed={gate.failed} onRetry={check} />;
  }
  return children;
}
