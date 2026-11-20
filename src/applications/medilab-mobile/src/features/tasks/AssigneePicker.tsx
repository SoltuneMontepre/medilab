import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Assignees } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, layout, radius, space } from "../../theme";
import { Unreachable } from "../connection/Unreachable";
import { Avatar } from "../shared/Avatar";
import { Button } from "../shared/Button";
import { Icon } from "../shared/Icon";

/** Whom a task goes to: a person, or a department's queue. */
export type Assignee = { kind: "person" | "department"; id: number; name: string };

/** Finds the people, and the departments when they may be chosen, whom the person may give a task to. */
export function AssigneePicker({
  chosen,
  onChoose,
  departments,
}: Readonly<{ chosen: Assignee | null; onChoose: (assignee: Assignee) => void; departments: boolean }>) {
  const t = useT();
  const { call } = useSession();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Load<Assignees> | null>(null);

  async function search() {
    setFound({ state: "loading" });
    try {
      const answer = await call<Assignees>(`/tasks/assignees?q=${encodeURIComponent(query.trim())}`);
      setFound({ state: "ready", value: answer ?? { people: [], departments: [] } });
    } catch (error) {
      setFound(failed(error));
    }
  }

  const options: Assignee[] =
    found?.state === "ready"
      ? [
          ...found.value.people.map((person) => ({
            kind: "person" as const,
            id: person.id,
            name: person.department ? `${person.name} (${person.department})` : person.name,
          })),
          ...(departments
            ? found.value.departments.map((department) => ({
                kind: "department" as const,
                id: department.id,
                name: t("assignee.queueOf", { department: department.name }),
              }))
            : []),
        ]
      : [];
  return (
    <View style={styles.box}>
      <Text style={shared.label}>{t("assignee.label")}</Text>
      {chosen && (
        <View style={styles.chosenBox}>
          <Icon name="check-circle" color={colors.primary} />
          <Text style={styles.chosen}>{t("assignee.chosen", { name: chosen.name })}</Text>
        </View>
      )}
      <View style={styles.search}>
        <TextInput
          accessibilityLabel={t("assignee.search")}
          placeholder={t("assignee.search")}
          placeholderTextColor={colors.textMuted}
          style={[shared.input, styles.query]}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={search}
          returnKeyType="search"
        />
        <Button label={t("assignee.find")} icon="magnify" onPress={search} />
      </View>
      {found?.state === "loading" && <Text style={shared.detail}>{t("loading")}</Text>}
      {found?.state === "unreachable" && <Unreachable onRetry={search} />}
      {found?.state === "refused" && <Text style={shared.error}>{found.message}</Text>}
      {found?.state === "ready" && options.length === 0 && <Text style={shared.detail}>{t("assignee.none")}</Text>}
      {options.map((option) => {
        const picked = chosen?.kind === option.kind && chosen.id === option.id;
        return (
          <Pressable
            key={`${option.kind}-${option.id}`}
            accessibilityRole="radio"
            accessibilityLabel={option.name}
            accessibilityState={{ checked: picked }}
            style={[styles.option, picked && styles.picked]}
            onPress={() => onChoose(option)}
          >
            {option.kind === "person" ? (
              <Avatar name={option.name} size={32} />
            ) : (
              <View style={styles.queue}>
                <Icon name="account-group-outline" size={18} color={colors.primary} />
              </View>
            )}
            <Text style={[shared.label, styles.optionName]}>{option.name}</Text>
            <Icon
              name={picked ? "radiobox-marked" : "radiobox-blank"}
              color={picked ? colors.primary : colors.borderControl}
            />
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: space.sm },
  chosenBox: { flexDirection: "row", alignItems: "center", gap: space.sm },
  chosen: { flex: 1, fontSize: 15, fontWeight: "600", color: colors.primary },
  search: { flexDirection: "row", gap: space.sm },
  query: { flex: 1 },
  option: {
    minHeight: layout.touch,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  picked: { borderColor: colors.primary, backgroundColor: colors.primaryLight },
  optionName: { flex: 1 },
  queue: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    backgroundColor: colors.primaryLight,
    alignItems: "center",
    justifyContent: "center",
  },
});
