import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ActivityIndicator, AppState, StyleSheet, View } from "react-native";

import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors } from "../../theme";
import { checkRelease, installApk, installCode, takesUpdates, type Release } from "./release";
import { UpdatingScreen } from "./UpdatingScreen";

type Gate = { kind: "checking" } | { kind: "open" } | { kind: "updating"; release: Release; failed: boolean };

// Android also sends the app to the background while it shows a permission dialog, the camera, a picker or the
// installer it opened itself; a shorter absence is that, not the person leaving the app.
const AWAY_MS = 60_000;

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
 * and whenever the person comes back to it after a minute away; the person cannot skip the update. */
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
    void check();
    let leftAt: number | null = null;
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") {
        leftAt ??= Date.now();
        return;
      }
      const away = leftAt !== null && Date.now() - leftAt >= AWAY_MS;
      leftAt = null;
      if (away) {
        void check();
      }
    });
    return () => subscription.remove();
  }, [check]);

  if (gate.kind === "checking") {
    return (
      <View style={styles.checking}>
        <ActivityIndicator size="large" color={colors.primary} accessibilityLabel={t("update.checking")} />
      </View>
    );
  }
  if (gate.kind === "updating") {
    return <UpdatingScreen release={gate.release} failed={gate.failed} onRetry={check} />;
  }
  return children;
}

const styles = StyleSheet.create({
  checking: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg },
});
