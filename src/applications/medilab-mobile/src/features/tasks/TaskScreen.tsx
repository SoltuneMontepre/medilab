import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, type TaskDetail } from "../../api";
import { useReloadOnReturn } from "../../focus";
import type { MessageKey } from "../../i18n";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { LoadNotice } from "../connection/LoadNotice";
import { Unreachable } from "../connection/Unreachable";
import { documentPath } from "../documents/documentPath";
import { formatMoment, statusKey } from "./taskText";

type Action = "claim" | "start" | "done";

const ACTIONS: { action: Action; label: MessageKey }[] = [
  { action: "claim", label: "task.claim" },
  { action: "start", label: "task.start" },
  { action: "done", label: "task.done" },
];

/** A task as the person may read it, with the actions the web's form shows them: claiming it from their queue,
 * starting it, marking a task created by hand done, assigning it, and opening its document at the action to take. */
export function TaskScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [problem, setProblem] = useState<{ action: Action; load: Load<never> } | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async () => {
    const task = await call<TaskDetail>(`/tasks/${encodeURIComponent(id)}`);
    if (!task) {
      throw new ApiError("not_found", "", 404);
    }
    return task;
  }, [call, id]);
  const { load, setLoad, reload } = useLoad(read);
  useReloadOnReturn(reload);

  async function act(action: Action) {
    setProblem(null);
    setBusy(true);
    try {
      const task = await call<TaskDetail>(`/tasks/${encodeURIComponent(id)}/${action}`, { method: "POST" });
      if (task) {
        setLoad({ state: "ready", value: task });
      }
    } catch (error) {
      setProblem({ action, load: failed(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <LoadNotice load={load} gone={t("task.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.content}>
          <Details task={load.value} />
          {problem?.load.state === "unreachable" && <Unreachable onRetry={() => act(problem.action)} />}
          {(problem?.load.state === "refused" || problem?.load.state === "gone") && (
            <Text accessibilityRole="alert" style={shared.error}>
              {problem.load.state === "refused" ? problem.load.message : t("task.gone")}
            </Text>
          )}
          {ACTIONS.filter(({ action }) => load.value.actions[action]).map(({ action, label }) => (
            <Pressable
              key={action}
              accessibilityRole="button"
              accessibilityState={{ disabled: busy }}
              disabled={busy}
              style={shared.primaryButton}
              onPress={() => act(action)}
            >
              <Text style={shared.primaryButtonText}>{t(label)}</Text>
            </Pressable>
          ))}
          {load.value.actions.assign && (
            <Pressable
              accessibilityRole="button"
              style={shared.secondaryButton}
              onPress={() => router.push({ pathname: "/tasks/[id]/assign", params: { id } })}
            >
              <Text style={shared.secondaryButtonText}>{t("task.assign")}</Text>
            </Pressable>
          )}
          {load.value.document && (
            <Pressable
              accessibilityRole="button"
              style={shared.secondaryButton}
              onPress={() => load.value.document && router.push(documentPath(load.value.document))}
            >
              <Text style={shared.secondaryButtonText}>
                {t("task.openDocument", { code: load.value.document.code || load.value.name })}
              </Text>
            </Pressable>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ task }: Readonly<{ task: TaskDetail }>) {
  const t = useT();
  const { language } = useSession();
  const facts: [MessageKey, string][] = [
    ["task.type", task.type],
    ["task.statusLabel", t(statusKey(task.status))],
    ["task.deadlineLabel", task.deadline ? formatMoment(task.deadline, language) : ""],
    ["task.planned", task.planned_start ? formatMoment(task.planned_start, language) : ""],
    ["task.plannedEnd", task.planned_end ? formatMoment(task.planned_end, language) : ""],
    ["task.doneAtLabel", task.done_at ? formatMoment(task.done_at, language) : ""],
    ["task.department", task.department],
    ["task.assignee", task.assignee],
    ["task.assignedBy", task.assigned_by],
    ["task.location", task.location],
    ["task.reason", task.reassign_reason],
  ];
  return (
    <>
      <Text style={shared.title}>{task.name}</Text>
      {!!task.document?.code && <Text style={shared.detail}>{task.document.code}</Text>}
      {facts
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <View key={label} style={styles.fact}>
            <Text style={shared.detail}>{t(label)}</Text>
            <Text style={shared.label}>{value}</Text>
          </View>
        ))}
      {!!task.note && <Text style={styles.note}>{task.note}</Text>}
      {task.steps.length > 0 && (
        <View style={styles.steps}>
          <Text accessibilityRole="header" style={styles.heading}>
            {t("task.steps")}
          </Text>
          {task.steps.map((step, index) => (
            <View key={`${index}-${step.instruction}`} style={styles.step}>
              <Text style={shared.label}>
                {t("task.step", { number: index + 1, minutes: step.minutes })}
              </Text>
              <Text style={styles.note}>{step.instruction}</Text>
              {!!step.note && <Text style={shared.detail}>{step.note}</Text>}
              {!!step.location && <Text style={shared.detail}>{t("task.stepLocation", { location: step.location })}</Text>}
            </View>
          ))}
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24 },
  content: { gap: 12, paddingBottom: 24 },
  fact: { gap: 2 },
  note: { fontSize: 15, color: colors.text },
  steps: { gap: 8 },
  heading: { fontSize: 18, fontWeight: "600", color: colors.text },
  step: { borderLeftWidth: 3, borderLeftColor: colors.border, paddingLeft: 12, gap: 2 },
});
