import { randomUUID } from "expo-crypto";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { NewFile, PersonName } from "../../api";
import { useT } from "../../locale";
import { colors, styles as shared } from "../../styles";
import { Button } from "../shared/Button";
import { pickFile, pickPhoto, type PhotoSource } from "./attachments";

// The name being typed after an @ at the end of the text.
const MENTION = /@([^@\n]*)$/;

/** What the person sends: the text, the people it mentions and the files. */
export interface Draft {
  text: string;
  mentions: number[];
  files: NewFile[];
}

/** Where the person writes a message: its text, @ mentions of the people `findPeople` finds, and with `files` photos
 * from the camera or the gallery and files. `onSend` gets the draft and its Idempotency-Key, which stays the same
 * until it is sent, and answers whether it was. */
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
  return (
    <View style={styles.composer}>
      {query !== undefined &&
        suggestions.map((person) => (
          <Pressable
            key={person.id}
            testID={`mention-${person.id}`}
            accessibilityRole="button"
            style={styles.suggestion}
            onPress={() => mention(person)}
          >
            <Text style={shared.label}>@{person.name}</Text>
          </Pressable>
        ))}
      {attached.map((file, index) => (
        <Pressable
          key={`${file.name}-${index}`}
          testID={`attached-${index}`}
          accessibilityRole="button"
          accessibilityLabel={t("messages.removeFile", { name: file.name })}
          onPress={() => setAttached((kept) => kept.filter((_file, place) => place !== index))}
        >
          <Text style={shared.detail}>{t("messages.removeFile", { name: file.name })}</Text>
        </Pressable>
      ))}
      <TextInput
        testID="message-text"
        accessibilityLabel={t("messages.write")}
        placeholder={t("messages.write")}
        style={shared.input}
        multiline
        value={text}
        onChangeText={setText}
      />
      {files && (
        <View style={styles.attachments}>
          {(["camera", "gallery"] as PhotoSource[]).map((source) => (
            <Button
              key={source}
              testID={`attach-${source}`}
              label={t(source === "camera" ? "messages.camera" : "messages.gallery")}
              onPress={() => attach(() => pickPhoto(source))}
            />
          ))}
          <Button testID="attach-file" label={t("messages.file")} onPress={() => attach(pickFile)} />
        </View>
      )}
      <Button testID="message-send" primary label={t("messages.send")} disabled={empty || busy} onPress={send} />
    </View>
  );
}

const styles = StyleSheet.create({
  composer: { gap: 8 },
  suggestion: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 8 },
  attachments: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
});
