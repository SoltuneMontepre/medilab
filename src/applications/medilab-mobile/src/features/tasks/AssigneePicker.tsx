import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Assignees } from "../../api";
import { failed, type Load } from "../../load";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { Unreachable } from "../connection/Unreachable";

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
      {chosen && <Text style={styles.chosen}>{t("assignee.chosen", { name: chosen.name })}</Text>}
      <TextInput
        accessibilityLabel={t("assignee.search")}
        placeholder={t("assignee.search")}
        style={shared.input}
        value={query}
        onChangeText={setQuery}
        onSubmitEditing={search}
        returnKeyType="search"
      />
      <Pressable accessibilityRole="button" style={shared.secondaryButton} onPress={search}>
        <Text style={shared.secondaryButtonText}>{t("assignee.find")}</Text>
      </Pressable>
      {found?.state === "loading" && <Text style={shared.detail}>{t("loading")}</Text>}
      {found?.state === "unreachable" && <Unreachable onRetry={search} />}
      {found?.state === "refused" && <Text style={shared.error}>{found.message}</Text>}
      {found?.state === "ready" && options.length === 0 && <Text style={shared.detail}>{t("assignee.none")}</Text>}
      {options.map((option) => (
        <Pressable
          key={`${option.kind}-${option.id}`}
          accessibilityRole="radio"
          accessibilityLabel={option.name}
          accessibilityState={{ checked: chosen?.kind === option.kind && chosen.id === option.id }}
          style={styles.option}
          onPress={() => onChoose(option)}
        >
          <Text style={shared.label}>{option.name}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  box: { gap: 8 },
  chosen: { fontSize: 15, fontWeight: "600", color: colors.primary },
  option: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10 },
});
