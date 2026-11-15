import { randomUUID } from "expo-crypto";
import { router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { TaskDetail } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";
import { taskPath } from "../documents/documentPath";
import { AssigneePicker, type Assignee } from "./AssigneePicker";
import { defaultDeadline, parseDeadline } from "./deadline";

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
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={shared.title}>{t("newTask.title")}</Text>
        <Text style={shared.label}>{t("newTask.name")}</Text>
        <TextInput accessibilityLabel={t("newTask.name")} style={shared.input} value={name} onChangeText={setName} />
        <Text style={shared.label}>{t("newTask.note")}</Text>
        <TextInput
          accessibilityLabel={t("newTask.note")}
          style={[shared.input, styles.note]}
          value={note}
          onChangeText={setNote}
          multiline
        />
        <Text style={shared.label}>{t("newTask.deadline")}</Text>
        <TextInput
          accessibilityLabel={t("newTask.deadline")}
          style={shared.input}
          value={deadline}
          onChangeText={setDeadline}
          autoCapitalize="none"
        />
        <Text style={shared.detail}>{t("newTask.deadlineHint")}</Text>
        <AssigneePicker chosen={assignee} onChoose={setAssignee} departments={false} />
        {invalid && (
          <Text accessibilityRole="alert" style={shared.error}>
            {invalid}
          </Text>
        )}
        {problem?.state === "unreachable" && <Unreachable onRetry={create} />}
        {problem?.state === "refused" && (
          <Text accessibilityRole="alert" style={shared.error}>
            {problem.message}
          </Text>
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: busy }}
          disabled={busy}
          style={shared.primaryButton}
          onPress={create}
        >
          <Text style={shared.primaryButtonText}>{t("newTask.submit")}</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 24, gap: 12 },
  note: { minHeight: 72, textAlignVertical: "top" },
});
