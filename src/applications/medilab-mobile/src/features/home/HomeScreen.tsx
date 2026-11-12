import { router } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, UnreachableError, type Me, type Task, type TaskDay } from "../../api";
import { useReloadOnReturn } from "../../focus";
import { useLoad } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { taskPath } from "../documents/documentPath";
import { TaskRow } from "../tasks/TaskRow";

interface Home {
  me: Me;
  day: TaskDay;
}

/** The person's day, as the Tasks app opens on it: today's plan, the next tasks to do and the tasks waiting in their
 * queues, with the way to their to-do list, their notifications and signing out. */
export function HomeScreen() {
  const t = useT();
  const session = useSession();
  const { call } = session;
  const [refusal, setRefusal] = useState<string | null>(null);
  const [signOutUnreachable, setSignOutUnreachable] = useState(false);

  // Reading the person also checks the phone's key; a refused key returns the person to sign-in.
  const read = useCallback(async (): Promise<Home> => {
    const [me, day] = await Promise.all([call<Me>("/me"), call<TaskDay>("/tasks/today")]);
    if (!me || !day) {
      throw new UnreachableError();
    }
    return { me, day };
  }, [call]);
  const { load, reload } = useLoad(read);
  useReloadOnReturn(reload);

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
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={shared.title}>MediLab</Text>
        <Text style={shared.detail}>{t("home.server", { url: session.serverUrl })}</Text>
        {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
        {load.state === "unreachable" && <Unreachable onRetry={reload} />}
        {load.state === "refused" && <Text style={shared.error}>{load.message}</Text>}
        {load.state === "ready" && <Day home={load.value} />}
        {signOutUnreachable && <Unreachable onRetry={signOut} />}
        {refusal && <Text style={shared.error}>{refusal}</Text>}
        <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={signOut}>
          <Text style={shared.secondaryButtonText}>{t("signOut.submit")}</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function Day({ home }: Readonly<{ home: Home }>) {
  const t = useT();
  const { me, day } = home;
  return (
    <>
      <Text style={shared.label}>{t("home.signedInAs", { name: day.person })}</Text>
      <Text style={shared.detail}>
        {t("day.summary", { open: day.open_count, overdue: day.overdue_count, today: day.due_today_count })}
      </Text>
      <Section title={t("day.plannedToday")} tasks={day.planned_today} />
      <Section title={t("day.nextUp")} tasks={day.next_up} empty={t("day.nothingToDo")} />
      <Section
        title={t("day.claimable", { count: day.claimable_count })}
        tasks={day.claimable}
        more={day.claimable_count > day.claimable.length ? "queue" : undefined}
      />
      <Pressable
        accessibilityRole="button"
        style={shared.primaryButton}
        onPress={() => router.push({ pathname: "/tasks", params: { list: "open" } })}
      >
        <Text style={shared.primaryButtonText}>{t("home.todo")}</Text>
      </Pressable>
      {me.can.create_tasks && (
        <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={() => router.push("/tasks/new")}>
          <Text style={shared.secondaryButtonText}>{t("home.newTask")}</Text>
        </Pressable>
      )}
      <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={() => router.push("/notifications")}>
        <Text style={shared.secondaryButtonText}>{t("home.notifications")}</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        style={shared.secondaryButton}
        onPress={() => router.push("/notification-settings")}
      >
        <Text style={shared.secondaryButtonText}>{t("home.notificationSettings")}</Text>
      </Pressable>
    </>
  );
}

function Section({
  title,
  tasks,
  empty,
  more,
}: Readonly<{ title: string; tasks: Task[]; empty?: string; more?: "queue" }>) {
  const t = useT();
  if (!tasks.length && !empty) {
    return null;
  }
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.heading}>
        {title}
      </Text>
      {!tasks.length && <Text style={shared.detail}>{empty}</Text>}
      {tasks.map((task) => (
        <TaskRow key={task.id} task={task} onPress={() => router.push(taskPath(task.id))} />
      ))}
      {more && (
        <Pressable
          accessibilityRole="button"
          style={shared.secondaryButton}
          onPress={() => router.push({ pathname: "/tasks", params: { list: more } })}
        >
          <Text style={shared.secondaryButtonText}>{t("day.seeQueue")}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 24, gap: 16 },
  section: { gap: 8 },
  heading: { fontSize: 18, fontWeight: "600" },
});
