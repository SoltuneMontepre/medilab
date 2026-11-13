import { useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, type Sample, type Task } from "../../api";
import { useReloadOnReturn } from "../../focus";
import type { MessageKey } from "../../i18n";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { LoadNotice } from "../connection/LoadNotice";
import { Unreachable } from "../connection/Unreachable";
import { formatMoment } from "../tasks/taskText";

type Action = "receive" | "claim";

/** A sample as the person may see it: recording its receipt by their department, when it was handed over to them,
 * and claiming the unassigned testing tasks of their department on it. */
export function SampleScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [chosen, setChosen] = useState<number[]>([]);
  const [problem, setProblem] = useState<{ action: Action; load: Load<never> } | null>(null);
  const [claimed, setClaimed] = useState(0);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async () => {
    const sample = await call<Sample>(`/samples/${encodeURIComponent(id)}`);
    if (!sample) {
      throw new ApiError("not_found", "", 404);
    }
    return sample;
  }, [call, id]);
  const { load, setLoad, reload } = useLoad(read);
  useReloadOnReturn(reload);

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

  return (
    <SafeAreaView style={styles.screen}>
      <LoadNotice load={load} gone={t("sample.gone")} onRetry={reload} />
      {load.state === "ready" && (
        <ScrollView contentContainerStyle={styles.content}>
          <Details sample={load.value} />
          <Handover sample={load.value} busy={busy} onReceive={() => act("receive", load.value)} />
          <View style={styles.section}>
            <Text accessibilityRole="header" style={styles.heading}>
              {t("sample.tasks")}
            </Text>
            {!load.value.tasks.length && <Text style={shared.detail}>{t("sample.noTasks")}</Text>}
            {load.value.tasks.map((task) => (
              <ClaimableTask key={task.id} task={task} chosen={chosen.includes(task.id)} onToggle={() => toggle(task)} />
            ))}
            {load.value.tasks.length > 0 && (
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ disabled: busy || !picked.length }}
                disabled={busy || !picked.length}
                style={[shared.primaryButton, !picked.length && styles.disabled]}
                onPress={() => act("claim", load.value)}
              >
                <Text style={shared.primaryButtonText}>{t("sample.claim", { count: picked.length })}</Text>
              </Pressable>
            )}
            {claimed > 0 && <Text style={shared.label}>{t("sample.claimed", { count: claimed })}</Text>}
          </View>
          {problem?.load.state === "unreachable" && <Unreachable onRetry={() => act(problem.action, load.value)} />}
          {(problem?.load.state === "refused" || problem?.load.state === "gone") && (
            <Text accessibilityRole="alert" style={shared.error}>
              {problem.load.state === "refused" ? problem.load.message : t("sample.gone")}
            </Text>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Details({ sample }: Readonly<{ sample: Sample }>) {
  const t = useT();
  const { language } = useSession();
  const facts: [MessageKey, string | null][] = [
    ["sample.status", sample.status],
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
      <Text style={shared.title}>{sample.code}</Text>
      {facts
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <View key={label} style={styles.fact}>
            <Text style={shared.detail}>{t(label)}</Text>
            <Text style={shared.label}>{value}</Text>
          </View>
        ))}
      {!!sample.note && <Text style={styles.note}>{sample.note}</Text>}
    </>
  );
}

function Handover({ sample, busy, onReceive }: Readonly<{ sample: Sample; busy: boolean; onReceive: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const { handover } = sample;
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={styles.heading}>
        {t("sample.handover")}
      </Text>
      {!handover && <Text style={shared.detail}>{t("sample.notHandedOver")}</Text>}
      {handover?.received_at && (
        <Text style={shared.label}>
          {t("sample.received", {
            department: handover.department,
            date: formatMoment(handover.received_at, language),
            name: handover.received_by,
          })}
        </Text>
      )}
      {handover && !handover.received_at && (
        <Text style={shared.detail}>{t("sample.notReceived", { department: handover.department })}</Text>
      )}
      {handover?.can_receive && (
        <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
            disabled={busy}
            style={shared.primaryButton}
            onPress={onReceive}
          >
          <Text style={shared.primaryButtonText}>{t("sample.receive")}</Text>
        </Pressable>
      )}
    </View>
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
      onPress={onToggle}
    >
      <Text style={shared.label}>{task.name}</Text>
      {!!due && <Text style={shared.detail}>{due}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24 },
  content: { gap: 12, paddingBottom: 24 },
  fact: { gap: 2 },
  note: { fontSize: 15, color: colors.text },
  section: { gap: 8 },
  heading: { fontSize: 18, fontWeight: "600", color: colors.text },
  task: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12, gap: 4 },
  chosen: { borderColor: colors.primary, borderWidth: 2 },
  disabled: { opacity: 0.5 },
});
