import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Task } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, space } from "../../theme";
import { Badge } from "../shared/Badge";
import { Icon, type IconName } from "../shared/Icon";
import { isOverdue, statusKey, statusTone, taskLabel, whenText } from "./taskText";

/** A task in a list, as a card of the web's kanban: its name and status, then its document's code, its deadline, or
 * when it was done, and its place. */
export function TaskRow({ task, onPress }: Readonly<{ task: Task; onPress: () => void }>) {
  const t = useT();
  const { language } = useSession();
  const when = whenText(task, t, language);
  const overdue = isOverdue(task);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={taskLabel(task, t, language)}
      style={({ pressed }) => [shared.card, styles.card, pressed && styles.pressed]}
      testID="task-row"
      onPress={onPress}
    >
      <View style={styles.head}>
        <Text style={[shared.label, styles.name]} numberOfLines={2}>
          {task.name}
        </Text>
        <Badge label={t(statusKey(task.status))} tone={statusTone(task.status)} />
      </View>
      <View style={styles.facts}>
        {!!task.document?.code && <Fact icon="pound" text={task.document.code} />}
        {!!when && <Fact icon={overdue ? "clock-alert-outline" : "clock-outline"} text={when} alert={overdue} />}
        {!!task.location && <Fact icon="map-marker-outline" text={task.location} />}
      </View>
    </Pressable>
  );
}

/** A fact of a task beside its icon; an overdue deadline is red and bold. */
export function Fact({ icon, text, alert = false }: Readonly<{ icon: IconName; text: string; alert?: boolean }>) {
  return (
    <View style={styles.fact}>
      <Icon name={icon} size={15} color={alert ? colors.danger : colors.textMuted} />
      <Text style={[shared.detail, alert && styles.overdue]} numberOfLines={1}>
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.sm },
  pressed: { backgroundColor: colors.primaryLight },
  head: { flexDirection: "row", alignItems: "flex-start", gap: space.sm },
  name: { flex: 1 },
  facts: { flexDirection: "row", flexWrap: "wrap", columnGap: space.md, rowGap: space.xs },
  fact: { flexDirection: "row", alignItems: "center", gap: space.xs, maxWidth: "100%" },
  overdue: { color: colors.danger, fontWeight: "600" },
});
