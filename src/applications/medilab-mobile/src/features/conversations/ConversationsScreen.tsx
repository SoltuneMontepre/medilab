import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import { AppState, Pressable, ScrollView, Text } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Conversation } from "../../api";
import { useT } from "../../locale";
import { useRecord } from "../../record";
import { watchMessagePushes } from "../../push";
import { styles as shared } from "../../styles";
import { LoadNotice } from "../connection/LoadNotice";
import { conversationPath } from "../documents/documentPath";
import { Button } from "../shared/Button";

/** The person's direct and group conversations, as Discuss on the web has them, with their unread messages: read
 * again on a message push, when the app comes back to the foreground and when the person returns to the list. */
export function ConversationsScreen() {
  const t = useT();
  const { load, reload } = useRecord<{ conversations: Conversation[] }>("/conversations");
  const refresh = useCallback(() => void reload(), [reload]);

  useEffect(() => watchMessagePushes(refresh), [refresh]);
  useEffect(() => {
    const listening = AppState.addEventListener("change", (state) => state === "active" && refresh());
    return () => listening.remove();
  }, [refresh]);

  return (
    <SafeAreaView style={shared.page}>
      <ScrollView contentContainerStyle={shared.pageContent}>
        <Text style={shared.title}>{t("conversations.title")}</Text>
        <Button
          testID="conversations-new"
          primary
          label={t("conversations.new")}
          onPress={() => router.push("/conversations/new")}
        />
        <LoadNotice load={load} gone={t("conversations.empty")} onRetry={reload} />
        {load.state === "ready" && !load.value.conversations.length && (
          <Text style={shared.detail}>{t("conversations.empty")}</Text>
        )}
        {load.state === "ready" &&
          load.value.conversations.map((conversation) => <Row key={conversation.id} conversation={conversation} />)}
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ conversation }: Readonly<{ conversation: Conversation }>) {
  const t = useT();
  const unread = conversation.unread ? t("conversations.unread", { count: conversation.unread }) : null;
  const muted = conversation.muted ? t("conversations.muted") : null;
  return (
    <Pressable
      testID={`conversation-${conversation.id}`}
      accessibilityRole="button"
      accessibilityLabel={[conversation.name, unread, muted].filter(Boolean).join(", ")}
      style={shared.card}
      onPress={() => router.push(conversationPath(conversation.id))}
    >
      <Text style={[shared.label, !!unread && { fontWeight: "700" }]}>{conversation.name}</Text>
      {!!conversation.last_message && (
        <Text style={shared.detail} numberOfLines={1}>
          {conversation.last_message.mine ? t("messages.you") : conversation.last_message.author}:{" "}
          {conversation.last_message.text || conversation.last_message.attachments.map((file) => file.name).join(", ")}
        </Text>
      )}
      {[unread, muted].filter(Boolean).map((tag) => (
        <Text key={tag} style={shared.detail}>
          {tag}
        </Text>
      ))}
    </Pressable>
  );
}
