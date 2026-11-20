import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Sample, Task } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, layout, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { ChatterLink } from "../messages/ChatterLink";
import { SamplePhotos } from "../photos/SamplePhotos";
import { Button } from "../shared/Button";
import { Facts, type Fact } from "../shared/Facts";
import { Icon } from "../shared/Icon";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { formatMoment } from "../tasks/taskText";

type Action = "receive" | "claim";

/** A sample as the person may see it: recording its receipt by their department, when it was handed over to them,
 * its photos, and claiming the unassigned testing tasks of their department on it. Only a person who tests samples
 * sees their department's handover and tasks, or the handover when the sample was handed over to them. */
export function SampleScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [chosen, setChosen] = useState<number[]>([]);
  const [problem, setProblem] = useState<{ action: Action; load: Load<never> } | null>(null);
  const [claimed, setClaimed] = useState(0);
  const [busy, setBusy] = useState(false);

  const { load, setLoad, reload } = useRecord<Sample>(`/samples/${encodeURIComponent(id)}`);

  // The chosen tasks the sample still offers: one claimed by someone else meanwhile is gone once the sample is read again.
  const picked = load.state === "ready" ? chosen.filter((taskId) => load.value.tasks.some((task) => task.id === taskId)) : [];

  async function act(action: Action, sample: Sample) {
    setProblem(null);
    setClaimed(0);
    setBusy(true);
    try {
      const changed =
        action === "receive"
          ? await call<Sample>("/samples/receive", { method: "POST", body: { code: sample.code } })
          : await call<Sample>(`/samples/${sample.id}/claim`, { method: "POST", body: { task_ids: picked } });
      if (changed) {
        setLoad({ state: "ready", value: changed });
      }
      if (action === "claim") {
        setClaimed(picked.length);
        setChosen([]);
      }
    } catch (error) {
      setProblem({ action, load: failed(error) });
    } finally {
      setBusy(false);
    }
  }

  function toggle(task: Task) {
    setChosen((now) => (now.includes(task.id) ? now.filter((taskId) => taskId !== task.id) : [...now, task.id]));
  }

  const sample = load.state === "ready" ? load.value : null;
  return (
    <Screen title={sample?.code ?? t("scan.title")}>
      <LoadNotice load={load} gone={t("sample.gone")} onRetry={reload} />
      {sample && (
        <>
          <Details sample={sample} />
          <ActionProblem
            problem={problem?.load ?? null}
            gone={t("sample.gone")}
            onRetry={() => problem && act(problem.action, sample)}
          />
          {(sample.tests_samples || sample.handover) && (
            <Handover sample={sample} busy={busy} onReceive={() => act("receive", sample)} />
          )}
          {sample.tests_samples && (
            <Sheet title={t("sample.tasks")}>
              {!sample.tasks.length && <Text style={shared.detail}>{t("sample.noTasks")}</Text>}
              {sample.tasks.map((task) => (
                <ClaimableTask key={task.id} task={task} chosen={chosen.includes(task.id)} onToggle={() => toggle(task)} />
              ))}
              {sample.tasks.length > 0 && (
                <Button
                  label={t("sample.claim", { count: picked.length })}
                  icon="hand-back-right-outline"
                  tone="primary"
                  disabled={busy || !picked.length}
                  testID="sample-claim"
                  onPress={() => act("claim", sample)}
                />
              )}
              {claimed > 0 && (
                <Text accessibilityRole="alert" style={[shared.label, styles.done]}>
                  {t("sample.claimed", { count: claimed })}
                </Text>
              )}
            </Sheet>
          )}
          {sample.can_add_photos && <SamplePhotos sample={sample} />}
          <Sheet>
            <ChatterLink document={{ model: "medilab.sample", id: sample.id, code: sample.code }} />
          </Sheet>
        </>
      )}
    </Screen>
  );
}

function Details({ sample }: Readonly<{ sample: Sample }>) {
  const t = useT();
  const { language } = useSession();
  const facts: Fact[] = [
    ["sample.customer", sample.customer],
    ["sample.customerName", sample.customer_sample_name],
    ["sample.type", sample.sample_type],
    ["sample.physicalState", sample.physical_state],
    ["sample.form", sample.form],
    ["sample.container", sample.container],
    ["sample.receivedAt", sample.received_at ? formatMoment(sample.received_at, language) : ""],
    ["sample.storageLocation", sample.storage_location],
    ["sample.samplingLocation", sample.sampling_location],
  ];
  return (
    <>
      <RecordHead title={sample.code} status={sample.status ? { label: sample.status, tone: "info" } : undefined} />
      <Sheet title={t("task.info")}>
        <Facts facts={facts} />
        {!!sample.note && <Text style={shared.text}>{sample.note}</Text>}
      </Sheet>
    </>
  );
}

function Handover({ sample, busy, onReceive }: Readonly<{ sample: Sample; busy: boolean; onReceive: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const { handover } = sample;
  return (
    <Sheet title={t("sample.handover")}>
      {!handover && <Text style={shared.detail}>{t("sample.notHandedOver")}</Text>}
      {handover?.received_at && (
        <View style={styles.received}>
          <Icon name="check-circle" color={colors.success} />
          <Text style={[shared.label, styles.receivedText]}>
            {t("sample.received", {
              department: handover.department,
              date: formatMoment(handover.received_at, language),
              name: handover.received_by,
            })}
          </Text>
        </View>
      )}
      {handover && !handover.received_at && (
        <Text style={shared.detail}>{t("sample.notReceived", { department: handover.department })}</Text>
      )}
      {handover?.can_receive && (
        <Button label={t("sample.receive")} icon="inbox-arrow-down" tone="success" disabled={busy} onPress={onReceive} />
      )}
    </Sheet>
  );
}

function ClaimableTask({ task, chosen, onToggle }: Readonly<{ task: Task; chosen: boolean; onToggle: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const due = task.deadline ? t("task.deadline", { date: formatMoment(task.deadline, language) }) : "";
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: chosen }}
      accessibilityLabel={[task.name, due].filter(Boolean).join(", ")}
      style={[styles.task, chosen && styles.chosen]}
      testID="claimable-task"
      onPress={onToggle}
    >
      <Icon
        name={chosen ? "checkbox-marked" : "checkbox-blank-outline"}
        size={24}
        color={chosen ? colors.primary : colors.borderControl}
      />
      <View style={styles.taskText}>
        <Text style={shared.label}>{task.name}</Text>
        {!!due && <Text style={shared.detail}>{due}</Text>}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  received: { flexDirection: "row", gap: space.sm, alignItems: "flex-start" },
  receivedText: { flex: 1 },
  done: { color: colors.success },
  task: {
    minHeight: layout.touch,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: space.md,
  },
  chosen: { borderColor: colors.primary, backgroundColor: colors.primaryLight },
  taskText: { flex: 1, gap: 2 },
});
