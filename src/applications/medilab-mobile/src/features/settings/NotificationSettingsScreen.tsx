import { useCallback, useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";

import { ApiError, UnreachableError, type PushPreference } from "../../api";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { LoadNotice } from "../connection/LoadNotice";
import { Unreachable } from "../connection/Unreachable";
import { Badge } from "../shared/Badge";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";

/** The person's push preferences per event, the same ones the web's notification preferences show. A mandatory
 * event's push stays on. */
export function NotificationSettingsScreen() {
  const t = useT();
  const { call } = useSession();
  const [problem, setProblem] = useState<string | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const read = useCallback(async () => {
    const answer = await call<{ preferences: PushPreference[] }>("/notification-preferences");
    return answer?.preferences ?? [];
  }, [call]);
  const { load, setLoad, reload } = useLoad(read);

  async function choose(preference: PushPreference, push: boolean) {
    setProblem(null);
    setUnreachable(false);
    try {
      const saved = await call<PushPreference>(`/notification-preferences/${encodeURIComponent(preference.event)}`, {
        method: "PUT",
        body: { push },
      });
      if (saved && load.state === "ready") {
        setLoad({ state: "ready", value: load.value.map((item) => (item.event === saved.event ? saved : item)) });
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
    <Screen title={t("settings.title")}>
      <Text style={shared.detail}>{t("settings.explanation")}</Text>
      <LoadNotice load={load} gone="" onRetry={reload} />
      {unreachable && <Unreachable onRetry={() => setUnreachable(false)} />}
      {problem && (
        <Text accessibilityRole="alert" style={shared.error}>
          {problem}
        </Text>
      )}
      {load.state === "ready" && (
        <Sheet>
          {load.value.map((preference, index) => (
            <View key={preference.event} style={[styles.row, index > 0 && styles.divided]}>
              <View style={styles.name}>
                <Text style={shared.label}>{preference.name}</Text>
                {preference.mandatory && <Badge label={t("settings.mandatory")} tone="muted" />}
              </View>
              <Switch
                accessibilityLabel={preference.name}
                value={preference.push}
                disabled={preference.mandatory}
                trackColor={{ true: colors.accentLight, false: colors.borderStrong }}
                thumbColor={preference.push ? colors.primary : colors.surface}
                onValueChange={(push) => choose(preference, push)}
              />
            </View>
          ))}
        </Sheet>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.md, minHeight: 48 },
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, paddingTop: space.md },
  name: { flex: 1, gap: space.xs },
});
