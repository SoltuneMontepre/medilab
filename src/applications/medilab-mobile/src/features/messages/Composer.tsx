import { randomUUID } from "expo-crypto";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import type { NewFile, PersonName } from "../../api";
import { useT } from "../../locale";
import { colors, fontSize, radius, space } from "../../theme";
import { Icon, type IconName } from "../shared/Icon";
import { pickFile, pickPhoto, type PhotoSource } from "./attachments";

// The name being typed after an @ at the end of the text.
const MENTION = /@([^@\n]*)$/;

/** What the person sends: the text, the people it mentions and the files. */
export interface Draft {
  text: string;
  mentions: number[];
  files: NewFile[];
}

const SOURCES: { source: PhotoSource; icon: IconName; label: "messages.camera" | "messages.gallery" }[] = [
  { source: "camera", icon: "camera-outline", label: "messages.camera" },
  { source: "gallery", icon: "image-outline", label: "messages.gallery" },
];

/** Where the person writes a message, as Discuss's composer: its text, @ mentions of the people `findPeople` finds
 * offered above it, and with `files` photos from the camera or the gallery and files. `onSend` gets the draft and its
 * Idempotency-Key, which stays the same until it is sent, and answers whether it was. */
export function Composer({
  findPeople,
  onSend,
  files = false,
  busy = false,
}: Readonly<{
  findPeople: (query: string) => Promise<PersonName[]>;
  onSend: (draft: Draft, key: string) => Promise<boolean>;
  files?: boolean;
  busy?: boolean;
}>) {
  const t = useT();
  const [text, setText] = useState("");
  const [mentioned, setMentioned] = useState<PersonName[]>([]);
  const [attached, setAttached] = useState<NewFile[]>([]);
  const [suggestions, setSuggestions] = useState<PersonName[]>([]);
  const [key, setKey] = useState(randomUUID);
  const typed = MENTION.exec(text)?.[1];
  // After a person is mentioned, the words that follow their name are the message, not another name.
  const query = mentioned.some((person) => typed?.startsWith(person.name)) ? undefined : typed;

  useEffect(() => {
    if (query === undefined) {
      return;
    }
    let current = true;
    findPeople(query)
      .then((people) => current && setSuggestions(people))
      .catch(() => current && setSuggestions([]));
    return () => {
      current = false;
    };
  }, [query, findPeople]);

  function mention(person: PersonName) {
    setText(text.replace(MENTION, `@${person.name} `));
    setMentioned((people) => [...people.filter((kept) => kept.id !== person.id), person]);
  }

  async function attach(pick: () => Promise<NewFile | null>) {
    const file = await pick().catch(() => null);
    if (file) {
      setAttached((kept) => [...kept, file]);
    }
  }

  async function send() {
    const draft = {
      text: text.trim(),
      // A person whose name the text no longer has is no longer mentioned.
      mentions: mentioned.filter((person) => text.includes(`@${person.name}`)).map((person) => person.id),
      files: attached,
    };
    if (await onSend(draft, key)) {
      setText("");
      setMentioned([]);
      setAttached([]);
      setKey(randomUUID());
    }
  }

  const empty = !text.trim() && !attached.length;
  const suggesting = query !== undefined && suggestions.length > 0;
  return (
    <View style={styles.composer}>
      {(suggesting || attached.length > 0) && (
        <ScrollView horizontal keyboardShouldPersistTaps="handled" contentContainerStyle={styles.chips}>
          {suggesting &&
            suggestions.map((person) => (
              <Pressable
                key={person.id}
                testID={`mention-${person.id}`}
                accessibilityRole="button"
                accessibilityLabel={`@${person.name}`}
                style={styles.chip}
                onPress={() => mention(person)}
              >
                <Text style={styles.chipText}>@{person.name}</Text>
              </Pressable>
            ))}
          {attached.map((file, index) => (
            <Pressable
              key={`${file.name}-${index}`}
              testID={`attached-${index}`}
              accessibilityRole="button"
              accessibilityLabel={t("messages.removeFile", { name: file.name })}
              style={[styles.chip, styles.file]}
              onPress={() => setAttached((kept) => kept.filter((_file, place) => place !== index))}
            >
              <Icon name="paperclip" size={16} />
              <Text style={styles.fileText} numberOfLines={1}>
                {file.name}
              </Text>
              <Icon name="close" size={16} />
            </Pressable>
          ))}
        </ScrollView>
      )}
      <View style={styles.row}>
        {files &&
          SOURCES.map(({ source, icon, label }) => (
            <IconButton key={source} icon={icon} label={t(label)} testID={`attach-${source}`} onPress={() => attach(() => pickPhoto(source))} />
          ))}
        {files && <IconButton icon="paperclip" label={t("messages.file")} testID="attach-file" onPress={() => attach(pickFile)} />}
        <TextInput
          testID="message-text"
          accessibilityLabel={t("messages.write")}
          placeholder={t("messages.write")}
          placeholderTextColor={colors.textMuted}
          style={styles.input}
          multiline
          value={text}
          onChangeText={setText}
        />
        <Pressable
          testID="message-send"
          accessibilityRole="button"
          accessibilityLabel={t("messages.send")}
          accessibilityState={{ disabled: empty || busy }}
          disabled={empty || busy}
          style={[styles.send, (empty || busy) && styles.sendDisabled]}
          onPress={send}
        >
          <Icon name="send" size={20} color={colors.textOnPrimary} />
        </Pressable>
      </View>
    </View>
  );
}

function IconButton({
  icon,
  label,
  testID,
  onPress,
}: Readonly<{ icon: IconName; label: string; testID: string; onPress: () => void }>) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
      hitSlop={4}
      style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
      onPress={onPress}
    >
      <Icon name={icon} size={24} color={colors.textSecondary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  composer: { gap: space.sm },
  chips: { gap: space.sm },
  chip: {
    minHeight: 36,
    justifyContent: "center",
    borderRadius: radius.pill,
    backgroundColor: colors.accentSoft,
    paddingHorizontal: space.md,
  },
  chipText: { fontSize: fontSize.base, fontWeight: "600", color: colors.primary },
  file: { flexDirection: "row", alignItems: "center", gap: space.xs, backgroundColor: colors.secondaryLight, maxWidth: 220 },
  fileText: { flexShrink: 1, fontSize: fontSize.sm, color: colors.text },
  row: { flexDirection: "row", alignItems: "flex-end", gap: space.xs },
  input: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: colors.borderControl,
    borderRadius: 22,
    paddingHorizontal: space.lg,
    paddingTop: 11,
    paddingBottom: 11,
    fontSize: fontSize.md,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  iconButton: { width: 40, height: 44, alignItems: "center", justifyContent: "center", borderRadius: radius.pill },
  pressed: { backgroundColor: colors.secondaryLight },
  send: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  sendDisabled: { opacity: 0.4 },
});
