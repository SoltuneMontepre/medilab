import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles } from "../../styles";
import { Unreachable } from "../connection/Unreachable";

type Load = { state: "loading" } | { state: "ready"; modules: string[] } | { state: "unreachable" };

/** The signed-in person's start: it reads the installed modules, which also checks the phone's key, and signs out. */
export function HomeScreen() {
  const t = useT();
  const session = useSession();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [refusal, setRefusal] = useState<string | null>(null);
  const [signOutUnreachable, setSignOutUnreachable] = useState(false);
  const { call } = session;

  // The modules once read; a refused key has already returned the person to sign-in, so it leaves the screen loading.
  const loadModules = useCallback(async (): Promise<Load> => {
    try {
      const answer = await call<{ modules: string[] }>("/modules");
      return { state: "ready", modules: answer?.modules ?? [] };
    } catch (error) {
      if (error instanceof UnreachableError) {
        return { state: "unreachable" };
      }
      if (error instanceof ApiError) {
        return { state: "loading" };
      }
      throw error;
    }
  }, [call]);

  useEffect(() => {
    let shown = true;
    loadModules().then((loaded) => shown && setLoad(loaded));
    return () => {
      shown = false;
    };
  }, [loadModules]);

  async function retry() {
    setLoad({ state: "loading" });
    setLoad(await loadModules());
  }

  async function signOut() {
    setRefusal(null);
    setSignOutUnreachable(false);
    try {
      await session.signOut();
    } catch (error) {
      if (error instanceof UnreachableError) {
        setSignOutUnreachable(true);
      } else if (error instanceof ApiError) {
        setRefusal(error.message);
      } else {
        throw error;
      }
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={styles.title}>MediLab</Text>
      <Text style={styles.detail}>{t("home.server", { url: session.serverUrl })}</Text>
      {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
      {load.state === "unreachable" && <Unreachable onRetry={retry} />}
      {load.state === "ready" && <Text style={styles.label}>{t("home.signedIn")}</Text>}
      {signOutUnreachable && <Unreachable onRetry={signOut} />}
      {refusal && <Text style={styles.error}>{refusal}</Text>}
      <Pressable accessibilityRole="button" style={styles.secondaryButton} onPress={signOut}>
        <Text style={styles.secondaryButtonText}>{t("signOut.submit")}</Text>
      </Pressable>
    </SafeAreaView>
  );
}
