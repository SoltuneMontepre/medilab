import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError, type Notification, type NotificationPage } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { documentPath } from "../documents/documentPath";

type Load =
  | { state: "loading" }
  | { state: "ready"; notifications: Notification[]; nextAfter: number | null }
  | { state: "unreachable" }
  | { state: "refused"; message: string };

/** The person's notifications, unread first, as the web's inbox has them: opening one marks it read and opens its
 * document. */
export function NotificationsScreen() {
  const t = useT();
  const { call, language } = useSession();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [problem, setProblem] = useState<Load | null>(null);

  const page = useCallback(
    async (after: number | null): Promise<NotificationPage> =>
      (await call<NotificationPage>(after ? `/notifications?after=${after}` : "/notifications")) ?? {
        notifications: [],
        next_after: null,
      },
    [call],
  );

  const first = useCallback(async (): Promise<Load> => {
    try {
      const answer = await page(null);
      return { state: "ready", notifications: answer.notifications, nextAfter: answer.next_after };
    } catch (error) {
      return failed(error);
    }
  }, [page]);

  useEffect(() => {
    let shown = true;
    first()
      .then((loaded) => shown && setLoad(loaded))
      .catch(() => shown && setLoad({ state: "unreachable" }));
    return () => {
      shown = false;
    };
  }, [first]);

  async function retry() {
    setLoad({ state: "loading" });
    setLoad(await first());
  }

  async function more() {
    if (load.state !== "ready" || !load.nextAfter) {
      return;
    }
    try {
      const answer = await page(load.nextAfter);
      setLoad({
        state: "ready",
        notifications: [...load.notifications, ...answer.notifications],
        nextAfter: answer.next_after,
      });
    } catch (error) {
      setProblem(failed(error));
    }
  }

  async function open(notification: Notification) {
    setProblem(null);
    if (!notification.read) {
      try {
        await call(`/notifications/${notification.id}/read`, { method: "POST" });
      } catch (error) {
        setProblem(failed(error));
        return;
      }
      setLoad((current) =>
        current.state === "ready"
          ? {
              ...current,
              notifications: current.notifications.map((item) =>
                item.id === notification.id ? { ...item, read: true } : item,
              ),
            }
          : current,
      );
    }
    if (notification.document) {
      router.push(documentPath(notification.document));
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={shared.title}>{t("notifications.title")}</Text>
      {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
      {load.state === "unreachable" && <Unreachable onRetry={retry} />}
      {load.state === "refused" && <Text style={shared.error}>{load.message}</Text>}
      {problem?.state === "unreachable" && <Unreachable onRetry={() => setProblem(null)} />}
      {problem?.state === "refused" && <Text style={shared.error}>{problem.message}</Text>}
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.list}>
          {load.notifications.length === 0 && <Text style={shared.detail}>{t("notifications.empty")}</Text>}
          {load.notifications.map((notification) => (
            <Pressable
              key={notification.id}
              accessibilityRole="button"
              accessibilityLabel={[
                notification.title,
                notification.document?.code,
                notification.read ? null : t("notifications.unread"),
              ]
                .filter(Boolean)
                .join(", ")}
              style={[styles.item, !notification.read && styles.unread]}
              onPress={() => open(notification)}
            >
              <Text style={[shared.label, !notification.read && styles.unreadText]}>{notification.title}</Text>
              {!!notification.document?.code && <Text style={shared.detail}>{notification.document.code}</Text>}
              <Text style={shared.detail}>{new Date(notification.date).toLocaleString(language)}</Text>
            </Pressable>
          ))}
          {load.nextAfter !== null && (
            <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={more}>
              <Text style={shared.secondaryButtonText}>{t("more")}</Text>
            </Pressable>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

// A refused key has already returned the person to sign-in.
function failed(error: unknown): Load {
  if (error instanceof UnreachableError) {
    return { state: "unreachable" };
  }
  if (error instanceof ApiError) {
    return { state: "refused", message: error.message };
  }
  throw error;
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24, gap: 16 },
  list: { gap: 8 },
  item: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12, gap: 4 },
  unread: { borderColor: colors.primary },
  unreadText: { fontWeight: "700" },
});
