import { Pressable, StyleSheet, Text } from "react-native";

import type { Task } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { formatMoment, statusKey } from "./taskText";

/** A task in a list: its name, its document's code, its status and its deadline, or when it was done. */
export function TaskRow({ task, onPress }: Readonly<{ task: Task; onPress: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const when = task.status === "done" ? task.done_at : task.deadline;
  const whenKey = task.status === "done" ? "task.doneAt" : "task.deadline";
  const whenText = when ? t(whenKey, { date: formatMoment(when, language) }) : "";
  const overdue = task.status !== "done" && !!task.deadline && new Date(task.deadline) < new Date();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[task.name, task.document?.code, t(statusKey(task.status)), whenText].filter(Boolean).join(", ")}
      style={styles.item}
      onPress={onPress}
    >
      <Text style={shared.label}>{task.name}</Text>
      {!!task.document?.code && <Text style={shared.detail}>{task.document.code}</Text>}
      <Text style={shared.detail}>{t(statusKey(task.status))}</Text>
      {!!whenText && <Text style={[shared.detail, overdue && styles.overdue]}>{whenText}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  item: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12, gap: 4 },
  overdue: { color: colors.error },
});
