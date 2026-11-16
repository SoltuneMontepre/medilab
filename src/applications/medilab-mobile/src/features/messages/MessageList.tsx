import { Image, StyleSheet, Text, View } from "react-native";

import type { Message, MessageAttachment } from "../../api";
import { useT } from "../../locale";
import { useSession } from "../../session";
import { colors, styles as shared } from "../../styles";

/** The messages oldest first, each with its author, its time, its text and its files: a photo is shown, any other file
 * is named. */
export function MessageList({ messages, empty }: Readonly<{ messages: Message[]; empty: string }>) {
  const t = useT();
  const { language } = useSession();
  if (!messages.length) {
    return <Text style={shared.detail}>{empty}</Text>;
  }
  return (
    <>
      {messages.map((message) => (
        <View
          key={message.id}
          testID={`message-${message.id}`}
          style={[styles.message, message.mine && styles.mine, message.note && styles.note]}
        >
          <Text style={shared.label}>
            {message.mine ? t("messages.you") : message.author}
            {message.note ? ` · ${t("messages.note")}` : ""}
          </Text>
          {!!message.text && <Text style={shared.text}>{message.text}</Text>}
          {message.attachments.map((attachment) => (
            <Attachment key={attachment.id} attachment={attachment} />
          ))}
          <Text style={shared.detail}>{new Date(message.date).toLocaleString(language)}</Text>
        </View>
      ))}
    </>
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
    <Text testID={`attachment-${attachment.id}`} style={shared.detail}>
      {attachment.name}
    </Text>
  );
}

const styles = StyleSheet.create({
  message: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, gap: 4, marginRight: 32 },
  mine: { borderColor: colors.primary, marginRight: 0, marginLeft: 32 },
  note: { backgroundColor: "#fff8e6" },
  photo: { width: 200, height: 150, borderRadius: 6 },
});
