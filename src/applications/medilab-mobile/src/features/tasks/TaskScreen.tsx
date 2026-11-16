import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { SampleTest, TaskDetail } from "../../api";
import type { MessageKey } from "../../i18n";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useRecord } from "../../record";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { TestFacts } from "../bench/TestFacts";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { documentPath, resultPath, SAMPLE_TEST_MODEL, sampleTestPath } from "../documents/documentPath";
import { Button } from "../shared/Button";
import { ChatterButton } from "../messages/ChatterButton";
import { Facts, type Fact } from "../shared/Facts";
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

  const { load, setLoad, reload } = useRecord<TaskDetail>(`/tasks/${encodeURIComponent(id)}`);

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
    <SafeAreaView style={shared.page}>
      <LoadNotice load={load} gone={t("task.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={shared.pageContent}>
          <Details task={load.value} />
          <ActionProblem
            problem={problem?.load ?? null}
            gone={t("task.gone")}
            onRetry={() => problem && act(problem.action)}
          />
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
          <ChatterButton document={{ model: "medilab.task", id: load.value.id, code: load.value.name }} />
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ task }: Readonly<{ task: TaskDetail }>) {
  const t = useT();
  const { language } = useSession();
  const facts: Fact[] = [
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
      <Facts facts={facts} />
      {task.document?.model === SAMPLE_TEST_MODEL && <BenchTest id={task.document.id} />}
      {!!task.note && <Text style={shared.text}>{task.note}</Text>}
      {task.steps.length > 0 && (
        <View style={shared.section}>
          <Text accessibilityRole="header" style={shared.heading}>
            {t("task.steps")}
          </Text>
          {task.steps.map((step, index) => (
            <View key={`${index}-${step.instruction}`} style={styles.step}>
              <Text style={shared.label}>
                {t("task.step", { number: index + 1, minutes: step.minutes })}
              </Text>
              <Text style={shared.text}>{step.instruction}</Text>
              {!!step.note && <Text style={shared.detail}>{step.note}</Text>}
              {!!step.location && <Text style={shared.detail}>{t("task.stepLocation", { location: step.location })}</Text>}
            </View>
          ))}
        </View>
      )}
    </>
  );
}

/** The sample test a testing task opens: its lab code, parameter, way of testing and due date, and the way to enter or
 * open its result. */
function BenchTest({ id }: Readonly<{ id: number }>) {
  const t = useT();
  const { load } = useRecord<SampleTest>(`/sample-tests/${id}`);
  if (load.state !== "ready") {
    return null;
  }
  const test = load.value;
  return (
    <View style={shared.section}>
      <TestFacts test={test} />
      {test.can_enter_result && (
        <Button label={t("test.enterResult")} onPress={() => router.push(sampleTestPath(id))} primary />
      )}
      {!test.can_enter_result && test.result && (
        <Button label={t("test.openResult")} onPress={() => test.result && router.push(resultPath(test.result.id))} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  step: { borderLeftWidth: 3, borderLeftColor: colors.border, paddingLeft: 12, gap: 2 },
});
