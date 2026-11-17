import { randomUUID } from "expo-crypto";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Conversation, PersonName } from "../../api";
import { useT } from "../../locale";
import { useAction } from "../../record";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";
import { ActionProblem } from "../connection/ActionProblem";
import { conversationPath } from "../documents/documentPath";
import { usePeople } from "../messages/usePeople";
import { Button } from "../shared/Button";

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
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent}>
        <Text style={shared.title}>{t("conversations.new")}</Text>
        <TextInput
          testID="people-search"
          accessibilityLabel={t("conversations.findPeople")}
          placeholder={t("conversations.findPeople")}
          style={shared.input}
          value={query}
          onChangeText={setQuery}
        />
        {found.map((person) => {
          const picked = chosen.some((kept) => kept.id === person.id);
          return (
            <Pressable
              key={person.id}
              testID={`person-${person.id}`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: picked }}
              accessibilityLabel={person.name}
              style={[shared.card, picked && { borderColor: colors.primary }]}
              onPress={() => toggle(person)}
            >
              <Text style={shared.label}>{person.name}</Text>
            </Pressable>
          );
        })}
        {group && (
          <TextInput
            testID="group-name"
            accessibilityLabel={t("conversations.groupName")}
            placeholder={t("conversations.groupName")}
            style={shared.input}
            value={name}
            onChangeText={setName}
          />
        )}
        <ActionProblem problem={problem?.load ?? null} gone="" onRetry={problem?.retry ?? (() => undefined)} />
        <Button
          testID="conversation-start"
          primary
          label={t(group ? "conversations.createGroup" : "conversations.openDirect")}
          disabled={!chosen.length || busy}
          onPress={start}
        />
      </ScrollView>
    </SafeAreaView>
  );
}
