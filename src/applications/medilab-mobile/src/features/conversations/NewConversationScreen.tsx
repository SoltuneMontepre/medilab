import { randomUUID } from "expo-crypto";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Conversation, PersonName } from "../../api";
import { useT } from "../../locale";
import { useAction } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, layout, radius, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { conversationPath } from "../documents/documentPath";
import { usePeople } from "../messages/usePeople";
import { ActionBar } from "../shared/ActionBar";
import { Avatar } from "../shared/Avatar";
import { Icon } from "../shared/Icon";
import { Screen } from "../shared/Screen";
import { Sheet } from "../shared/Sheet";

/** Starts a conversation: with one person it opens their direct conversation, the same as on the web; with several,
 * it creates a group with its name. */
export function NewConversationScreen() {
  const t = useT();
  const { call } = useSession();
  const findPeople = usePeople();
  const { problem, busy, run } = useAction();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<PersonName[]>([]);
  const [chosen, setChosen] = useState<PersonName[]>([]);
  const [name, setName] = useState("");
  // One key per group the person creates, so a request sent again creates nothing more.
  const [requestKey] = useState(randomUUID);

  useEffect(() => {
    let current = true;
    findPeople(query)
      .then((people) => current && setFound(people))
      .catch(() => current && setFound([]));
    return () => {
      current = false;
    };
  }, [query, findPeople]);

  function toggle(person: PersonName) {
    setChosen((people) =>
      people.some((kept) => kept.id === person.id)
        ? people.filter((kept) => kept.id !== person.id)
        : [...people, person],
    );
  }

  const group = chosen.length > 1;

  function start() {
    void run(async () => {
      const body = group
        ? { name: name.trim(), member_ids: chosen.map((person) => person.id) }
        : { person_id: chosen[0].id };
      const conversation = await call<Conversation>("/conversations", {
        method: "POST",
        headers: group ? { "Idempotency-Key": requestKey } : {},
        body,
      });
      if (conversation) {
        router.replace(conversationPath(conversation.id));
      }
    });
  }

  return (
    <Screen
      title={t("conversations.new")}
      footer={
        <ActionBar
          actions={[
            {
              key: "start",
              label: t(group ? "conversations.createGroup" : "conversations.openDirect"),
              tone: "primary",
              icon: group ? "account-multiple-plus-outline" : "message-outline",
              disabled: !chosen.length || busy,
              testID: "conversation-start",
              onPress: start,
            },
          ]}
        >
          <ActionProblem problem={problem?.load ?? null} gone="" onRetry={problem?.retry ?? (() => undefined)} />
        </ActionBar>
      }
    >
      <View style={styles.search}>
        <Icon name="magnify" />
        <TextInput
          testID="people-search"
          accessibilityLabel={t("conversations.findPeople")}
          placeholder={t("conversations.findPeople")}
          placeholderTextColor={colors.textMuted}
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
        />
      </View>
      {group && (
        <Sheet>
          <View style={styles.field}>
            <Text style={shared.label}>{t("conversations.groupName")}</Text>
            <TextInput
              testID="group-name"
              accessibilityLabel={t("conversations.groupName")}
              placeholder={t("conversations.groupName")}
              placeholderTextColor={colors.textMuted}
              style={shared.input}
              value={name}
              onChangeText={setName}
            />
          </View>
        </Sheet>
      )}
      {found.length > 0 && (
        <Sheet>
          {found.map((person) => {
            const picked = chosen.some((kept) => kept.id === person.id);
            return (
              <Pressable
                key={person.id}
                testID={`person-${person.id}`}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: picked }}
                accessibilityLabel={person.name}
                style={({ pressed }) => [styles.person, pressed && styles.pressed]}
                onPress={() => toggle(person)}
              >
                <Avatar name={person.name} size={36} />
                <Text style={[shared.label, styles.name]}>{person.name}</Text>
                <Icon
                  name={picked ? "checkbox-marked" : "checkbox-blank-outline"}
                  size={24}
                  color={picked ? colors.primary : colors.borderControl}
                />
              </Pressable>
            );
          })}
        </Sheet>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  search: {
    minHeight: layout.touch,
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    borderWidth: 1,
    borderColor: colors.borderControl,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    paddingHorizontal: space.lg,
  },
  searchInput: { flex: 1, fontSize: 16, color: colors.text, paddingVertical: 10 },
  field: { gap: 6 },
  person: { minHeight: layout.touch, flexDirection: "row", alignItems: "center", gap: space.md },
  pressed: { opacity: 0.6 },
  name: { flex: 1 },
});
