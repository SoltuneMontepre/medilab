import { useRef, type ComponentRef, type ReactNode } from "react";
import { ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import type { Message, PersonName } from "../../api";
import type { Load } from "../../load";
import { useT } from "../../locale";
import { useAction } from "../../record";
import { colors, layout, space } from "../../theme";
import { ActionProblem } from "../connection/ActionProblem";
import { LoadNotice } from "../connection/LoadNotice";
import { Button } from "../shared/Button";
import { content, Screen } from "../shared/Screen";
import { Composer, type Draft } from "./Composer";
import type { useThread } from "./useThread";
import { MessageList, type MessageLook } from "./MessageList";

/** A screen of messages: its title and the navbar's actions, the messages oldest first with the way to older ones,
 * kept scrolled to the newest, and where the person writes at the bottom. A conversation shows them as Discuss does,
 * a chatter as the web's chatter does; a conversation's navbar has its own bell to mute it instead of the
 * notifications. `post` sends a draft with its Idempotency-Key and answers the message posted. */
export function Thread({
  title,
  actions,
  look,
  thread,
  gone,
  empty,
  findPeople,
  post,
  files = false,
}: Readonly<{
  title: string;
  actions?: ReactNode;
  look: MessageLook;
  thread: ReturnType<typeof useThread>;
  gone: string;
  empty: string;
  findPeople: (query: string) => Promise<PersonName[]>;
  post: (draft: Draft, key: string) => Promise<Message | null>;
  files?: boolean;
}>) {
  const t = useT();
  const { problem, busy, run } = useAction();
  const { load } = thread;
  const list = useRef<ComponentRef<typeof ScrollView>>(null);

  async function send(draft: Draft, key: string) {
    let sent = false;
    await run(async () => {
      const message = await post(draft, key);
      if (message) {
        thread.add(message);
      }
      sent = true;
    });
    return sent;
  }

  return (
    <Screen
      title={title}
      actions={actions}
      bell={look !== "conversation"}
      scroll={false}
      footer={
        load.state === "ready" && (
          <SafeAreaView edges={["bottom", "left", "right"]} style={styles.composer}>
            <View style={styles.composerInner}>
              <ActionProblem problem={problem?.load ?? null} gone={gone} onRetry={problem?.retry ?? (() => undefined)} />
              <Composer findPeople={findPeople} onSend={send} files={files} busy={busy} />
            </View>
          </SafeAreaView>
        )
      }
    >
      <ScrollView
        ref={list}
        contentContainerStyle={styles.messages}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
      >
        <LoadNotice load={load as Load<unknown>} gone={gone} onRetry={thread.read} />
        {load.state === "ready" && (
          <>
            {thread.hasOlder && (
              <View style={styles.older}>
                <Button testID="messages-older" label={t("more")} icon="history" compact onPress={thread.older} />
              </View>
            )}
            <MessageList messages={load.value} empty={empty} look={look} />
          </>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  messages: { ...content, paddingBottom: space.lg, flexGrow: 1 },
  older: { alignItems: "center" },
  composer: { backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  composerInner: {
    width: "100%",
    maxWidth: layout.contentWidth,
    alignSelf: "center",
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    gap: space.sm,
  },
});
