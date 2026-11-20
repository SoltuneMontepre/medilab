import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError, type TaskDetail } from "../../api";
import { failed, useLoad, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { ActionBar } from "../shared/ActionBar";
import { RecordHead } from "../shared/RecordHead";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { Fact } from "./TaskRow";
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

  const task = load.state === "ready" ? load.value : null;
  return (
    <Screen
      title={t("assign.title")}
      footer={
        task && (
          <ActionBar
            actions={[
              {
                key: "assign",
                label: t("assign.submit"),
                tone: "primary",
                icon: "account-arrow-right-outline",
                disabled: !chosen || busy,
                testID: "assign-submit",
                onPress: assign,
              },
            ]}
          >
            <ActionProblem problem={problem} gone={t("task.gone")} onRetry={assign} />
          </ActionBar>
        )
      }
    >
      <LoadNotice load={load} gone={t("task.gone")} onRetry={reload} />
      {task && (
        <>
          <RecordHead title={task.name}>
            <Fact icon="account-outline" text={t("assign.current", { who: task.assignee || task.department || "-" })} />
          </RecordHead>
          <Sheet>
            <AssigneePicker chosen={chosen} onChoose={setChosen} departments />
          </Sheet>
          <Sheet>
            <View style={styles.field}>
              <Text style={shared.label}>{t("assign.reason")}</Text>
              <TextInput
                accessibilityLabel={t("assign.reason")}
                style={[shared.input, shared.multiline]}
                value={reason}
                onChangeText={setReason}
                multiline
              />
              <Text style={shared.detail}>{t("assign.reasonHint")}</Text>
            </View>
          </Sheet>
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  field: { gap: 6 },
});
