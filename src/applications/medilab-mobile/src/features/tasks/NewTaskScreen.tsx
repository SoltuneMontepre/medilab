import { randomUUID } from "expo-crypto";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { TaskDetail } from "../../api";
import type { MessageKey } from "../../i18n";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { taskPath } from "../documents/documentPath";
import { ActionBar } from "../shared/ActionBar";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";
import { AssigneePicker, type Assignee } from "./AssigneePicker";
import { deadlineIn, defaultDeadline, parseDeadline, quickDays } from "./deadline";

const QUICK_LABELS: Record<number, MessageKey> = {
  0: "newTask.today",
  1: "newTask.tomorrow",
  3: "newTask.inThreeDays",
};

/** Creates a task by hand with a name, a note, an assignee and a deadline, as a person with the task permissions does
 * on the web. The task opens no document. Sending it again after a lost answer creates it once. */
export function NewTaskScreen() {
  const t = useT();
  const { call } = useSession();
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [deadline, setDeadline] = useState(defaultDeadline);
  const [assignee, setAssignee] = useState<Assignee | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [problem, setProblem] = useState<Load<never> | null>(null);
  const [busy, setBusy] = useState(false);
  // One key per task the person creates, so a request sent again creates nothing more.
  const [requestKey] = useState(randomUUID);

  async function create() {
    setProblem(null);
    const moment = parseDeadline(deadline);
    if (!name.trim() || !assignee) {
      setInvalid(t("newTask.missing"));
      return;
    }
    if (!moment) {
      setInvalid(t("newTask.invalidDeadline"));
      return;
    }
    setInvalid(null);
    setBusy(true);
    try {
      const task = await call<TaskDetail>("/tasks", {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: {
          name: name.trim(),
          ...(note.trim() ? { note: note.trim() } : {}),
          assignee_id: assignee.id,
          deadline: moment.toISOString(),
        },
      });
      if (task) {
        router.replace(taskPath(task.id));
      }
    } catch (error) {
      setProblem(failed(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen
      title={t("newTask.title")}
      footer={
        <ActionBar
          actions={[
            {
              key: "create",
              label: t("newTask.submit"),
              tone: "primary",
              icon: "plus",
              disabled: busy,
              testID: "new-task-create",
              onPress: create,
            },
          ]}
        >
          {invalid && (
            <Text accessibilityRole="alert" style={shared.error}>
              {invalid}
            </Text>
          )}
          <ActionProblem problem={problem} gone="" onRetry={create} />
        </ActionBar>
      }
    >
      <Sheet>
        <View style={styles.field}>
          <Text style={shared.label}>{t("newTask.name")}</Text>
          <TextInput accessibilityLabel={t("newTask.name")} style={shared.input} value={name} onChangeText={setName} />
        </View>
        <View style={styles.field}>
          <Text style={shared.label}>{t("newTask.note")}</Text>
          <TextInput
            accessibilityLabel={t("newTask.note")}
            style={[shared.input, shared.multiline]}
            value={note}
            onChangeText={setNote}
            multiline
          />
        </View>
        <View style={styles.field}>
          <Text style={shared.label}>{t("newTask.deadline")}</Text>
          <View style={styles.picks}>
            {quickDays().map((days) => {
              const value = deadlineIn(days);
              const chosen = value === deadline;
              return (
                <Pressable
                  key={days}
                  accessibilityRole="radio"
                  accessibilityState={{ checked: chosen }}
                  testID={`deadline-${days}`}
                  hitSlop={6}
                  style={[styles.pick, chosen && styles.picked]}
                  onPress={() => setDeadline(value)}
                >
                  <Text style={[styles.pickText, chosen && styles.pickedText]}>{t(QUICK_LABELS[days])}</Text>
                </Pressable>
              );
            })}
          </View>
          <TextInput
            accessibilityLabel={t("newTask.deadline")}
            style={shared.input}
            value={deadline}
            onChangeText={setDeadline}
            autoCapitalize="none"
          />
          <Text style={shared.detail}>{t("newTask.deadlineHint")}</Text>
        </View>
      </Sheet>
      <Sheet>
        <AssigneePicker chosen={assignee} onChoose={setAssignee} departments={false} />
      </Sheet>
    </Screen>
  );
}

const styles = StyleSheet.create({
  field: { gap: 6 },
  picks: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginBottom: space.xs },
  pick: {
    minHeight: 36,
    justifyContent: "center",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    paddingHorizontal: space.md,
  },
  picked: { backgroundColor: colors.primary, borderColor: colors.primary },
  pickText: { fontSize: fontSize.base, color: colors.textSecondary },
  pickedText: { color: colors.textOnPrimary, fontWeight: "600" },
});
