import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError, type MediLabDocument } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles } from "../../styles";
import { Unreachable } from "../connection/Unreachable";

type Load =
  | { state: "loading" }
  | { state: "ready"; document: MediLabDocument }
  | { state: "gone" }
  | { state: "unreachable" }
  | { state: "refused"; message: string };

/** The document a push or a notification opens, read with the person's rights. A document they can no longer see
 * says so instead of showing an empty screen. */
export function DocumentScreen() {
  const t = useT();
  const { call } = useSession();
  const { model, id } = useLocalSearchParams<{ model: string; id: string }>();
  const [load, setLoad] = useState<Load>({ state: "loading" });

  const read = useCallback(async (): Promise<Load> => {
    try {
      const document = await call<MediLabDocument>(
        `/documents/${encodeURIComponent(model)}/${encodeURIComponent(id)}`,
      );
      return document ? { state: "ready", document } : { state: "gone" };
    } catch (error) {
      if (error instanceof UnreachableError) {
        return { state: "unreachable" };
      }
      if (error instanceof ApiError) {
        return error.code === "not_found" ? { state: "gone" } : { state: "refused", message: error.message };
      }
      throw error;
    }
  }, [call, model, id]);

  useEffect(() => {
    let shown = true;
    read()
      .then((loaded) => shown && setLoad(loaded))
      .catch(() => shown && setLoad({ state: "unreachable" }));
    return () => {
      shown = false;
    };
  }, [read]);

  async function retry() {
    setLoad({ state: "loading" });
    setLoad(await read());
  }

  return (
    <SafeAreaView style={styles.screen}>
      {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
      {load.state === "unreachable" && <Unreachable onRetry={retry} />}
      {load.state === "gone" && (
        <Text accessibilityRole="alert" style={styles.error}>
          {t("document.gone")}
        </Text>
      )}
      {load.state === "refused" && <Text style={styles.error}>{load.message}</Text>}
      {load.state === "ready" && (
        <>
          <Text style={styles.title}>{load.document.title}</Text>
          {!!load.document.code && load.document.code !== load.document.title && (
            <Text style={styles.detail}>{load.document.code}</Text>
          )}
          <Pressable
            accessibilityRole="button"
            style={styles.secondaryButton}
            onPress={() => Linking.openURL(load.document.url)}
          >
            <Text style={styles.secondaryButtonText}>{t("document.openOnWeb")}</Text>
          </Pressable>
        </>
      )}
    </SafeAreaView>
  );
}
