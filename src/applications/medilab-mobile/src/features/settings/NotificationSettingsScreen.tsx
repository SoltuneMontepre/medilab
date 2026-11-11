import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError, type PushPreference } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";

type Load =
  | { state: "loading" }
  | { state: "ready"; preferences: PushPreference[] }
  | { state: "unreachable" }
  | { state: "refused"; message: string };

/** The person's push preferences per event, the same ones the web's notification preferences show. A mandatory
 * event's push stays on. */
export function NotificationSettingsScreen() {
  const t = useT();
  const { call } = useSession();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [problem, setProblem] = useState<string | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const read = useCallback(async (): Promise<Load> => {
    try {
      const answer = await call<{ preferences: PushPreference[] }>("/notification-preferences");
      return { state: "ready", preferences: answer?.preferences ?? [] };
    } catch (error) {
      if (error instanceof UnreachableError) {
        return { state: "unreachable" };
      }
      if (error instanceof ApiError) {
        return { state: "refused", message: error.message };
      }
      throw error;
    }
  }, [call]);

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

  async function choose(preference: PushPreference, push: boolean) {
    setProblem(null);
    setUnreachable(false);
    try {
      const saved = await call<PushPreference>(`/notification-preferences/${encodeURIComponent(preference.event)}`, {
        method: "PUT",
        body: { push },
      });
      if (saved) {
        setLoad((current) =>
          current.state === "ready"
            ? {
                ...current,
                preferences: current.preferences.map((item) => (item.event === saved.event ? saved : item)),
              }
            : current,
        );
      }
    } catch (error) {
      if (error instanceof UnreachableError) {
        setUnreachable(true);
      } else if (error instanceof ApiError) {
        setProblem(error.message);
      } else {
        throw error;
      }
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={shared.title}>{t("settings.title")}</Text>
      <Text style={shared.detail}>{t("settings.explanation")}</Text>
      {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
      {load.state === "unreachable" && <Unreachable onRetry={retry} />}
      {load.state === "refused" && <Text style={shared.error}>{load.message}</Text>}
      {unreachable && <Unreachable onRetry={() => setUnreachable(false)} />}
      {problem && <Text style={shared.error}>{problem}</Text>}
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.list}>
          {load.preferences.map((preference) => (
            <View key={preference.event} style={styles.row}>
              <View style={styles.name}>
                <Text style={shared.label}>{preference.name}</Text>
                {preference.mandatory && <Text style={shared.detail}>{t("settings.mandatory")}</Text>}
              </View>
              <Switch
                accessibilityLabel={preference.name}
                value={preference.push}
                disabled={preference.mandatory}
                onValueChange={(push) => choose(preference, push)}
              />
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24, gap: 16 },
  list: { gap: 4 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  name: { flex: 1, gap: 2 },
});
