import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import type { SampleTest, TaskDetail } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { TestFacts } from "../bench/TestFacts";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { documentPath, resultPath, SAMPLE_TEST_MODEL, samplePath, sampleTestPath } from "../documents/documentPath";
import { ChatterLink } from "../messages/ChatterLink";
import type { MessageKey } from "../../i18n";
import { ActionBar, type BarAction } from "../shared/ActionBar";
import { Button, type Tone } from "../shared/Button";
import type { IconName } from "../shared/Icon";
import { Facts, type Fact as FactRow } from "../shared/Facts";
import { LinkRow } from "../shared/LinkRow";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact } from "./TaskRow";
import { formatMoment, isOverdue, statusKey, statusTone, whenText } from "./taskText";

type Action = "claim" | "start" | "done";

// Claiming and starting move the task forward; marking it done finishes it.
const ACTIONS: { action: Action; label: MessageKey; tone: Tone; icon: IconName }[] = [
  { action: "claim", label: "task.claim", tone: "primary", icon: "hand-back-right-outline" },
  { action: "start", label: "task.start", tone: "primary", icon: "play" },
  { action: "done", label: "task.done", tone: "success", icon: "check" },
];

/** A task as the person may read it, with the actions the web's form shows them: claiming it from their queue,
 * starting it, marking a task created by hand done, assigning it, and opening its document at the action to take or
 * the samples a collection task is for. */
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

  const task = load.state === "ready" ? load.value : null;
  const actions: BarAction[] = ACTIONS.filter(({ action }) => task?.actions[action]).map(
    ({ action, label, tone, icon }) => ({
      key: action,
      label: t(label),
      tone,
      icon,
      testID: `task-${action}`,
      disabled: busy,
      onPress: () => act(action),
    }),
  );
  if (task?.actions.assign) {
    actions.push({
      key: "assign",
      label: t("task.assign"),
      icon: "account-arrow-right-outline",
      testID: "task-assign",
      onPress: () => router.push({ pathname: "/tasks/[id]/assign", params: { id } }),
    });
  }

  return (
    <Screen
      title={task?.document?.code || task?.name || t("tasks.title")}
      footer={
        task && (
          <ActionBar actions={actions}>
            <ActionProblem
              problem={problem?.load ?? null}
              gone={t("task.gone")}
              onRetry={() => problem && act(problem.action)}
            />
          </ActionBar>
        )
      }
    >
      <LoadNotice load={load} gone={t("task.gone")} onRetry={reload} />
      {task && <Details task={task} />}
    </Screen>
  );
}

function Details({ task }: Readonly<{ task: TaskDetail }>) {
  const t = useT();
  const { language } = useSession();
  const when = whenText(task, t, language);
  const done = task.status === "done";
  // The head shows the person and when the task is due, or was done; the sheet shows the rest.
  const facts: FactRow[] = [
    ["task.type", task.type],
    ["task.deadlineLabel", done && task.deadline ? formatMoment(task.deadline, language) : ""],
    ["task.planned", task.planned_start ? formatMoment(task.planned_start, language) : ""],
    ["task.plannedEnd", task.planned_end ? formatMoment(task.planned_end, language) : ""],
    ["task.department", task.department],
    ["task.assignedBy", task.assigned_by],
    ["task.location", task.location],
    ["task.reason", task.reassign_reason],
  ];
  const opensDocument = task.document && !(task.samples.length && task.document.screen === "sample");
  return (
    <>
      <RecordHead title={task.name} status={{ label: t(statusKey(task.status)), tone: statusTone(task.status) }}>
        {!!when &&<Fact icon="clock-outline" text={when} alert={isOverdue(task)} />}
        {!!task.assignee && <Fact icon="account-outline" text={task.assignee} />}
      </RecordHead>
      {task.document?.model === SAMPLE_TEST_MODEL && <BenchTest id={task.document.id} />}
      {task.steps.length > 0 && (
        <Sheet title={t("task.steps")}>
          {task.steps.map((step, index) => (
            <View key={`${index}-${step.instruction}`} style={styles.step}>
              <View style={styles.number}>
                <Text style={styles.numberText}>{index + 1}</Text>
              </View>
              <View style={styles.stepText}>
                <Text style={shared.label}>{t("task.step", { number: index + 1, minutes: step.minutes })}</Text>
                <Text style={shared.text}>{step.instruction}</Text>
                {!!step.note && <Text style={shared.detail}>{step.note}</Text>}
                {!!step.location && <Fact icon="map-marker-outline" text={t("task.stepLocation", { location: step.location })} />}
              </View>
            </View>
          ))}
        </Sheet>
      )}
      {task.samples.length > 0 && (
        <Sheet title={t("task.samples")}>
          {task.samples.map((sample) => (
            <LinkRow
              key={sample.id}
              icon="test-tube"
              label={t("task.openDocument", { code: sample.code })}
              detail={sample.sampling_location}
              testID={`collection-sample-${sample.id}`}
              onPress={() => router.push(samplePath(sample.id))}
            />
          ))}
        </Sheet>
      )}
      {!!task.note && (
        <Sheet title={t("newTask.note")}>
          <Text style={shared.text}>{task.note}</Text>
        </Sheet>
      )}
      <Sheet title={t("task.info")}>
        <Facts facts={facts} />
      </Sheet>
      <Sheet>
        {opensDocument && task.document && (
          <LinkRow
            icon="file-document-outline"
            label={t("task.openDocument", { code: task.document.code || task.name })}
            testID="task-open-document"
            onPress={() => task.document && router.push(documentPath(task.document))}
          />
        )}
        <ChatterLink document={{ model: "medilab.task", id: task.id, code: task.name }} />
      </Sheet>
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
    <Sheet title={t("test.title")}>
      <TestFacts test={test} />
      {test.can_enter_result && (
        <Button
          label={t("test.enterResult")}
          icon="pencil-outline"
          tone="primary"
          onPress={() => router.push(sampleTestPath(id))}
          testID="task-enter-result"
        />
      )}
      {!test.can_enter_result && test.result && (
        <LinkRow
          icon="file-document-outline"
          label={t("test.openResult")}
          testID="task-open-result"
          onPress={() => test.result && router.push(resultPath(test.result.id))}
        />
      )}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  step: { flexDirection: "row", gap: space.md },
  number: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: colors.primaryLight,
    alignItems: "center",
    justifyContent: "center",
  },
  numberText: { fontSize: fontSize.sm, fontWeight: "700", color: colors.primary },
  stepText: { flex: 1, gap: 2 },
});
