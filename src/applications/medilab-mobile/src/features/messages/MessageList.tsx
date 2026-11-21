import { Image, StyleSheet, Text, View } from "react-native";

import type { Message, MessageAttachment } from "../../api";
import type { Locale } from "../../i18n";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { styles as shared } from "../../styles";
import { colors, fontSize, radius, space } from "../../theme";
import { Avatar } from "../shared/Avatar";
import { EmptyState } from "../shared/EmptyState";
import { Icon } from "../shared/Icon";

/** How messages are shown: as the bubbles of a conversation in Discuss, or as the entries of a record's chatter. */
export type MessageLook = "conversation" | "chatter";

function day(value: string, language: Locale): string {
  return new Date(value).toLocaleDateString(language, { weekday: "short", day: "numeric", month: "short" });
}

function time(value: string, language: Locale): string {
  return new Date(value).toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit" });
}

/** The messages oldest first under the day they were written, each with its author, its time, its text and its files:
 * a photo is shown, any other file is named. In a conversation the author is named once for the messages they wrote
 * in a row, and the person's own messages stand on the right. */
export function MessageList({
  messages,
  empty,
  look,
}: Readonly<{ messages: Message[]; empty: string; look: MessageLook }>) {
  const { language } = useSession();
  if (!messages.length) {
    return <EmptyState icon={look === "chatter" ? "message-text-outline" : "chat-outline"} text={empty} />;
  }
  return (
    <>
      {messages.map((message, index) => {
        const before = messages[index - 1];
        const newDay = !before || day(before.date, language) !== day(message.date, language);
        const sameAuthor = !newDay && before?.author === message.author && before.mine === message.mine;
        return (
          <View key={message.id} style={styles.entry}>
            {newDay && (
              <View style={styles.day}>
                <Text style={styles.dayText}>{day(message.date, language)}</Text>
              </View>
            )}
            {look === "chatter" ? (
              <ChatterEntry message={message} />
            ) : (
              <Bubble message={message} first={!sameAuthor} />
            )}
          </View>
        );
      })}
    </>
  );
}

function author(message: Message, t: ReturnType<typeof useT>): string {
  return `${message.mine ? t("messages.you") : message.author}${message.note ? ` · ${t("messages.note")}` : ""}`;
}

function Bubble({ message, first }: Readonly<{ message: Message; first: boolean }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <View testID={`message-${message.id}`} style={[styles.bubbleRow, message.mine && styles.mineRow]}>
      {!message.mine && <View style={styles.avatar}>{first && <Avatar name={message.author} size={32} />}</View>}
      <View style={[styles.bubble, message.mine ? styles.mine : styles.theirs, message.note && styles.note]}>
        {(first || message.note) && <Text style={[shared.detail, styles.author]}>{author(message, t)}</Text>}
        {!!message.text && <Text style={shared.text}>{message.text}</Text>}
        {message.attachments.map((attachment) => (
          <Attachment key={attachment.id} attachment={attachment} />
        ))}
        <Text style={[shared.detail, styles.time]}>{time(message.date, language)}</Text>
      </View>
    </View>
  );
}

function ChatterEntry({ message }: Readonly<{ message: Message }>) {
  const t = useT();
  const { language } = useSession();
  return (
    <View testID={`message-${message.id}`} style={styles.chatter}>
      <Avatar name={message.author} size={36} />
      <View style={styles.chatterBody}>
        <View style={styles.chatterHead}>
          <Text style={[shared.label, styles.chatterAuthor]}>{author(message, t)}</Text>
          <Text style={shared.detail}>{time(message.date, language)}</Text>
        </View>
        <View style={[styles.chatterText, message.note && styles.chatterNote]}>
          {!!message.text && <Text style={shared.text}>{message.text}</Text>}
          {message.attachments.map((attachment) => (
            <Attachment key={attachment.id} attachment={attachment} />
          ))}
        </View>
      </View>
    </View>
  );
}

function Attachment({ attachment }: Readonly<{ attachment: MessageAttachment }>) {
  const { source } = useSession();
  if (attachment.mimetype.startsWith("image/")) {
    return (
      <Image
        testID={`attachment-${attachment.id}`}
        accessibilityLabel={attachment.name}
        source={source(`/attachments/${attachment.id}`)}
        style={styles.photo}
      />
    );
  }
  return (
    <View style={styles.file}>
      <Icon name="paperclip" size={16} />
      <Text testID={`attachment-${attachment.id}`} style={[shared.detail, styles.fileName]} numberOfLines={1}>
        {attachment.name}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  entry: { gap: space.sm },
  day: {
    alignSelf: "center",
    backgroundColor: colors.secondaryLight,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 2,
    marginVertical: space.xs,
  },
  dayText: { fontSize: fontSize.xs, fontWeight: "600", color: colors.textSecondary },
  bubbleRow: { flexDirection: "row", alignItems: "flex-end", gap: space.sm },
  mineRow: { justifyContent: "flex-end" },
  avatar: { width: 32 },
  bubble: { maxWidth: "80%", gap: 2, paddingHorizontal: space.md, paddingVertical: space.sm, borderRadius: radius.lg },
  mine: { backgroundColor: colors.primaryLight, borderBottomRightRadius: radius.sm },
  theirs: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderBottomLeftRadius: radius.sm,
  },
  note: { backgroundColor: colors.warningSoft },
  author: { fontWeight: "600", color: colors.textSecondary },
  time: { alignSelf: "flex-end", fontSize: fontSize.xs },
  chatter: { flexDirection: "row", gap: space.md },
  chatterBody: { flex: 1, gap: space.xs },
  chatterHead: { flexDirection: "row", alignItems: "baseline", gap: space.sm, flexWrap: "wrap" },
  chatterAuthor: { fontWeight: "600" },
  chatterText: { gap: space.xs },
  chatterNote: { backgroundColor: colors.warningSoft, borderRadius: radius.md, padding: space.sm },
  photo: { width: 200, height: 150, borderRadius: radius.md, marginTop: space.xs },
  file: { flexDirection: "row", alignItems: "center", gap: space.xs },
  fileName: { flexShrink: 1 },
});
