import { router } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Notification, NotificationPage } from "../../api";
import { useBadges } from "../../badges";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { documentPath } from "../documents/documentPath";
import { Icon } from "../shared/Icon";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";
import { formatMoment } from "../tasks/taskText";

interface Listed {
  notifications: Notification[];
  nextAfter: number | null;
}

/** The person's notifications, unread first, as the web's inbox has them: opening one marks it read and opens its
 * document. */
export function NotificationsScreen() {
  const t = useT();
  const { call } = useSession();
  const badges = useBadges();
  const [problem, setProblem] = useState<{ load: Load<never>; retry: () => void } | null>(null);

  const page = useCallback(
    async (after: number | null): Promise<Listed> => {
      const answer = await call<NotificationPage>(after ? `/notifications?after=${after}` : "/notifications");
      return { notifications: answer?.notifications ?? [], nextAfter: answer?.next_after ?? null };
    },
    [call],
  );
  const first = useCallback(() => page(null), [page]);
  const { load, setLoad, reload, refresh } = useLoad(first);

  async function more() {
    if (load.state !== "ready" || !load.value.nextAfter) {
      return;
    }
    setProblem(null);
    try {
      const next = await page(load.value.nextAfter);
      setLoad({
        state: "ready",
        value: { notifications: [...load.value.notifications, ...next.notifications], nextAfter: next.nextAfter },
      });
    } catch (error) {
      setProblem({ load: failed(error), retry: () => void more() });
    }
  }

  async function open(notification: Notification) {
    setProblem(null);
    if (!notification.read) {
      try {
        await call(`/notifications/${notification.id}/read`, { method: "POST" });
      } catch (error) {
        setProblem({ load: failed(error), retry: () => void open(notification) });
        return;
      }
      if (load.state === "ready") {
        setLoad({
          state: "ready",
          value: {
            ...load.value,
            notifications: load.value.notifications.map((item) =>
              item.id === notification.id ? { ...item, read: true } : item,
            ),
          },
        });
      }
      badges.refresh();
    }
    if (notification.document) {
      router.push(documentPath(notification.document));
    }
  }

  return (
    <Screen title={t("notifications.title")} bell={false} scroll={false}>
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value.notifications : []}
        keyOf={(notification) => notification.id}
        renderItem={(notification) => <Row notification={notification} onOpen={() => open(notification)} />}
        icon="bell-outline"
        empty={t("notifications.empty")}
        onRetry={reload}
        onRefresh={refresh}
        hasMore={load.state === "ready" && load.value.nextAfter !== null}
        onMore={more}
        header={
          problem ? <ActionProblem problem={problem.load} gone={t("document.gone")} onRetry={problem.retry} /> : undefined
        }
      />
    </Screen>
  );
}

function Row({ notification, onOpen }: Readonly<{ notification: Notification; onOpen: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const unread = !notification.read;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[notification.title, notification.document?.code, unread ? t("notifications.unread") : null]
        .filter(Boolean)
        .join(", ")}
      style={({ pressed }) => [shared.card, styles.row, unread && styles.unread, pressed && styles.pressed]}
      onPress={onOpen}
    >
      <View style={[styles.icon, unread && styles.iconUnread]}>
        <Icon name={unread ? "bell-ring-outline" : "bell-outline"} size={20} color={unread ? colors.primary : colors.textMuted} />
      </View>
      <View style={styles.text}>
        <Text style={[shared.label, unread && styles.unreadText]}>{notification.title}</Text>
        {!!notification.document?.code && <Text style={shared.detail}>{notification.document.code}</Text>}
        <Text style={shared.detail}>{formatMoment(notification.date, language)}</Text>
      </View>
      {unread && <View style={styles.dot} />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space.md },
  unread: { borderColor: colors.accentLight, backgroundColor: colors.accentSoft },
  pressed: { opacity: 0.7 },
  icon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.secondaryLight,
  },
  iconUnread: { backgroundColor: colors.surface },
  text: { flex: 1, gap: 2 },
  unreadText: { fontWeight: "700" },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent },
});
