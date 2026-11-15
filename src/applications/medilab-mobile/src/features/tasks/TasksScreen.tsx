import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Task, TaskList, TaskPage } from "../../api";
import { useReloadOnReturn } from "../../focus";
import type { MessageKey } from "../../i18n";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { taskPath } from "../documents/documentPath";
import { TaskRow } from "./TaskRow";

const LISTS: { list: TaskList; label: MessageKey; empty: MessageKey }[] = [
  { list: "open", label: "tasks.open", empty: "tasks.openEmpty" },
  { list: "finished", label: "tasks.finished", empty: "tasks.finishedEmpty" },
  { list: "queue", label: "tasks.queue", empty: "tasks.queueEmpty" },
];

interface Listed {
  tasks: Task[];
  nextAfter: number | null;
}

/** The person's to-do list: their open tasks, soonest deadline first, their finished tasks, and the tasks waiting in
 * the queues they can claim from, the same as the web's lists. */
export function TasksScreen() {
  const t = useT();
  const { call } = useSession();
  const params = useLocalSearchParams<{ list?: string }>();
  const [list, setList] = useState<TaskList>(
    LISTS.some((item) => item.list === params.list) ? (params.list as TaskList) : "open",
  );
  const [problem, setProblem] = useState<Load<never> | null>(null);

  const page = useCallback(
    async (after: number | null): Promise<Listed> => {
      const query = after ? `list=${list}&after=${after}` : `list=${list}`;
      const answer = await call<TaskPage>(`/tasks?${query}`);
      return { tasks: answer?.tasks ?? [], nextAfter: answer?.next_after ?? null };
    },
    [call, list],
  );
  const first = useCallback(() => page(null), [page]);
  const { load, setLoad, reload } = useLoad(first);
  useReloadOnReturn(reload);

  async function more() {
    if (load.state !== "ready" || !load.value.nextAfter) {
      return;
    }
    setProblem(null);
    try {
      const next = await page(load.value.nextAfter);
      setLoad({ state: "ready", value: { tasks: [...load.value.tasks, ...next.tasks], nextAfter: next.nextAfter } });
    } catch (error) {
      setProblem(failed(error));
    }
  }

  const current = LISTS.find((item) => item.list === list) ?? LISTS[0];
  return (
    <SafeAreaView style={styles.screen}>
      <Text style={shared.title}>{t("tasks.title")}</Text>
      <View accessibilityRole="tablist" style={styles.tabs}>
        {LISTS.map((item) => (
          <Pressable
            key={item.list}
            accessibilityRole="tab"
            accessibilityState={{ selected: item.list === list }}
            style={[styles.tab, item.list === list && styles.selected]}
            onPress={() => {
              setProblem(null);
              setList(item.list);
            }}
          >
            <Text style={[styles.tabText, item.list === list && styles.selectedText]}>{t(item.label)}</Text>
          </Pressable>
        ))}
      </View>
      {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
      {load.state === "unreachable" && <Unreachable onRetry={reload} />}
      {load.state === "refused" && <Text style={shared.error}>{load.message}</Text>}
      {problem?.state === "unreachable" && <Unreachable onRetry={more} />}
      {problem?.state === "refused" && <Text style={shared.error}>{problem.message}</Text>}
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.list}>
          {load.value.tasks.length === 0 && <Text style={shared.detail}>{t(current.empty)}</Text>}
          {load.value.tasks.map((task) => (
            <TaskRow key={task.id} task={task} onPress={() => router.push(taskPath(task.id))} />
          ))}
          {load.value.nextAfter !== null && (
            <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={more}>
              <Text style={shared.secondaryButtonText}>{t("more")}</Text>
            </Pressable>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24, gap: 16 },
  tabs: { flexDirection: "row", gap: 8 },
  tab: { flex: 1, borderWidth: 1, borderColor: colors.primary, borderRadius: 8, paddingVertical: 8, alignItems: "center" },
  selected: { backgroundColor: colors.primary },
  tabText: { color: colors.primary, fontWeight: "500" },
  selectedText: { color: "#ffffff" },
  list: { gap: 8 },
});
