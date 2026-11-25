import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import { AppState, Pressable, StyleSheet, Text, View } from "react-native";

import type { Conversation, Message } from "../../api";
import { useBadges } from "../../badges";
import type { Translate } from "../../i18n";
import { useT } from "../../locale";
import { watchMessagePushes } from "../../push";
import { useRecord } from "../../record";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { conversationPath } from "../documents/documentPath";
import { Avatar } from "../shared/Avatar";
import { Icon } from "../shared/Icon";
import { NavButton } from "../shared/Navbar";
import { RecordList } from "../shared/RecordList";
import { Screen } from "../shared/Screen";

/** The person's direct and group conversations, as Discuss on the web has them, with their unread messages: read
 * again on a message push, when the app comes back to the foreground and when the person returns to the list. */
export function ConversationsScreen() {
  const t = useT();
  const { showConversations } = useBadges();
  const { load, reload, refresh } = useRecord<{ conversations: Conversation[] }>("/conversations");
  const again = useCallback(() => void refresh(), [refresh]);

  useEffect(() => watchMessagePushes(again), [again]);
  useEffect(() => {
    const listening = AppState.addEventListener("change", (state) => state === "active" && again());
    return () => listening.remove();
  }, [again]);
  useEffect(() => {
    if (load.state === "ready") {
      showConversations(load.value.conversations);
    }
  }, [load, showConversations]);

  return (
    <Screen
      title={t("conversations.title")}
      tab
      scroll={false}
      actions={
        <NavButton
          icon="message-plus-outline"
          label={t("conversations.new")}
          testID="conversations-new"
          onPress={() => router.push("/conversations/new")}
        />
      }
    >
      <RecordList
        load={load}
        items={load.state === "ready" ? load.value.conversations : []}
        keyOf={(conversation) => conversation.id}
        renderItem={(conversation) => <Row conversation={conversation} />}
        icon="message-text-outline"
        empty={t("conversations.empty")}
        onRetry={reload}
        onRefresh={refresh}
      />
    </Screen>
  );
}

function Row({ conversation }: Readonly<{ conversation: Conversation }>) {
  const t = useT();
  const { language } = useSession();
  const unread = conversation.unread ? t("conversations.unread", { count: conversation.unread }) : null;
  const muted = conversation.muted ? t("conversations.muted") : null;
  const last = conversation.last_message;
  return (
    <Pressable
      testID={`conversation-${conversation.id}`}
      accessibilityRole="button"
      accessibilityLabel={[conversation.name, unread, muted].filter(Boolean).join(", ")}
      style={({ pressed }) => [shared.card, styles.row, pressed && styles.pressed]}
      onPress={() => router.push(conversationPath(conversation.id))}
    >
      <Avatar name={conversation.name} size={44} />
      <View style={styles.text}>
        <View style={styles.head}>
          <Text style={[shared.label, styles.name, !!unread && styles.unread]} numberOfLines={1}>
            {conversation.name}
          </Text>
          {muted && <Icon name="bell-off-outline" size={16} />}
          {!!last && <Text style={shared.detail}>{shortTime(last.date, language)}</Text>}
        </View>
        <View style={styles.head}>
          <Text style={[shared.detail, styles.preview]} numberOfLines={1}>
            {last ? preview(last, t) : ""}
          </Text>
          {!!conversation.unread && (
            <View style={styles.count}>
              <Text style={styles.countText}>{conversation.unread}</Text>
            </View>
          )}
        </View>
      </View>
    </Pressable>
  );
}

// The last message as its row shows it: who wrote it, then its text or the names of its files.
function preview(message: Message, t: Translate): string {
  const author = message.mine ? t("messages.you") : message.author;
  return `${author}: ${message.text || message.attachments.map((file) => file.name).join(", ")}`;
}

// The time of a message of today, or its day otherwise.
function shortTime(value: string, language: string): string {
  const date = new Date(value);
  const today = new Date().toDateString() === date.toDateString();
  return today
    ? date.toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString(language, { day: "2-digit", month: "2-digit" });
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: space.md },
  pressed: { backgroundColor: colors.primaryLight },
  text: { flex: 1, gap: 2 },
  head: { flexDirection: "row", alignItems: "center", gap: space.sm },
  name: { flex: 1 },
  unread: { fontWeight: "700" },
  preview: { flex: 1 },
  count: {
    minWidth: 22,
    height: 22,
    borderRadius: radius.pill,
    paddingHorizontal: 6,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.accent,
  },
  countText: { fontSize: fontSize.xs, fontWeight: "700", color: colors.textOnPrimary },
});
