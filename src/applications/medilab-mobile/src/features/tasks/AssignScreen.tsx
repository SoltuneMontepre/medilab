import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { ApiError, type TaskDetail } from "../../api";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { AssigneePicker, type Assignee } from "./AssigneePicker";

/** Assigns a task to a person or a department's queue, as the web's Assign does: moving it away from its person or
 * department needs a reason, which MediLab refuses to do without. */
export function AssignScreen() {
  const t = useT();
  const { call } = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [chosen, setChosen] = useState<Assignee | null>(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<Load<never> | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async () => {
    const task = await call<TaskDetail>(`/tasks/${encodeURIComponent(id)}`);
    if (!task) {
      throw new ApiError("not_found", "", 404);
    }
    return task;
  }, [call, id]);
  const { load, reload } = useLoad(read);

  async function assign() {
    if (!chosen) {
      return;
    }
    setProblem(null);
    setBusy(true);
    const target =
      chosen.kind === "person" ? { assignee_id: chosen.id } : { department_id: chosen.id, assignee_id: null };
    try {
      await call(`/tasks/${encodeURIComponent(id)}/assign`, {
        method: "POST",
        body: { ...target, ...(reason.trim() ? { reason: reason.trim() } : {}) },
      });
      router.back();
    } catch (error) {
      setProblem(failed(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={shared.title}>{t("assign.title")}</Text>
        {load.state === "loading" && <ActivityIndicator accessibilityLabel={t("loading")} />}
        {load.state === "unreachable" && <Unreachable onRetry={reload} />}
        {load.state === "gone" && <Text style={shared.error}>{t("task.gone")}</Text>}
        {load.state === "refused" && <Text style={shared.error}>{load.message}</Text>}
        {load.state === "ready" && (
          <>
            <Text style={shared.label}>{load.value.name}</Text>
            <Text style={shared.detail}>
              {t("assign.current", { who: load.value.assignee || load.value.department || "-" })}
            </Text>
            <AssigneePicker chosen={chosen} onChoose={setChosen} departments />
            <TextInput
              accessibilityLabel={t("assign.reason")}
              placeholder={t("assign.reason")}
              style={[shared.input, styles.reason]}
              value={reason}
              onChangeText={setReason}
              multiline
            />
            <Text style={shared.detail}>{t("assign.reasonHint")}</Text>
            {problem?.state === "unreachable" && <Unreachable onRetry={assign} />}
            {problem?.state === "refused" && (
              <Text accessibilityRole="alert" style={shared.error}>
                {problem.message}
              </Text>
            )}
            {problem?.state === "gone" && <Text style={shared.error}>{t("task.gone")}</Text>}
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: !chosen || busy }}
              disabled={!chosen || busy}
              style={shared.primaryButton}
              onPress={assign}
            >
              <Text style={shared.primaryButtonText}>{t("assign.submit")}</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 24, gap: 12 },
  reason: { minHeight: 72, textAlignVertical: "top" },
});
